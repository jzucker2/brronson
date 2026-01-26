"""Empty folder cleanup endpoints."""

import logging
import os
import time
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException

from ..config import get_target_directory
from ..helpers import validate_directory
from ..metrics import (
    empty_folders_batch_operations_total,
    empty_folders_errors_total,
    empty_folders_found_total,
    empty_folders_operation_duration,
    empty_folders_removed_total,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def find_empty_folders(
    directory_path: Path, max_folders: int = None
) -> List[Path]:
    """
    Recursively find empty folders in a directory.

    This function finds empty folders, including nested ones.
    It processes directories from deepest to shallowest to ensure
    that when a parent folder only contains empty subdirectories,
    it can be identified correctly.

    IMPORTANT: The target directory itself is never included in the results,
    even if it becomes empty. This prevents accidental deletion of the
    configured target directory root.

    Args:
        directory_path: Path to the directory to scan
        max_folders: Maximum number of empty folders to find. If None,
                    scans the entire directory. If provided (> 0), stops
                    scanning once this many folders are found.

    Returns:
        List of Path objects for empty folders (sorted deepest first)
    """
    empty_folders = []
    empty_folders_set = set()  # Track which folders we've identified as empty
    resolved_target = directory_path.resolve()

    # Walk through directory from bottom up (deepest first)
    # This ensures we process nested empty folders correctly
    for root, dirs, files in os.walk(directory_path, topdown=False):
        # Stop scanning if we've reached the maximum number of folders
        if max_folders is not None and len(empty_folders) >= max_folders:
            break

        root_path = Path(root).resolve()

        # CRITICAL: Never include the target directory itself in results
        # This prevents accidental deletion of the configured root directory
        if root_path == resolved_target:
            continue

        # Check if directory is empty
        try:
            items = list(root_path.iterdir())
            if len(items) == 0:
                # Directory is completely empty
                empty_folders.append(root_path)
                empty_folders_set.add(root_path.resolve())
            else:
                # Check if directory only contains empty subdirectories
                # (that we've already identified as empty)
                has_non_empty_content = False
                for item in items:
                    # CRITICAL: Check for symlinks FIRST, before is_dir() or is_file()
                    # because is_dir() follows symlinks. A symlink to a directory
                    # would be incorrectly treated as a directory, but the symlink
                    # itself is a filesystem entry that makes the folder non-empty.
                    if item.is_symlink():
                        # Has symlink (even if it points to an empty directory),
                        # so not empty. The symlink itself is content.
                        has_non_empty_content = True
                        break
                    # Check for regular files
                    elif item.is_file():
                        # Has files, so not empty
                        has_non_empty_content = True
                        break
                    # Check for directories (only reached if not a symlink)
                    elif item.is_dir():
                        # Check if this subdirectory is in our empty set
                        if item.resolve() not in empty_folders_set:
                            # Has non-empty subdirectory, so not empty
                            has_non_empty_content = True
                            break
                    # Check for other special files: sockets, named pipes,
                    # device files, etc. These return False for both
                    # is_file() and is_dir() and is_symlink()
                    else:
                        # Check if item exists (catches other special files)
                        # Use stat() to catch other special files
                        try:
                            # Try to stat the item - if it succeeds, it's a real
                            # item (socket, pipe, device, etc.)
                            item.stat()
                            # Item exists and is stat-able, so not empty
                            has_non_empty_content = True
                            break
                        except (OSError, ValueError):
                            # Item doesn't exist or can't be stat'd
                            # This shouldn't happen if we got it from iterdir(),
                            # but handle gracefully
                            pass

                if not has_non_empty_content:
                    # Directory only contains empty subdirectories, so it's empty
                    empty_folders.append(root_path)
                    empty_folders_set.add(root_path.resolve())
                    # Stop scanning if we've reached the maximum number of folders
                    if (
                        max_folders is not None
                        and len(empty_folders) >= max_folders
                    ):
                        break
        except (OSError, PermissionError):
            # Skip directories we can't read
            pass

    return empty_folders


@router.post("/api/v1/cleanup/empty-folders")
async def cleanup_empty_folders(dry_run: bool = True, batch_size: int = 100):
    """
    Recursively find and delete empty folders in the target directory.

    This endpoint:
    - Scans the target directory recursively
    - Identifies empty folders (folders with no files or subdirectories)
    - Deletes empty folders (or shows what would be deleted in dry run mode)
    - Processes folders from deepest to shallowest to handle nested empty folders
    - Supports batch processing for re-entrant operations

    Args:
        dry_run: If True, only show what would be deleted (default: True)
        batch_size: Maximum number of empty folders to scan and process per request
                   (default: 100). If provided, scanning stops once this many empty
                   folders are found. If not provided or 0, performs a full scan
                   of the entire directory. Only counts folders actually deleted,
                   not skipped folders. This makes the operation re-entrant -
                   subsequent requests will continue from where the previous request
                   stopped.

    Returns:
        dict: Cleanup results including folders found, removed, and errors
    """
    start_time = time.time()
    target_dir = get_target_directory()

    # Validate batch_size parameter
    # batch_size of 0 means full scan (no limit), negative values are invalid
    if batch_size < 0:
        raise HTTPException(
            status_code=400,
            detail=f"batch_size must be a non-negative integer, got {batch_size}",
        )

    try:
        target_path = Path(target_dir).resolve()
        validate_directory(target_path, target_dir, "empty_folders")
    except HTTPException:
        # validate_directory already recorded the error in the correct metric
        # (empty_folders_errors_total), so we just re-raise
        raise
    except Exception as e:
        # For any other unexpected exceptions, record in empty_folders_errors_total
        empty_folders_errors_total.labels(
            target_directory=target_dir, error_type="validation_error"
        ).inc()
        raise HTTPException(
            status_code=400, detail=f"Invalid target directory: {str(e)}"
        )

    try:
        # Find empty folders, with optional batch_size limit on scanning
        # If batch_size > 0, only scan until we find that many folders
        # If batch_size is 0 or None, scan the entire directory
        max_folders_to_scan = batch_size if batch_size > 0 else None
        empty_folders = find_empty_folders(
            target_path, max_folders=max_folders_to_scan
        )

        logger.info(
            f"Empty folder scan completed: Found {len(empty_folders)} empty folders in {target_path}"
        )
        if empty_folders:
            logger.info(
                f"Empty folders found: {', '.join([str(f.relative_to(target_path)) for f in empty_folders[:10]])}{'...' if len(empty_folders) > 10 else ''}"
            )

        removed_folders = []
        errors = []
        # batch_limit_reached is True if:
        # - batch_size > 0 (a limit was set)
        # - We found exactly batch_size folders (scan stopped at limit)
        # This indicates there may be more folders remaining
        batch_limit_hit = batch_size > 0 and len(empty_folders) >= batch_size

        # Process empty folders for removal (already sorted deepest first)
        # Note: If batch_size was provided, we already limited the scan,
        # so we process all found folders. If batch_size was 0 or not provided,
        # we process all found folders (full scan).
        for folder_path in empty_folders:
            # CRITICAL: Defense in depth - never delete the target directory itself
            # This is a safety guard even though find_empty_folders excludes it
            if folder_path.resolve() == target_path.resolve():
                logger.warning(
                    f"Attempted to delete target directory itself: {folder_path}. "
                    f"This should never happen, but skipping to prevent data loss."
                )
                continue

            if not dry_run:
                try:
                    # Check if folder still exists (might have been deleted as part of parent)
                    if not folder_path.exists():
                        # Folder was already deleted (likely as part of parent removal)
                        continue

                    logger.info(
                        f"Starting to remove empty folder: {folder_path.relative_to(target_path)}"
                    )
                    folder_path.rmdir()
                    removed_folders.append(
                        str(folder_path.relative_to(target_path))
                    )
                    logger.info(
                        f"Successfully finished removing empty folder: {folder_path.relative_to(target_path)}"
                    )
                    empty_folders_removed_total.labels(
                        target_directory=target_dir,
                        dry_run=str(dry_run).lower(),
                    ).inc()
                except OSError as e:
                    # Folder might not exist anymore (deleted as part of parent)
                    if not folder_path.exists():
                        continue
                    error_msg = f"Failed to remove {folder_path}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    empty_folders_errors_total.labels(
                        target_directory=target_dir,
                        error_type="folder_removal_error",
                    ).inc()
                    # Don't count errors toward batch limit - only successful
                    # deletions count. This ensures re-entrancy: persistent errors
                    # won't block progress on other folders.
                except Exception as e:
                    error_msg = f"Failed to remove {folder_path}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    empty_folders_errors_total.labels(
                        target_directory=target_dir,
                        error_type="folder_removal_error",
                    ).inc()
                    # Don't count errors toward batch limit - only successful
                    # deletions count. This ensures re-entrancy: persistent errors
                    # won't block progress on other folders.
            else:
                logger.info(
                    f"DRY RUN: Would remove empty folder: {folder_path.relative_to(target_path)}"
                )

        # Record metrics for found folders
        empty_folders_found_total.labels(
            target_directory=target_dir, dry_run=str(dry_run).lower()
        ).inc(len(empty_folders))

        # Record batch operation metric
        empty_folders_batch_operations_total.labels(
            target_directory=target_dir,
            batch_size=str(batch_size),
            dry_run=str(dry_run).lower(),
        ).inc()

        # Record operation duration
        operation_duration = time.time() - start_time
        empty_folders_operation_duration.labels(
            operation_type="cleanup_empty_folders", target_directory=target_dir
        ).observe(operation_duration)

        return {
            "directory": str(target_path),
            "dry_run": dry_run,
            "batch_size": batch_size,
            "empty_folders_found": len(empty_folders),
            "empty_folders_removed": len(removed_folders),
            "errors": len(errors),
            "batch_limit_reached": batch_limit_hit,
            "remaining_folders": (
                # If batch limit was hit, we don't know how many remain
                # without a full scan, so return 0 (unknown)
                0
            ),
            "empty_folders": [
                str(f.relative_to(target_path)) for f in empty_folders
            ],
            "removed_folders": removed_folders,
            "error_details": errors,
        }

    except Exception as e:
        empty_folders_errors_total.labels(
            target_directory=target_dir, error_type="operation_error"
        ).inc()
        raise HTTPException(
            status_code=500,
            detail=f"Error during empty folder cleanup: {str(e)}",
        )
