"""Migrate non-movie folders endpoints."""

import asyncio
import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Set

from fastapi import APIRouter, HTTPException

from ..config import (
    DEFAULT_MOVIE_EXTENSIONS,
    get_migrated_movies_directory,
    get_target_directory,
)
from ..helpers import validate_directory
from ..metrics import (
    migrate_batch_operations_total,
    migrate_errors_total,
    migrate_folders_found_total,
    migrate_folders_moved_total,
    migrate_folders_skipped_total,
    migrate_operation_duration,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Thread pool executor for running blocking I/O operations
# This prevents blocking the async event loop during long-running scans
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="migrate")


def is_movie_file(file_path: Path, movie_extensions: Set[str]) -> bool:
    """
    Check if a file is a movie file based on its extension.

    Args:
        file_path: Path to the file to check
        movie_extensions: Set of movie file extensions (lowercase, with dot)

    Returns:
        True if the file is a movie file, False otherwise
    """
    return file_path.suffix.lower() in movie_extensions


def folder_contains_movie_files(
    folder_path: Path, movie_extensions: Set[str]
) -> bool:
    """
    Check if a folder (recursively) contains any movie files.

    Args:
        folder_path: Path to the folder to check
        movie_extensions: Set of movie file extensions (lowercase, with dot)

    Returns:
        True if the folder contains at least one movie file, False otherwise
    """
    try:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = Path(root) / file
                if is_movie_file(file_path, movie_extensions):
                    return True
    except (OSError, PermissionError):
        # If we can't read the folder, assume it might have movie files
        # to be safe (don't migrate folders we can't read)
        return True
    return False


def find_folders_without_movies(
    directory_path: Path,
    max_folders: int = None,
    movie_extensions: Set[str] = None,
    exclude_path: Path = None,
) -> List[Path]:
    """
    Recursively find folders that contain files but no movie files.

    This function scans the target directory and identifies folders that:
    - Contain at least one file (not empty)
    - Do not contain any movie files (based on extension list)

    Args:
        directory_path: Path to the directory to scan
        max_folders: Maximum number of folders to find. If None,
                    scans the entire directory. If provided (> 0), stops
                    scanning once this many folders are found.
        movie_extensions: Set of movie file extensions to check for.
                         If None, uses DEFAULT_MOVIE_EXTENSIONS.
        exclude_path: Optional path to exclude from scan results (e.g., migrated
                     directory if it's inside the target directory).

    Returns:
        List of Path objects for folders without movie files
    """
    if movie_extensions is None:
        movie_extensions = {ext.lower() for ext in DEFAULT_MOVIE_EXTENSIONS}

    folders_without_movies = []
    resolved_target = directory_path.resolve()
    resolved_exclude = exclude_path.resolve() if exclude_path else None

    logger.info(
        f"Starting directory walk for folders without movies: {directory_path} "
        f"(max_folders={max_folders}, exclude_path={exclude_path})"
    )

    directories_scanned = 0
    try:
        # Walk through directory from top to bottom
        for root, dirs, files in os.walk(directory_path):
            directories_scanned += 1
            # Log progress every 1000 directories scanned
            if directories_scanned % 1000 == 0:
                logger.info(
                    f"Scanning progress: {directories_scanned} directories scanned, "
                    f"{len(folders_without_movies)} folders without movies found so far"
                )

            # Stop scanning if we've reached the maximum number of folders
            if (
                max_folders is not None
                and len(folders_without_movies) >= max_folders
            ):
                logger.info(
                    f"Reached max_folders limit ({max_folders}): stopping scan "
                    f"after scanning {directories_scanned} directories"
                )
                break

            root_path = Path(root).resolve()

            # CRITICAL: Never include the target directory itself in results
            # This prevents accidental migration of the configured root directory
            if root_path == resolved_target:
                continue

            # CRITICAL: Never include the excluded path (e.g., migrated directory)
            # if it's inside the target directory. This prevents attempting to
            # move the migrated directory into itself.
            if resolved_exclude and (
                root_path == resolved_exclude
                or root_path.is_relative_to(resolved_exclude)
            ):
                continue

            # Check if directory contains files (not empty)
            try:
                items = list(root_path.iterdir())
                if len(items) == 0:
                    # Empty folder - skip (empty folder cleanup handles this)
                    continue

                # Check if folder contains any files (not just subdirectories)
                # We only want to migrate folders that actually contain files
                has_files = any(item.is_file() for item in items)
                if not has_files:
                    # Folder only contains subdirectories, skip it
                    # (subdirectories will be checked in their own iteration)
                    continue

                # Check if folder contains any movie files
                if not folder_contains_movie_files(
                    root_path, movie_extensions
                ):
                    # Folder has files but no movie files - add to list
                    folders_without_movies.append(root_path)
                    # Stop scanning if we've reached the maximum number of folders
                    if (
                        max_folders is not None
                        and len(folders_without_movies) >= max_folders
                    ):
                        break
            except (OSError, PermissionError):
                # Skip directories we can't read
                pass
    except KeyboardInterrupt:
        # Allow graceful interruption
        raise
    except Exception as e:
        # Log unexpected errors during scanning
        logger.error(
            f"Unexpected error during folder scan after scanning "
            f"{directories_scanned} directories: {str(e)}"
        )
        raise

    logger.info(
        f"Directory walk completed: scanned {directories_scanned} directories, "
        f"found {len(folders_without_movies)} folders without movie files"
    )

    return folders_without_movies


@router.post("/api/v1/migrate/non-movie-folders")
async def migrate_non_movie_folders(
    dry_run: bool = True, batch_size: int = 100
):
    """
    Find and move folders that contain files but no movie files to migrated directory.

    This endpoint:
    - Scans the target directory recursively
    - Identifies folders that contain files but no movie files (.avi, .mkv, .mp4, etc)
    - Moves those folders to the migrated movies directory
    - Supports batch processing for re-entrant operations

    Args:
        dry_run: If True, only show what would be moved (default: True)
        batch_size: Maximum number of folders to scan and process per request
                   (default: 100). If provided, scanning stops once this many folders
                   are found. If not provided or 0, performs a full scan
                   of the entire directory. Only counts folders actually moved,
                   not skipped folders. This makes the operation re-entrant -
                   subsequent requests will continue from where the previous request
                   stopped.

    Returns:
        dict: Migration results including folders found, moved, skipped, and errors
    """
    start_time = time.time()
    target_dir = get_target_directory()
    migrated_dir = get_migrated_movies_directory()

    logger.info(
        f"Non-movie folder migration request: dry_run={dry_run}, "
        f"batch_size={batch_size}, target_directory={target_dir}, "
        f"migrated_directory={migrated_dir}"
    )

    # Validate batch_size parameter
    # batch_size of 0 means full scan (no limit), negative values are invalid
    if batch_size < 0:
        raise HTTPException(
            status_code=400,
            detail=f"batch_size must be a non-negative integer, got {batch_size}",
        )

    try:
        target_path = Path(target_dir).resolve()
        logger.info(f"Validating target directory: {target_path}")
        validate_directory(target_path, target_dir, "migrate")
        logger.info(f"Target directory validation successful: {target_path}")

        migrated_path = Path(migrated_dir).resolve()
        logger.info(f"Validating migrated directory: {migrated_path}")

        # Ensure migrated directory exists (create if it doesn't)
        try:
            migrated_path.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError):
            # If directory creation fails, validate_directory will handle the 404
            pass

        # Validate migrated directory (after attempting to create it)
        validate_directory(migrated_path, migrated_dir, "migrate")
        logger.info(
            f"Migrated directory validation successful: {migrated_path}"
        )
    except HTTPException:
        # validate_directory already recorded the error in the correct metric
        # (migrate_errors_total), so we just re-raise
        raise
    except Exception as e:
        # For any other unexpected exceptions, record in migrate_errors_total
        migrate_errors_total.labels(
            target_directory=target_dir,
            migrated_directory=migrated_dir,
            error_type="validation_error",
        ).inc()
        raise HTTPException(
            status_code=400, detail=f"Invalid directory: {str(e)}"
        )

    try:
        # Find folders without movie files, with optional batch_size limit on scanning
        # If batch_size > 0, only scan until we find that many folders
        # If batch_size is 0 or None, scan the entire directory
        max_folders_to_scan = batch_size if batch_size > 0 else None
        logger.info(
            f"Starting folder scan in {target_path} "
            f"(max_folders={max_folders_to_scan})"
        )
        # Run the blocking scan in a thread pool to prevent worker timeout
        # This allows the async event loop to handle other requests while scanning
        # The scan can take a long time on large directories, so running it in a
        # separate thread prevents blocking the worker and causing timeouts
        # Exclude migrated_path if it's inside target_path to prevent moving it into itself
        exclude_path = (
            migrated_path
            if migrated_path.resolve().is_relative_to(target_path.resolve())
            else None
        )
        loop = asyncio.get_running_loop()
        folders_to_migrate = await loop.run_in_executor(
            _executor,
            find_folders_without_movies,
            target_path,
            max_folders_to_scan,
            None,  # Use default movie extensions
            exclude_path,  # Exclude migrated directory if inside target
        )

        logger.info(
            f"Folder scan completed: Found {len(folders_to_migrate)} folders "
            f"without movie files in {target_path}"
        )
        if folders_to_migrate:
            logger.info(
                f"Folders to migrate: {', '.join([str(f.relative_to(target_path)) for f in folders_to_migrate[:10]])}{'...' if len(folders_to_migrate) > 10 else ''}"
            )

        moved_folders = []
        skipped_folders = []
        errors = []
        # batch_limit_reached is True if:
        # - batch_size > 0 (a limit was set)
        # - We found exactly batch_size folders (scan stopped at limit)
        # This indicates there may be more folders remaining
        batch_limit_hit = (
            batch_size > 0 and len(folders_to_migrate) >= batch_size
        )

        logger.info(
            f"Processing {len(folders_to_migrate)} folders for migration "
            f"(dry_run={dry_run}, batch_limit_reached={batch_limit_hit})"
        )

        # Process folders for migration
        for folder_path in folders_to_migrate:
            # CRITICAL: Defense in depth - never migrate the target directory itself
            # This is a safety guard even though find_folders_without_movies excludes it
            if folder_path.resolve() == target_path.resolve():
                logger.warning(
                    f"Attempted to migrate target directory itself: {folder_path}. "
                    f"This should never happen, but skipping to prevent data loss."
                )
                continue

            # Preserve relative path structure to avoid collisions when folders
            # with the same name exist at different paths (e.g., /target/a/common
            # and /target/b/common). Use relative path from target directory.
            folder_relative = folder_path.relative_to(target_path)
            target_migrated_path = migrated_path / folder_relative

            if not dry_run:
                try:
                    # Check if destination already exists
                    if target_migrated_path.exists():
                        logger.info(
                            f"Skipping folder (destination exists): {folder_relative} "
                            f"-> {target_migrated_path}"
                        )
                        skipped_folders.append(
                            str(folder_path.relative_to(target_path))
                        )
                        migrate_folders_skipped_total.labels(
                            target_directory=target_dir,
                            migrated_directory=migrated_dir,
                            dry_run=str(dry_run).lower(),
                        ).inc()
                        continue

                    # Check if source still exists (might have been moved already)
                    if not folder_path.exists():
                        logger.info(
                            f"Skipping folder (already moved): {folder_path.relative_to(target_path)}"
                        )
                        continue

                    logger.info(
                        f"Starting to move folder: {folder_path.relative_to(target_path)} "
                        f"-> {target_migrated_path}"
                    )
                    # Use shutil.move for cross-device moves if needed
                    shutil.move(str(folder_path), str(target_migrated_path))
                    moved_folders.append(
                        str(folder_path.relative_to(target_path))
                    )
                    logger.info(
                        f"Successfully finished moving folder: {folder_path.relative_to(target_path)}"
                    )
                    migrate_folders_moved_total.labels(
                        target_directory=target_dir,
                        migrated_directory=migrated_dir,
                        dry_run=str(dry_run).lower(),
                    ).inc()
                except OSError as e:
                    # Folder might not exist anymore (moved by another process)
                    if not folder_path.exists():
                        logger.info(
                            f"Folder no longer exists (moved during processing): {folder_path.relative_to(target_path)}"
                        )
                        continue
                    error_msg = f"Failed to move {folder_path}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    migrate_errors_total.labels(
                        target_directory=target_dir,
                        migrated_directory=migrated_dir,
                        error_type="folder_move_error",
                    ).inc()
                    # Don't count errors toward batch limit - only successful
                    # moves count. This ensures re-entrancy: persistent errors
                    # won't block progress on other folders.
                except Exception as e:
                    error_msg = f"Failed to move {folder_path}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    migrate_errors_total.labels(
                        target_directory=target_dir,
                        migrated_directory=migrated_dir,
                        error_type="folder_move_error",
                    ).inc()
                    # Don't count errors toward batch limit - only successful
                    # moves count. This ensures re-entrancy: persistent errors
                    # won't block progress on other folders.
            else:
                logger.info(
                    f"DRY RUN: Would move folder: {folder_path.relative_to(target_path)} "
                    f"-> {target_migrated_path}"
                )

        # Record metrics for found folders
        migrate_folders_found_total.labels(
            target_directory=target_dir, dry_run=str(dry_run).lower()
        ).inc(len(folders_to_migrate))

        # Record batch operation metric
        migrate_batch_operations_total.labels(
            target_directory=target_dir,
            migrated_directory=migrated_dir,
            batch_size=str(batch_size),
            dry_run=str(dry_run).lower(),
        ).inc()

        # Record operation duration
        operation_duration = time.time() - start_time
        migrate_operation_duration.labels(
            operation_type="migrate_non_movie_folders",
            target_directory=target_dir,
            migrated_directory=migrated_dir,
        ).observe(operation_duration)

        logger.info(
            f"Non-movie folder migration completed: found={len(folders_to_migrate)}, "
            f"moved={len(moved_folders)}, skipped={len(skipped_folders)}, "
            f"errors={len(errors)}, duration={operation_duration:.2f}s, "
            f"batch_limit_reached={batch_limit_hit}"
        )

        return {
            "target_directory": str(target_path),
            "migrated_directory": str(migrated_path),
            "dry_run": dry_run,
            "batch_size": batch_size,
            "folders_found": len(folders_to_migrate),
            "folders_moved": len(moved_folders),
            "folders_skipped": len(skipped_folders),
            "errors": len(errors),
            "batch_limit_reached": batch_limit_hit,
            "remaining_folders": (
                # If batch limit was hit, we don't know how many remain
                # without a full scan, so return 0 (unknown)
                0
            ),
            "folders_to_migrate": [
                str(f.relative_to(target_path)) for f in folders_to_migrate
            ],
            "moved_folders": moved_folders,
            "skipped_folders": skipped_folders,
            "error_details": errors,
        }

    except Exception as e:
        operation_duration = time.time() - start_time
        logger.error(
            f"Error during non-movie folder migration after {operation_duration:.2f}s: {str(e)}",
            exc_info=True,
        )
        migrate_errors_total.labels(
            target_directory=target_dir,
            migrated_directory=migrated_dir,
            error_type="operation_error",
        ).inc()
        raise HTTPException(
            status_code=500,
            detail=f"Error during non-movie folder migration: {str(e)}",
        )
