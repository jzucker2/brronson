"""Subtitle sync endpoints: move subtitle files from source to target."""

import errno
import logging
import os
import shutil
import time
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException

from ..config import (
    DEFAULT_SUBTITLE_EXTENSIONS,
    get_migrated_movies_directory,
    get_salvaged_movies_directory,
    get_target_directory,
)
from ..helpers import is_subtitle_file, validate_directory
from ..metrics import (
    sync_subtitles_batch_operations_total,
    sync_subtitles_errors_total,
    sync_subtitles_files_moved_total,
    sync_subtitles_files_skipped_total,
    sync_subtitles_operation_duration,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _collect_subtitle_files(
    movie_folder: Path,
    subtitle_extensions: List[str],
) -> List[Path]:
    """
    Collect all subtitle files under a movie folder (recursive), sorted by path.

    Args:
        movie_folder: Path to the movie folder (first-level under source).
        subtitle_extensions: List of subtitle file extensions (with leading dot).

    Returns:
        List of Path objects for subtitle files, sorted by path for deterministic
        order (re-entrant batch_size behavior).
    """
    files = []
    try:
        for root, _dirs, filenames in os.walk(movie_folder):
            for name in filenames:
                p = Path(root) / name
                if is_subtitle_file(p, subtitle_extensions):
                    files.append(p)
    except (OSError, PermissionError):
        pass
    return sorted(files, key=lambda p: str(p))


@router.post("/api/v1/sync/subtitles-to-target")
async def sync_subtitles_to_target(
    source: Literal["salvaged", "migrated"],
    dry_run: bool = True,
    batch_size: int = 100,
    subtitle_extensions: Optional[List[str]] = None,
):
    """
    Move subtitle files from source (salvaged or migrated) to target.

    Scans the chosen source movies directory and moves subtitle files into the
    target directory under each movie folder, preserving the same hierarchy
    (equivalent path: source/Movie/Subs/en.srt -> target/Movie/Subs/en.srt).
    Only moves when the destination file does not already exist. Creates
    directories as needed. Skipped files do not count toward batch_size.

    Args:
        source: Source of subtitles: "salvaged" or "migrated".
        dry_run: If True, only report what would be moved (default: True).
        batch_size: Maximum number of subtitle files to move per request
                    (default: 100). Only actually moved files count.
        subtitle_extensions: List of subtitle file extensions (with leading dot).
                             If None, uses DEFAULT_SUBTITLE_EXTENSIONS.

    Returns:
        dict: Sync results including source, target, counts, and errors.
    """
    start_time = time.time()

    if batch_size <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"batch_size must be a positive integer, got {batch_size}",
        )

    if source == "salvaged":
        source_dir = get_salvaged_movies_directory()
    else:
        source_dir = get_migrated_movies_directory()

    target_dir = get_target_directory()

    if subtitle_extensions is None:
        subtitle_extensions = DEFAULT_SUBTITLE_EXTENSIONS

    try:
        source_path = Path(source_dir).resolve()
        target_path = Path(target_dir).resolve()

        validate_directory(
            source_path,
            source_dir,
            operation_type="subtitle_sync",
            subtitle_sync_source_directory=source_dir,
            subtitle_sync_target_directory=target_dir,
        )

        # Ensure target exists (create if needed), then validate
        try:
            target_path.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError):
            pass
        validate_directory(
            target_path,
            target_dir,
            operation_type="subtitle_sync",
            subtitle_sync_source_directory=source_dir,
            subtitle_sync_target_directory=target_dir,
        )

        logger.info(
            f"Subtitle sync: source={source}, scanning {source_path} -> {target_path}"
        )

        # First-level subdirs (movie folders) in source
        movie_folders = []
        try:
            for item in source_path.iterdir():
                if item.is_dir():
                    movie_folders.append(item)
        except OSError as e:
            if e.errno == errno.ESTALE:
                sync_subtitles_errors_total.labels(
                    source_directory=source_dir,
                    target_directory=target_dir,
                    error_type="stale_file_handle",
                ).inc()
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Stale file handle error accessing source directory "
                        f"'{source_dir}'. Check mount status and try again."
                    ),
                )
            sync_subtitles_errors_total.labels(
                source_directory=source_dir,
                target_directory=target_dir,
                error_type="directory_read_error",
            ).inc()
            raise HTTPException(
                status_code=500,
                detail=f"Error reading source directory: {str(e)}",
            )

        movie_folders.sort(key=lambda p: p.name)

        files_moved = 0
        files_skipped = 0
        errors = []
        batch_limit_hit = False

        for movie_folder in movie_folders:
            if files_moved >= batch_size:
                batch_limit_hit = True
                break

            subtitle_files = _collect_subtitle_files(
                movie_folder, subtitle_extensions
            )
            rel_base = movie_folder.name
            target_movie_base = target_path / rel_base

            for src_file in subtitle_files:
                if files_moved >= batch_size:
                    batch_limit_hit = True
                    break

                try:
                    rel = src_file.relative_to(movie_folder)
                except ValueError:
                    continue
                dest_file = target_movie_base / rel

                if dest_file.exists():
                    files_skipped += 1
                    sync_subtitles_files_skipped_total.labels(
                        source_directory=source_dir,
                        target_directory=target_dir,
                        dry_run=str(dry_run).lower(),
                    ).inc()
                    logger.debug(
                        f"Skipping {src_file.name} - target exists: {dest_file}"
                    )
                    continue

                if dry_run:
                    files_moved += 1
                    sync_subtitles_files_moved_total.labels(
                        source_directory=source_dir,
                        target_directory=target_dir,
                        dry_run=str(dry_run).lower(),
                    ).inc()
                    logger.info(
                        f"DRY RUN: Would move {src_file} -> {dest_file}"
                    )
                    continue

                try:
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src_file), str(dest_file))
                    files_moved += 1
                    sync_subtitles_files_moved_total.labels(
                        source_directory=source_dir,
                        target_directory=target_dir,
                        dry_run=str(dry_run).lower(),
                    ).inc()
                    logger.debug(f"Moved {src_file} -> {dest_file}")
                except Exception as e:
                    error_msg = f"Failed to move {src_file}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    sync_subtitles_errors_total.labels(
                        source_directory=source_dir,
                        target_directory=target_dir,
                        error_type="move_error",
                    ).inc()

        operation_duration = time.time() - start_time
        sync_subtitles_operation_duration.labels(
            operation_type="sync_subtitles_to_target",
            source_directory=source_dir,
            target_directory=target_dir,
        ).observe(operation_duration)

        sync_subtitles_batch_operations_total.labels(
            source_directory=source_dir,
            target_directory=target_dir,
            batch_size=str(batch_size),
            dry_run=str(dry_run).lower(),
        ).inc()

        return {
            "source": source,
            "source_directory": str(source_path),
            "target_directory": str(target_path),
            "dry_run": dry_run,
            "batch_size": batch_size,
            "subtitle_extensions": subtitle_extensions,
            "subtitle_files_moved": files_moved,
            "subtitle_files_skipped": files_skipped,
            "batch_limit_reached": batch_limit_hit,
            "errors": len(errors),
            "error_details": errors,
        }

    except HTTPException:
        raise
    except Exception as e:
        sync_subtitles_errors_total.labels(
            source_directory=source_dir,
            target_directory=target_dir,
            error_type="operation_error",
        ).inc()
        raise HTTPException(
            status_code=500,
            detail=f"Error during subtitle sync: {str(e)}",
        )
