"""Helper functions for the Brronson application."""

import os
import re
from pathlib import Path
from typing import List

from fastapi import HTTPException

from .config import (
    get_recycled_movies_directory,
    get_salvaged_movies_directory,
)
from .metrics import (
    cleanup_directory_size_bytes,
    cleanup_errors_total,
    comparison_errors_total,
    scan_directory_size_bytes,
    scan_errors_total,
    salvage_errors_total,
    subdirectories_found_total,
)


def validate_directory(
    directory_path: Path,
    cleanup_dir: str,
    operation_type: str = "scan",
) -> None:
    """
    Shared helper method to validate directory for cleanup/scan operations.

    Args:
        directory_path: Path to the directory to validate
        cleanup_dir: String representation of the cleanup directory for error messages  # noqa: E501
        operation_type: Type of operation ("scan", "cleanup", "comparison", or "salvage") for metrics

    Raises:
        HTTPException: If directory validation fails
    """
    if not directory_path.exists():
        if operation_type == "scan":
            scan_errors_total.labels(
                directory=cleanup_dir, error_type="directory_not_found"
            ).inc()
        elif operation_type == "cleanup":
            cleanup_errors_total.labels(
                directory=cleanup_dir, error_type="directory_not_found"
            ).inc()
        elif operation_type == "comparison":
            comparison_errors_total.labels(
                directory=cleanup_dir, error_type="directory_not_found"
            ).inc()
        elif operation_type == "salvage":
            # For salvage operations, we need to determine which directory failed
            # Use resolved path comparison to avoid substring false positives
            recycled_dir = get_recycled_movies_directory()
            salvaged_dir = get_salvaged_movies_directory()
            recycled_path_resolved = str(Path(recycled_dir).resolve())
            salvaged_path_resolved = str(Path(salvaged_dir).resolve())
            dir_str_resolved = str(directory_path.resolve())

            # Determine which directory this is using exact path comparison
            if (
                dir_str_resolved == recycled_path_resolved
                or dir_str_resolved.startswith(recycled_path_resolved + "/")
            ):
                salvage_errors_total.labels(
                    recycled_directory=recycled_dir,
                    salvaged_directory=salvaged_dir,
                    error_type="recycled_directory_not_found",
                ).inc()
            elif (
                dir_str_resolved == salvaged_path_resolved
                or dir_str_resolved.startswith(salvaged_path_resolved + "/")
            ):
                salvage_errors_total.labels(
                    recycled_directory=recycled_dir,
                    salvaged_directory=salvaged_dir,
                    error_type="salvaged_directory_not_found",
                ).inc()
            else:
                # Fallback: if we can't determine, use a generic error type
                salvage_errors_total.labels(
                    recycled_directory=recycled_dir,
                    salvaged_directory=salvaged_dir,
                    error_type="directory_not_found",
                ).inc()
        raise HTTPException(
            status_code=404,
            detail=f"Configured directory {cleanup_dir} not found",
        )

    # Security check: prevent operations on critical system directories
    critical_dirs = [
        "/",
        "/home",
        "/usr",
        "/etc",
        "/var",
        "/bin",
        "/sbin",
        "/boot",
        "/root",
    ]
    dir_str = str(directory_path.resolve())
    allowed_tmp_paths = [
        str(Path(p).resolve())
        for p in ["/tmp", "/private/tmp", "/private/var"]
    ]
    # Only allow if in allowed tmp paths or their subdirectories
    if not any(
        dir_str == tmp_path or dir_str.startswith(tmp_path + "/")
        for tmp_path in allowed_tmp_paths
    ):
        for sys_dir in critical_dirs:
            sys_dir_path = str(Path(sys_dir).resolve())
            if dir_str == sys_dir_path or dir_str.startswith(
                sys_dir_path + "/"
            ):  # noqa: E501
                # Record error in appropriate metric based on operation type
                if operation_type == "salvage":
                    recycled_dir = get_recycled_movies_directory()
                    salvaged_dir = get_salvaged_movies_directory()
                    salvage_errors_total.labels(
                        recycled_directory=recycled_dir,
                        salvaged_directory=salvaged_dir,
                        error_type="protected_system_location",
                    ).inc()
                raise HTTPException(
                    status_code=400,
                    detail="Configured directory is in a protected system location",  # noqa: E501
                )


def find_unwanted_files(
    directory_path: Path,
    patterns: List[str],
    operation_type: str = "scan",
):
    """
    Shared helper method to find unwanted files in a directory.

    Args:
        directory_path: Path to the directory to scan
        patterns: List of regex patterns to match unwanted files
        operation_type: Type of operation ("scan" or "cleanup") for metrics

    Returns:
        tuple: (found_files, file_sizes, pattern_matches)
    """
    found_files = []
    file_sizes = {}
    pattern_matches = {}

    # Walk through directory recursively
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            file_path = Path(root) / file

            # Check if file matches any unwanted pattern
            for pattern in patterns:
                if re.search(pattern, file, re.IGNORECASE):
                    found_files.append(str(file_path))
                    pattern_matches[str(file_path)] = pattern

                    try:
                        file_size = file_path.stat().st_size
                        file_sizes[str(file_path)] = file_size

                        # Record file size metric based on operation type
                        if operation_type == "scan":
                            scan_directory_size_bytes.labels(
                                directory=str(directory_path), pattern=pattern
                            ).observe(file_size)
                        else:  # cleanup
                            cleanup_directory_size_bytes.labels(
                                directory=str(directory_path), pattern=pattern
                            ).observe(file_size)
                    except Exception:
                        file_sizes[str(file_path)] = 0
                    break

    return found_files, file_sizes, pattern_matches


def get_subdirectories(
    directory_path: Path,
    operation_type: str = "general",
    dry_run: bool = False,
) -> List[str]:
    """
    Get all subdirectories in a directory.

    Args:
        directory_path: Path to the directory to scan
        operation_type: Type of operation for metrics (e.g., "comparison", "scan", "cleanup")
        dry_run: Boolean for Prometheus metrics

    Returns:
        List of subdirectory names (not full paths)
    """
    subdirectories = []
    try:
        for item in directory_path.iterdir():
            if item.is_dir():
                subdirectories.append(item.name)
    except Exception:
        pass  # Return empty list if directory doesn't exist or can't be read

    # Record metric for subdirectories found (but not for comparison operations)
    if operation_type != "comparison":
        subdirectories_found_total.labels(
            directory=str(directory_path),
            operation_type=operation_type,
            dry_run=str(dry_run).lower(),
        ).inc(len(subdirectories))

    return subdirectories


def has_subtitle_in_root(
    folder_path: Path, subtitle_extensions: List[str]
) -> bool:
    """
    Check if a folder has any subtitle files in its root directory.

    Args:
        folder_path: Path to the folder to check
        subtitle_extensions: List of subtitle file extensions (with leading dot)

    Returns:
        True if folder contains at least one subtitle file in root, False otherwise
    """
    try:
        for item in folder_path.iterdir():
            if item.is_file():
                file_ext = item.suffix.lower()
                if file_ext in [ext.lower() for ext in subtitle_extensions]:
                    return True
    except Exception:
        pass  # Return False if directory can't be read
    return False


def is_subtitle_file(file_path: Path, subtitle_extensions: List[str]) -> bool:
    """
    Check if a file is a subtitle file based on its extension.

    Args:
        file_path: Path to the file to check
        subtitle_extensions: List of subtitle file extensions (with leading dot)

    Returns:
        True if file is a subtitle file, False otherwise
    """
    return file_path.suffix.lower() in [
        ext.lower() for ext in subtitle_extensions
    ]
