"""Directory comparison endpoints."""

import logging
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import get_cleanup_directory, get_target_directory
from ..helpers import get_subdirectories, validate_directory
from ..metrics import (
    comparison_duplicates_found_total,
    comparison_errors_total,
    comparison_non_duplicates_found_total,
    comparison_operation_duration,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/v1/compare/directories")
async def compare_directories(verbose: bool = False):
    """
    Compare subdirectories of CLEANUP_DIRECTORY with subdirectories of
     TARGET_DIRECTORY and count duplicates that exist in both.

    Args:
        verbose: If True, include full lists of subdirectories in response
    """
    start_time = time.time()

    cleanup_dir = get_cleanup_directory()
    target_dir = get_target_directory()

    try:
        cleanup_path = Path(cleanup_dir).resolve()
        target_path = Path(target_dir).resolve()

        # Validate both directories
        validate_directory(cleanup_path, cleanup_dir, "comparison")
        validate_directory(target_path, target_dir, "comparison")

        # Get subdirectories from both directories
        cleanup_subdirs = get_subdirectories(cleanup_path, "comparison", False)
        target_subdirs = get_subdirectories(target_path, "comparison", False)

        logger.info(
            f"Directory comparison: Found {len(cleanup_subdirs)} subdirectories in cleanup, {len(target_subdirs)} in target"
        )

        # Find duplicates (subdirectories that exist in both)
        cleanup_set = set(cleanup_subdirs)
        target_set = set(target_subdirs)
        duplicates = list(cleanup_set.intersection(target_set))
        non_duplicates = list(cleanup_set - target_set)

        logger.info(
            f"Comparison results: {len(duplicates)} duplicates, {len(non_duplicates)} non-duplicates"
        )
        if non_duplicates:
            logger.info(
                f"Non-duplicate directories: {', '.join(non_duplicates)}"
            )

        # Record metrics for duplicates and non-duplicates
        comparison_duplicates_found_total.labels(
            cleanup_directory=cleanup_dir, target_directory=target_dir
        ).set(len(duplicates))
        comparison_non_duplicates_found_total.labels(
            cleanup_directory=cleanup_dir, target_directory=target_dir
        ).set(len(non_duplicates))

        # Record operation duration
        operation_duration = time.time() - start_time
        comparison_operation_duration.labels(
            operation_type="compare",
            cleanup_directory=cleanup_dir,
            target_directory=target_dir,
        ).observe(operation_duration)

        response = {
            "cleanup_directory": str(cleanup_path),
            "target_directory": str(target_path),
            "duplicates": duplicates,
            "duplicate_count": len(duplicates),
            "non_duplicate_count": len(non_duplicates),
            "total_cleanup_subdirectories": len(cleanup_subdirs),
            "total_target_subdirectories": len(target_subdirs),
        }

        # Include full lists only if verbose is True
        if verbose:
            response["cleanup_subdirectories"] = cleanup_subdirs
            response["target_subdirectories"] = target_subdirs

        return response

    except HTTPException:
        # Re-raise HTTPExceptions (like 404 for missing directories) as-is
        raise
    except Exception as e:
        comparison_errors_total.labels(
            directory=f"{cleanup_dir}:{target_dir}",
            error_type="operation_error",
        ).inc()
        raise HTTPException(
            status_code=500,
            detail=f"Error during directory comparison: {str(e)}",
        )
