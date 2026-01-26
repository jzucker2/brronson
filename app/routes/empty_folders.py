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


def find_empty_folders(directory_path: Path) -> List[Path]:
    """
    Recursively find all empty folders in a directory.

    This function finds all empty folders, including nested ones.
    It processes directories from deepest to shallowest to ensure
    that when a parent folder only contains empty subdirectories,
    it can be identified correctly.

    IMPORTANT: The target directory itself is never included in the results,
    even if it becomes empty. This prevents accidental deletion of the
    configured target directory root.

    Args:
        directory_path: Path to the directory to scan

    Returns:
        List of Path objects for empty folders (sorted deepest first)
    """
    empty_folders = []
    empty_folders_set = set()  # Track which folders we've identified as empty
    resolved_target = directory_path.resolve()

    # Walk through directory from bottom up (deepest first)
    # This ensures we process nested empty folders correctly
    for root, dirs, files in os.walk(directory_path, topdown=False):
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
                    # Check for regular files
                    if item.is_file():
                        # Has files, so not empty
                        has_non_empty_content = True
                        break
                    # Check for directories
                    elif item.is_dir():
                        # Check if this subdirectory is in our empty set
                        if item.resolve() not in empty_folders_set:
                            # Has non-empty subdirectory, so not empty
                            has_non_empty_content = True
                            break
                    # Check for special files: symlinks (including broken),
                    # sockets, named pipes, device files, etc.
                    # These return False for both is_file() and is_dir()
                    else:
                        # Check if it's a symlink (even if broken)
                        if item.is_symlink():
                            # Has symlink, so not empty
                            has_non_empty_content = True
                            break
                        # Check if item exists (catches other special files)
                        # Use os.path.lexists() which returns True even for
                        # broken symlinks, and stat() to catch other special files
                        try:
                            # Try to stat the item - if it succeeds, it's a real
                            # item (file, dir, socket, pipe, device, etc.)
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
        except (OSError, PermissionError):
            # Skip directories we can't read
            pass

    return empty_folders


@router.post("/api/v1/cleanup/empty-folders")
async def cleanup_empty_folders(dry_run: bool = True, batch_size: int = 100):
    """
    Recursively find and delete all empty folders in the target directory.

    This endpoint:
    - Scans the target directory recursively
    - Identifies all empty folders (folders with no files or subdirectories)
    - Deletes empty folders (or shows what would be deleted in dry run mode)
    - Processes folders from deepest to shallowest to handle nested empty folders
    - Supports batch processing for re-entrant operations

    Args:
        dry_run: If True, only show what would be deleted (default: True)
        batch_size: Maximum number of empty folders to delete per request (default: 100).
                   Only counts folders actually deleted, not skipped folders. This makes the
                   operation re-entrant - subsequent requests will continue from where
                   the previous request stopped.

    Returns:
        dict: Cleanup results including folders found, removed, and errors
    """
    start_time = time.time()
    target_dir = get_target_directory()

    # Validate batch_size parameter
    if batch_size <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"batch_size must be a positive integer, got {batch_size}",
        )

    try:
        target_path = Path(target_dir).resolve()
        validate_directory(target_path, target_dir, "scan")
    except Exception as e:
        empty_folders_errors_total.labels(
            target_directory=target_dir, error_type="validation_error"
        ).inc()
        raise HTTPException(
            status_code=400, detail=f"Invalid target directory: {str(e)}"
        )

    try:
        # Find all empty folders
        empty_folders = find_empty_folders(target_path)

        logger.info(
            f"Empty folder scan completed: Found {len(empty_folders)} empty folders in {target_path}"
        )
        if empty_folders:
            logger.info(
                f"Empty folders found: {', '.join([str(f.relative_to(target_path)) for f in empty_folders[:10]])}{'...' if len(empty_folders) > 10 else ''}"
            )

        removed_folders = []
        errors = []
        processed_count = 0
        batch_limit_hit = False

        # Process empty folders for removal (already sorted deepest first)
        for folder_path in empty_folders:
            # CRITICAL: Defense in depth - never delete the target directory itself
            # This is a safety guard even though find_empty_folders excludes it
            if folder_path.resolve() == target_path.resolve():
                logger.warning(
                    f"Attempted to delete target directory itself: {folder_path}. "
                    f"This should never happen, but skipping to prevent data loss."
                )
                continue

            # Check if we've reached the batch limit
            if processed_count >= batch_size:
                batch_limit_hit = True
                logger.info(
                    f"Batch limit reached ({batch_size} folders processed), "
                    f"stopping processing. {len(empty_folders) - processed_count} folders remaining."
                )
                break

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
                    processed_count += 1
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
                    # Still count as processed even if it failed
                    processed_count += 1
                except Exception as e:
                    error_msg = f"Failed to remove {folder_path}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    empty_folders_errors_total.labels(
                        target_directory=target_dir,
                        error_type="folder_removal_error",
                    ).inc()
                    # Still count as processed even if it failed
                    processed_count += 1
            else:
                logger.info(
                    f"DRY RUN: Would remove empty folder: {folder_path.relative_to(target_path)}"
                )
                processed_count += 1

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
            "remaining_folders": len(empty_folders) - processed_count,
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
