"""File move endpoints."""

import logging
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import get_cleanup_directory, get_target_directory
from ..helpers import get_subdirectories, validate_directory
from ..metrics import (
    move_batch_operations_total,
    move_directories_moved,
    move_duplicates_found,
    move_errors_total,
    move_files_found_total,
    move_files_moved_total,
    move_operation_duration,
)
from .cleanup import perform_cleanup_internal

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/v1/move/non-duplicates")
async def move_non_duplicate_files(
    dry_run: bool = True, batch_size: int = 1, skip_cleanup: bool = False
):
    """
    Move non-duplicate files from CLEANUP_DIRECTORY to TARGET_DIRECTORY.

    This function identifies subdirectories that exist in the cleanup directory
    but not in the target directory, and moves them to the target directory.

    By default, this function will run cleanup files before moving to remove
    unwanted files from the directories being moved.

    Args:
        dry_run: If True, only show what would be moved (default: True)
        batch_size: Number of files to move per request (default: 1)
        skip_cleanup: If True, skip the cleanup files step before moving (default: False)
    """
    start_time = time.time()

    cleanup_dir = get_cleanup_directory()
    target_dir = get_target_directory()

    try:
        cleanup_path = Path(cleanup_dir).resolve()
        target_path = Path(target_dir).resolve()

        # Run cleanup files by default unless skip_cleanup is True
        cleanup_results = None
        cleanup_failed = False
        if not skip_cleanup:
            logger.info("Running cleanup files before move operation")
            try:
                # Call the internal cleanup helper
                cleanup_results = perform_cleanup_internal(dry_run=dry_run)
                logger.info(
                    f"Cleanup completed: {cleanup_results['files_removed']} files removed"
                )
            except HTTPException as e:
                logger.warning(f"Cleanup files step failed: {str(e)}")
                # Continue with move operation even if cleanup fails
                cleanup_results = {"error": str(e)}
                cleanup_failed = True
            except Exception as e:
                logger.warning(f"Cleanup files step failed: {str(e)}")
                # Continue with move operation even if cleanup fails
                cleanup_results = {"error": str(e)}
                cleanup_failed = True

        # Validate both directories (after cleanup attempt)
        # Skip cleanup directory validation if cleanup failed
        if not cleanup_failed:
            validate_directory(cleanup_path, cleanup_dir, "comparison")
        validate_directory(target_path, target_dir, "comparison")

        # Get subdirectories from both directories (reusing existing functionality)
        cleanup_subdirs = get_subdirectories(cleanup_path, "move", dry_run)
        target_subdirs = get_subdirectories(target_path, "move", dry_run)

        logger.info(
            f"Move operation: Found {len(cleanup_subdirs)} subdirectories in cleanup, {len(target_subdirs)} in target"
        )

        # Find non-duplicates (subdirectories that exist in cleanup but not in target)
        cleanup_set = set(cleanup_subdirs)
        target_set = set(target_subdirs)
        non_duplicates = sorted(
            list(cleanup_set - target_set)
        )  # Sort for deterministic order
        duplicates = list(cleanup_set.intersection(target_set))

        logger.info(
            f"Move analysis: {len(duplicates)} duplicates, {len(non_duplicates)} non-duplicates to move"
        )
        if non_duplicates:
            logger.info(f"Directories to move: {', '.join(non_duplicates)}")

        # Record metrics for files found
        move_files_found_total.labels(
            cleanup_directory=cleanup_dir,
            target_directory=target_dir,
            dry_run=str(dry_run).lower(),
        ).inc(len(non_duplicates))

        # Record gauge metrics for duplicates found and directories moved
        move_duplicates_found.labels(
            cleanup_directory=cleanup_dir,
            target_directory=target_dir,
            dry_run=str(dry_run).lower(),
        ).set(len(duplicates))

        moved_files = []
        errors = []
        processed_count = 0

        # Process non-duplicate subdirectories for moving in batches
        for subdir_name in non_duplicates:
            # Check if we've reached the batch limit
            if processed_count >= batch_size:
                logger.info(
                    f"Batch limit reached ({batch_size}), stopping processing. {len(non_duplicates) - processed_count} files remaining."
                )
                break

            source_path = cleanup_path / subdir_name
            target_path_subdir = target_path / subdir_name

            if not dry_run:
                try:
                    logger.info(
                        f"Starting to move directory: {subdir_name} from {source_path} to {target_path_subdir}"
                    )
                    # Use shutil.move for cross-device moves if needed
                    shutil.move(str(source_path), str(target_path_subdir))
                    moved_files.append(subdir_name)
                    logger.info(
                        f"Successfully finished moving directory: {subdir_name}"
                    )
                    move_files_moved_total.labels(
                        cleanup_directory=cleanup_dir,
                        target_directory=target_dir,
                        dry_run=str(dry_run).lower(),
                    ).inc()
                except Exception as e:
                    error_msg = f"Failed to move {subdir_name}: {str(e)}"
                    logger.error(
                        f"Failed to move directory {subdir_name}: {str(e)}"
                    )
                    errors.append(error_msg)
                    move_errors_total.labels(
                        cleanup_directory=cleanup_dir,
                        target_directory=target_dir,
                        error_type="file_move_error",
                    ).inc()
            else:
                # In dry run mode, just add to moved_files for reporting
                logger.info(
                    f"DRY RUN: Would move directory: {subdir_name} from {source_path} to {target_path_subdir}"
                )
                moved_files.append(subdir_name)

            processed_count += 1

        # Record gauge metric for directories moved
        move_directories_moved.labels(
            cleanup_directory=cleanup_dir,
            target_directory=target_dir,
            dry_run=str(dry_run).lower(),
        ).set(len(moved_files))

        # Record batch operation metric
        move_batch_operations_total.labels(
            cleanup_directory=cleanup_dir,
            target_directory=target_dir,
            batch_size=str(batch_size),
            dry_run=str(dry_run).lower(),
        ).inc()

        # Record operation duration
        operation_duration = time.time() - start_time
        move_operation_duration.labels(
            operation_type="move",
            cleanup_directory=cleanup_dir,
            target_directory=target_dir,
        ).observe(operation_duration)

        response = {
            "cleanup_directory": str(cleanup_path),
            "target_directory": str(target_path),
            "dry_run": dry_run,
            "batch_size": batch_size,
            "skip_cleanup": skip_cleanup,
            "non_duplicates_found": len(non_duplicates),
            "files_moved": len(moved_files),
            "errors": len(errors),
            "non_duplicate_subdirectories": non_duplicates,
            "moved_subdirectories": moved_files,
            "error_details": errors,
            "remaining_files": len(non_duplicates) - processed_count,
        }

        # Add cleanup results to response if cleanup was performed
        if cleanup_results is not None:
            response["cleanup_results"] = cleanup_results

        return response

    except HTTPException:
        # Re-raise HTTPExceptions (like 404 for missing directories) as-is
        raise
    except Exception as e:
        move_errors_total.labels(
            cleanup_directory=cleanup_dir,
            target_directory=target_dir,
            error_type="operation_error",
        ).inc()
        raise HTTPException(
            status_code=500,
            detail=f"Error during file move operation: {str(e)}",
        )
