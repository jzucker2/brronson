"""Subtitle salvage endpoints."""

import errno
import logging
import os
import shutil
import time
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Body, HTTPException

from ..config import (
    DEFAULT_SUBTITLE_EXTENSIONS,
    get_recycled_movies_directory,
    get_salvaged_movies_directory,
)
from ..helpers import (
    has_subtitle_in_root,
    is_subtitle_file,
    validate_directory,
)
from ..metrics import (
    salvage_errors_total,
    salvage_folders_copied_total,
    salvage_folders_scanned_total,
    salvage_folders_skipped_total,
    salvage_folders_with_subtitles_found,
    salvage_files_skipped_total,
    salvage_operation_duration,
    salvage_subtitle_files_copied_total,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/v1/salvage/subtitle-folders")
async def salvage_subtitle_folders(
    dry_run: bool = True,
    batch_size: int = 100,
    subtitle_extensions: Optional[List[str]] = Body(None),
):
    """
    Traverse the recycled movies directory and copy folders that have subtitles
    in the root to the salvaged movies directory.

    This function:
    - Scans all folders in the recycled movies directory
    - Identifies folders that contain subtitle files in their root
    - Copies only subtitle files (not media files, images, or any other files)
    - Preserves the folder structure during the copy
    - Leaves the original files in the recycled directory unchanged
    - Skips folders and files if the destination already exists (does not overwrite)

    Args:
        dry_run: If True, only show what would be copied (default: True)
        batch_size: Maximum number of subtitle files to copy per request (default: 100).
                   Only counts files actually copied, not skipped files. This makes the
                   operation re-entrant - subsequent requests will continue from where
                   the previous request stopped.
        subtitle_extensions: List of subtitle file extensions (with leading dot).
                            If None, uses DEFAULT_SUBTITLE_EXTENSIONS

    Returns:
        dict: Salvage results including folders found, copied, and errors
    """
    start_time = time.time()

    # Validate batch_size parameter
    if batch_size <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"batch_size must be a positive integer, got {batch_size}",
        )

    recycled_dir = get_recycled_movies_directory()
    salvaged_dir = get_salvaged_movies_directory()

    if subtitle_extensions is None:
        subtitle_extensions = DEFAULT_SUBTITLE_EXTENSIONS

    try:
        recycled_path = Path(recycled_dir).resolve()
        salvaged_path = Path(salvaged_dir).resolve()

        # Validate recycled directory first
        validate_directory(recycled_path, recycled_dir, "salvage")

        # Ensure salvaged directory exists (create if it doesn't)
        try:
            salvaged_path.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError):
            # If directory creation fails, validate_directory will handle the 404
            pass

        # Validate salvaged directory (after attempting to create it)
        validate_directory(salvaged_path, salvaged_dir, "salvage")

        logger.info(
            f"Subtitle salvage: Scanning {recycled_path} for folders with subtitles"
        )

        # Get all subdirectories in recycled directory
        folders_to_check = []
        try:
            for item in recycled_path.iterdir():
                if item.is_dir():
                    folders_to_check.append(item)
        except OSError as e:
            # Handle stale file handle errors (common with NFS mounts)
            if e.errno == errno.ESTALE:
                salvage_errors_total.labels(
                    recycled_directory=recycled_dir,
                    salvaged_directory=salvaged_dir,
                    error_type="stale_file_handle",
                ).inc()
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Stale file handle error accessing recycled directory "
                        f"'{recycled_dir}'. This usually indicates a network "
                        f"filesystem mount issue. Please check the mount status "
                        f"and try again."
                    ),
                )
            # Fall through to generic error handling for other OSError cases
            raise
        except Exception as e:
            salvage_errors_total.labels(
                recycled_directory=recycled_dir,
                salvaged_directory=salvaged_dir,
                error_type="directory_read_error",
            ).inc()
            raise HTTPException(
                status_code=500,
                detail=f"Error reading recycled directory: {str(e)}",
            )

        # Record metric for folders scanned
        salvage_folders_scanned_total.labels(
            recycled_directory=recycled_dir, dry_run=str(dry_run).lower()
        ).inc(len(folders_to_check))

        # Find folders with subtitles in root
        folders_with_subtitles = []
        for folder_path in folders_to_check:
            if has_subtitle_in_root(folder_path, subtitle_extensions):
                folders_with_subtitles.append(folder_path)

        logger.info(
            f"Found {len(folders_with_subtitles)} folders with subtitles in root"
        )

        # Record metric for folders with subtitles found
        salvage_folders_with_subtitles_found.labels(
            recycled_directory=recycled_dir, dry_run=str(dry_run).lower()
        ).set(len(folders_with_subtitles))

        copied_folders = []
        skipped_folders = []
        subtitle_files_copied = 0
        subtitle_files_skipped = 0
        errors = []
        files_copied_this_batch = 0  # Track files copied for batch_size limit
        batch_limit_hit = (
            False  # Track if we actually hit the batch limit (stopped early)
        )

        # Process each folder with subtitles
        for folder_path in folders_with_subtitles:
            # Check if we've reached the batch size limit before processing folder
            if files_copied_this_batch >= batch_size:
                batch_limit_hit = True
                logger.info(
                    f"Batch size limit reached ({batch_size} files copied), "
                    f"stopping processing. {len(folders_with_subtitles) - len(copied_folders) - len(skipped_folders)} folders remaining."
                )
                break

            folder_name = folder_path.name
            target_folder_path = salvaged_path / folder_name

            # Track files copied/skipped for this folder
            folder_files_copied = 0
            folder_files_skipped = 0

            if not dry_run:
                # Check if target folder already existed before we start
                target_existed_before = target_folder_path.exists()
                target_created = False
                try:
                    logger.info(
                        f"Starting to copy folder: {folder_name} from {folder_path} to {target_folder_path}"
                    )

                    # Create target folder (only mark as created if it didn't exist)
                    target_folder_path.mkdir(parents=True, exist_ok=True)
                    if not target_existed_before:
                        target_created = True

                    # Copy folder structure and subtitle files only
                    # Walk through the source folder
                    batch_limit_reached = False
                    for root, dirs, files in os.walk(folder_path):
                        # Check batch limit before processing more files
                        if files_copied_this_batch >= batch_size:
                            batch_limit_reached = True
                            batch_limit_hit = True
                            break

                        # Calculate relative path from source folder
                        rel_path = Path(root).relative_to(folder_path)
                        target_dir = target_folder_path / rel_path

                        # Create target directory structure
                        target_dir.mkdir(parents=True, exist_ok=True)

                        # Copy files: only subtitle files, skip everything else
                        # Sort files to ensure consistent processing order
                        for file in sorted(files):
                            # Check batch limit before processing each file
                            if files_copied_this_batch >= batch_size:
                                batch_limit_reached = True
                                batch_limit_hit = True
                                break
                            source_file = Path(root) / file
                            target_file = target_dir / file

                            # Only copy subtitle files, skip all other files
                            if is_subtitle_file(
                                source_file, subtitle_extensions
                            ):
                                # Check if target file already exists
                                if target_file.exists():
                                    logger.info(
                                        f"Skipping {source_file.name} - target file already exists: {target_file}"
                                    )
                                    folder_files_skipped += 1
                                    subtitle_files_skipped += 1
                                    salvage_files_skipped_total.labels(
                                        recycled_directory=recycled_dir,
                                        salvaged_directory=salvaged_dir,
                                        dry_run=str(dry_run).lower(),
                                    ).inc()
                                else:
                                    shutil.copy2(
                                        str(source_file), str(target_file)
                                    )
                                    folder_files_copied += 1
                                    subtitle_files_copied += 1
                                    files_copied_this_batch += 1
                                    logger.debug(
                                        f"Copied subtitle file: {source_file.name} to {target_file}"
                                    )
                            else:
                                # Skip all non-subtitle files (media files, .nfo, .txt, etc.)
                                logger.debug(
                                    f"Skipping non-subtitle file: {source_file.name}"
                                )

                        # Break out of directory walk if batch limit reached
                        if batch_limit_reached:
                            break

                    # Determine if folder should be counted as copied or skipped
                    if folder_files_copied > 0:
                        copied_folders.append(folder_name)
                        logger.info(
                            f"Successfully finished copying folder: {folder_name} ({folder_files_copied} files copied, {folder_files_skipped} files skipped)"
                        )
                        salvage_folders_copied_total.labels(
                            recycled_directory=recycled_dir,
                            salvaged_directory=salvaged_dir,
                            dry_run=str(dry_run).lower(),
                        ).inc()
                    elif folder_files_skipped > 0:
                        # All files were skipped (folder existed with all files)
                        skipped_folders.append(folder_name)
                        logger.info(
                            f"Folder {folder_name} skipped - all files already exist ({folder_files_skipped} files skipped)"
                        )
                        salvage_folders_skipped_total.labels(
                            recycled_directory=recycled_dir,
                            salvaged_directory=salvaged_dir,
                            dry_run=str(dry_run).lower(),
                        ).inc()
                    else:
                        # No subtitle files found in folder
                        logger.warning(
                            f"Folder {folder_name} had no subtitle files to copy"
                        )

                except Exception as e:
                    error_msg = (
                        f"Failed to copy folder {folder_name}: {str(e)}"
                    )
                    logger.error(error_msg)
                    errors.append(error_msg)
                    salvage_errors_total.labels(
                        recycled_directory=recycled_dir,
                        salvaged_directory=salvaged_dir,
                        error_type="folder_copy_error",
                    ).inc()

                    # Clean up partially created target folder on failure
                    if target_created and target_folder_path.exists():
                        try:
                            logger.warning(
                                f"Cleaning up partially created folder: {target_folder_path}"
                            )
                            shutil.rmtree(target_folder_path)
                            logger.info(
                                f"Successfully cleaned up partial folder: {target_folder_path}"
                            )
                        except Exception as cleanup_error:
                            logger.error(
                                f"Failed to clean up partial folder {target_folder_path}: {str(cleanup_error)}"
                            )
            else:
                # Dry run mode - count what would be copied
                try:
                    logger.info(
                        f"DRY RUN: Would copy folder: {folder_name} from {folder_path} to {target_folder_path}"
                    )

                    # Count subtitle files that would be copied (checking if they exist)
                    batch_limit_reached = False
                    for root, dirs, files in os.walk(folder_path):
                        if files_copied_this_batch >= batch_size:
                            batch_limit_reached = True
                            batch_limit_hit = True
                            break
                        rel_path = Path(root).relative_to(folder_path)
                        target_dir = target_folder_path / rel_path
                        # Sort files to ensure consistent processing order
                        for file in sorted(files):
                            if files_copied_this_batch >= batch_size:
                                batch_limit_reached = True
                                batch_limit_hit = True
                                break
                            source_file = Path(root) / file
                            if is_subtitle_file(
                                source_file, subtitle_extensions
                            ):
                                target_file = target_dir / file
                                if target_file.exists():
                                    folder_files_skipped += 1
                                    subtitle_files_skipped += 1
                                    salvage_files_skipped_total.labels(
                                        recycled_directory=recycled_dir,
                                        salvaged_directory=salvaged_dir,
                                        dry_run=str(dry_run).lower(),
                                    ).inc()
                                else:
                                    folder_files_copied += 1
                                    subtitle_files_copied += 1
                                    files_copied_this_batch += 1
                        if batch_limit_reached:
                            break

                    # Determine if folder would be copied or skipped
                    if folder_files_copied > 0:
                        copied_folders.append(folder_name)
                        salvage_folders_copied_total.labels(
                            recycled_directory=recycled_dir,
                            salvaged_directory=salvaged_dir,
                            dry_run=str(dry_run).lower(),
                        ).inc()
                    elif folder_files_skipped > 0:
                        skipped_folders.append(folder_name)
                        salvage_folders_skipped_total.labels(
                            recycled_directory=recycled_dir,
                            salvaged_directory=salvaged_dir,
                            dry_run=str(dry_run).lower(),
                        ).inc()
                    else:
                        # No subtitle files found in folder
                        logger.warning(
                            f"DRY RUN: Folder {folder_name} had no subtitle files to copy"
                        )

                except Exception as e:
                    error_msg = f"DRY RUN: Failed to process folder {folder_name}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    salvage_errors_total.labels(
                        recycled_directory=recycled_dir,
                        salvaged_directory=salvaged_dir,
                        error_type="folder_copy_error",
                    ).inc()

        # Record metrics for subtitle files copied and skipped
        if subtitle_files_copied > 0:
            salvage_subtitle_files_copied_total.labels(
                recycled_directory=recycled_dir,
                salvaged_directory=salvaged_dir,
                dry_run=str(dry_run).lower(),
            ).inc(subtitle_files_copied)

        # Record operation duration
        operation_duration = time.time() - start_time
        salvage_operation_duration.labels(
            operation_type="salvage_subtitle_folders",
            recycled_directory=recycled_dir,
            salvaged_directory=salvaged_dir,
        ).observe(operation_duration)

        response = {
            "recycled_directory": str(recycled_path),
            "salvaged_directory": str(salvaged_path),
            "dry_run": dry_run,
            "batch_size": batch_size,
            "subtitle_extensions": subtitle_extensions,
            "folders_scanned": len(folders_to_check),
            "folders_with_subtitles_found": len(folders_with_subtitles),
            "folders_copied": len(copied_folders),
            "folders_skipped": len(skipped_folders),
            "subtitle_files_copied": subtitle_files_copied,
            "subtitle_files_skipped": subtitle_files_skipped,
            "batch_limit_reached": batch_limit_hit,
            "errors": len(errors),
            "folders_with_subtitles": [f.name for f in folders_with_subtitles],
            "copied_folders": copied_folders,
            "skipped_folders": skipped_folders,
            "error_details": errors,
        }

        return response

    except HTTPException:
        # Re-raise HTTPExceptions (like 404 for missing directories) as-is
        raise
    except Exception as e:
        salvage_errors_total.labels(
            recycled_directory=recycled_dir,
            salvaged_directory=salvaged_dir,
            error_type="operation_error",
        ).inc()
        raise HTTPException(
            status_code=500,
            detail=f"Error during subtitle salvage operation: {str(e)}",
        )
