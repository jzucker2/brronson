"""Cleanup and scan endpoints for unwanted files."""

import logging
import time
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Body, HTTPException

from ..config import DEFAULT_UNWANTED_PATTERNS, get_cleanup_directory
from ..helpers import find_unwanted_files, validate_directory
from ..metrics import (
    cleanup_current_files,
    cleanup_errors_total,
    cleanup_files_found_total,
    cleanup_files_removed_total,
    cleanup_operation_duration,
    scan_current_files,
    scan_errors_total,
    scan_files_found_total,
    scan_operation_duration,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def perform_cleanup_internal(
    dry_run: bool = True, patterns: Optional[List[str]] = None
):
    """
    Internal helper function to perform cleanup operations.
    This can be called from other functions without the Body parameter issues.

    Args:
        dry_run: If True, only show what would be deleted (default: True)
        patterns: List of regex patterns to match unwanted files

    Returns:
        dict: Cleanup results
    """
    start_time = time.time()
    cleanup_dir = get_cleanup_directory()

    if patterns is None:
        patterns = DEFAULT_UNWANTED_PATTERNS

    # Use the configured cleanup directory
    try:
        directory_path = Path(cleanup_dir).resolve()
        validate_directory(directory_path, cleanup_dir, "cleanup")
    except Exception as e:  # noqa: E501
        cleanup_errors_total.labels(
            directory=cleanup_dir, error_type="validation_error"
        ).inc()
        msg = "Invalid cleanup directory: " f"{str(e)}"
        raise HTTPException(status_code=400, detail=msg)

    try:
        # Use shared helper to find unwanted files
        found_files, file_sizes, pattern_matches = find_unwanted_files(
            directory_path, patterns, "cleanup"
        )

        logger.info(
            f"Cleanup scan completed: Found {len(found_files)} unwanted files in {directory_path}"
        )
        if found_files:
            logger.info(
                f"Files found: {', '.join([Path(f).name for f in found_files[:10]])}{'...' if len(found_files) > 10 else ''}"
            )

        removed_files = []
        errors = []

        # Process found files for removal
        for file_path_str in found_files:
            file_path = Path(file_path_str)
            pattern = pattern_matches[file_path_str]

            if not dry_run:
                try:
                    logger.info(
                        f"Starting to remove file: {file_path.name} from {file_path}"
                    )
                    file_path.unlink()
                    removed_files.append(file_path_str)
                    logger.info(
                        f"Successfully finished removing file: {file_path.name}"
                    )
                    cleanup_files_removed_total.labels(
                        directory=cleanup_dir,
                        pattern=pattern,
                        dry_run=str(dry_run).lower(),
                    ).inc()
                    # Note: Current files gauge will be updated after all removals
                except Exception as e:
                    error_msg = (
                        f"Failed to remove {file_path}: {str(e)}"  # noqa: E501
                    )
                    logger.error(
                        f"Failed to remove file {file_path.name}: {str(e)}"
                    )
                    errors.append(error_msg)
                    cleanup_errors_total.labels(
                        directory=cleanup_dir, error_type="file_removal_error"
                    ).inc()
            else:
                logger.info(
                    f"DRY RUN: Would remove file: {file_path.name} from {file_path}"
                )

        # Record metrics for found files or zero out if none found
        if pattern_matches:
            # Count files found for each pattern
            pattern_counts = {}
            for file_path, pattern in pattern_matches.items():
                pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

            # Record metrics for each pattern
            for pattern in patterns:
                count = pattern_counts.get(pattern, 0)
                cleanup_files_found_total.labels(
                    directory=cleanup_dir,
                    pattern=pattern,
                    dry_run=str(dry_run).lower(),
                ).inc(count)
                # Set current files gauge
                cleanup_current_files.labels(
                    directory=cleanup_dir,
                    pattern=pattern,
                    dry_run=str(dry_run).lower(),
                ).set(count)
        else:
            # Zero out metrics for each pattern when no files are found
            for pattern in patterns:
                cleanup_files_found_total.labels(
                    directory=cleanup_dir,
                    pattern=pattern,
                    dry_run=str(dry_run).lower(),
                ).inc(0)
                # Set current files gauge to 0
                cleanup_current_files.labels(
                    directory=cleanup_dir,
                    pattern=pattern,
                    dry_run=str(dry_run).lower(),
                ).set(0)

        # Update current files gauge after removal
        if not dry_run and removed_files:
            # Set current files gauge to 0 for patterns that had files removed
            removed_patterns = set()
            for file_path_str in removed_files:
                pattern = pattern_matches[file_path_str]
                removed_patterns.add(pattern)

            for pattern in removed_patterns:
                cleanup_current_files.labels(
                    directory=cleanup_dir,
                    pattern=pattern,
                    dry_run=str(dry_run).lower(),
                ).set(0)

        # Record operation duration
        operation_duration = time.time() - start_time
        cleanup_operation_duration.labels(
            operation_type="cleanup", directory=cleanup_dir
        ).observe(operation_duration)

        return {
            "directory": str(directory_path),
            "dry_run": dry_run,
            "patterns_used": patterns,
            "files_found": len(found_files),
            "files_removed": len(removed_files),
            "errors": len(errors),
            "found_files": found_files,
            "removed_files": removed_files,
            "error_details": errors,
        }

    except Exception as e:
        cleanup_errors_total.labels(
            directory=cleanup_dir, error_type="operation_error"
        ).inc()
        raise HTTPException(
            status_code=500, detail=f"Error during cleanup: {str(e)}"
        )


@router.post("/api/v1/cleanup/files")
async def cleanup_unwanted_files(
    dry_run: bool = True, patterns: Optional[List[str]] = Body(None)
):
    """
    Recursively search the configured directory and remove unwanted files.

    Args:
        dry_run: If True, only show what would be deleted (default: True)
        patterns: List of regex patterns to match unwanted files
    """
    return perform_cleanup_internal(dry_run, patterns)


@router.get("/api/v1/cleanup/scan")
async def scan_for_unwanted_files(patterns: List[str] = None):
    """
    Scan the configured directory for unwanted files without removing them.

    Args:
        patterns: List of regex patterns to match unwanted files
    """
    start_time = time.time()

    if patterns is None:
        patterns = DEFAULT_UNWANTED_PATTERNS

    # Use the configured cleanup directory
    cleanup_dir = get_cleanup_directory()
    try:
        directory_path = Path(cleanup_dir).resolve()
        validate_directory(directory_path, cleanup_dir, "scan")
    except Exception as e:  # noqa: E501
        scan_errors_total.labels(
            directory=cleanup_dir, error_type="directory_error"
        ).inc()
        msg = "Invalid cleanup directory: " f"{str(e)}"
        raise HTTPException(status_code=400, detail=msg)

    try:
        # Use shared helper to find unwanted files
        found_files, file_sizes, pattern_matches = find_unwanted_files(
            directory_path, patterns, "scan"
        )

        logger.info(
            f"Scan completed: Found {len(found_files)} unwanted files in {directory_path}"
        )
        if found_files:
            logger.info(
                f"Files found: {', '.join([Path(f).name for f in found_files[:10]])}{'...' if len(found_files) > 10 else ''}"
            )

        total_size = sum(file_sizes.values())

        # Record metrics for found files or zero out if none found
        if pattern_matches:
            # Count files found for each pattern
            pattern_counts = {}
            for file_path, pattern in pattern_matches.items():
                pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

            # Record metrics for each pattern
            for pattern in patterns:
                count = pattern_counts.get(pattern, 0)
                scan_files_found_total.labels(
                    directory=cleanup_dir, pattern=pattern
                ).inc(count)
                # Set current files gauge
                scan_current_files.labels(
                    directory=cleanup_dir, pattern=pattern
                ).set(count)
        else:
            # Zero out metrics for each pattern when no files are found
            for pattern in patterns:
                scan_files_found_total.labels(
                    directory=cleanup_dir, pattern=pattern
                ).inc(0)
                # Set current files gauge to 0
                scan_current_files.labels(
                    directory=cleanup_dir, pattern=pattern
                ).set(0)

        # Record operation duration
        operation_duration = time.time() - start_time
        scan_operation_duration.labels(
            operation_type="scan", directory=cleanup_dir
        ).observe(operation_duration)

        return {
            "directory": str(directory_path),
            "patterns_used": patterns,
            "files_found": len(found_files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "found_files": found_files,
            "file_sizes": file_sizes,
        }

    except Exception as e:
        scan_errors_total.labels(
            directory=cleanup_dir, error_type="operation_error"
        ).inc()
        raise HTTPException(
            status_code=500, detail=f"Error during scan: {str(e)}"
        )
