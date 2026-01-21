import logging
import logging.config
import os
import re
import shutil
import time
from pathlib import Path
from typing import List, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator, metrics

from .version import version


# Configure logging
def setup_logging():
    """Setup configurable logging for the application"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_file = os.getenv("LOG_FILE", "brronson.log")
    log_format = os.getenv(
        "LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": log_format,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": log_level,
                "formatter": "default",
                "filename": str(log_dir / log_file),
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
            },
        },
        "loggers": {
            "": {  # Root logger
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(log_config)


# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


def get_cleanup_directory():
    """Get the cleanup directory from environment variable"""
    return os.getenv("CLEANUP_DIRECTORY", "/data")


def get_target_directory():
    """Get the target directory from environment variable"""
    return os.getenv("TARGET_DIRECTORY", "/target")


def get_recycled_movies_directory():
    """Get the recycled movies directory from environment variable"""
    return os.getenv("RECYCLED_MOVIES_DIRECTORY", "/recycled/movies")


def get_salvaged_movies_directory():
    """Get the salvaged movies directory from environment variable"""
    return os.getenv("SALVAGED_MOVIES_DIRECTORY", "/salvaged/movies")


# Default patterns for common unwanted files
DEFAULT_UNWANTED_PATTERNS = [
    r"www\.YTS\.MX\.jpg$",
    r"www\.YTS\.AM\.jpg$",
    r"www\.YTS\.LT\.jpg$",
    r"WWW\.YTS\.[A-Z]+\.jpg$",
    r"WWW\.YIFY-TORRENTS\.COM\.jpg$",
    r"YIFYStatus\.com\.txt$",
    r"YTSProxies\.com\.txt$",
    r"YTSYifyUP.*\(TOR\)\.txt$",
    r"\.DS_Store$",
    r"Thumbs\.db$",
    r"desktop\.ini$",
    r"\.tmp$",
    r"\.temp$",
    r"\.log$",
    r"\.cache$",
    r"\.bak$",
    r"\.backup$",
]

# Default subtitle file extensions (case-insensitive)
DEFAULT_SUBTITLE_EXTENSIONS = [
    ".srt",
    ".sub",
    ".vtt",
    ".ass",
    ".ssa",
    ".idx",
    ".sup",
    ".scc",
    ".ttml",
    ".dfxp",
    ".mcc",
    ".stl",
    ".sbv",
    ".smi",
    ".txt",  # Some subtitle files use .txt extension
]


# Custom Prometheus metrics for file cleanup operations
cleanup_files_found_total = Counter(
    "brronson_cleanup_files_found_total",
    "Total number of unwanted files found during cleanup",
    ["directory", "pattern", "dry_run"],
)

cleanup_current_files = Gauge(
    "brronson_cleanup_current_files",
    "Current number of unwanted files in directory",
    ["directory", "pattern", "dry_run"],
)

cleanup_files_removed_total = Counter(
    "brronson_cleanup_files_removed_total",
    "Total number of files successfully removed during cleanup",
    ["directory", "pattern", "dry_run"],
)

cleanup_errors_total = Counter(
    "brronson_cleanup_errors_total",
    "Total number of errors during file cleanup",
    ["directory", "error_type"],
)

cleanup_operation_duration = Histogram(
    "brronson_cleanup_operation_duration_seconds",
    "Time spent on cleanup operations",
    ["operation_type", "directory"],
)

cleanup_directory_size_bytes = Histogram(
    "brronson_cleanup_directory_size_bytes",
    "Size of files found during cleanup",
    ["directory", "pattern"],
)

# Custom Prometheus metrics for file scan operations
scan_files_found_total = Counter(
    "brronson_scan_files_found_total",
    "Total number of unwanted files found during scan",
    ["directory", "pattern"],
)

scan_current_files = Gauge(
    "brronson_scan_current_files",
    "Current number of unwanted files in directory",
    ["directory", "pattern"],
)

scan_errors_total = Counter(
    "brronson_scan_errors_total",
    "Total number of errors during file scan",
    ["directory", "error_type"],
)

scan_operation_duration = Histogram(
    "brronson_scan_operation_duration_seconds",
    "Time spent on scan operations",
    ["operation_type", "directory"],
)

scan_directory_size_bytes = Histogram(
    "brronson_scan_directory_size_bytes",
    "Size of files found during scan",
    ["directory", "pattern"],
)

# Custom Prometheus metrics for directory comparison operations
comparison_duplicates_found_total = Gauge(
    "brronson_comparison_duplicates_found_total",
    "Current number of duplicate subdirectories found between directories",
    ["cleanup_directory", "target_directory"],
)

comparison_non_duplicates_found_total = Gauge(
    "brronson_comparison_non_duplicates_found_total",
    "Current number of non-duplicate subdirectories in cleanup directory",
    ["cleanup_directory", "target_directory"],
)

comparison_errors_total = Counter(
    "brronson_comparison_errors_total",
    "Total number of errors during directory comparison",
    ["directory", "error_type"],
)

comparison_operation_duration = Histogram(
    "brronson_comparison_operation_duration_seconds",
    "Time spent on directory comparison operations",
    ["operation_type", "cleanup_directory", "target_directory"],
)

# Custom Prometheus metrics for subdirectory operations
subdirectories_found_total = Counter(
    "brronson_subdirectories_found_total",
    "Total number of subdirectories found",
    ["directory", "operation_type", "dry_run"],
)

# Custom Prometheus metrics for file move operations
move_files_found_total = Counter(
    "brronson_move_files_found_total",
    "Total number of files found for moving",
    ["cleanup_directory", "target_directory", "dry_run"],
)

move_files_moved_total = Counter(
    "brronson_move_files_moved_total",
    "Total number of files successfully moved",
    ["cleanup_directory", "target_directory", "dry_run"],
)

move_errors_total = Counter(
    "brronson_move_errors_total",
    "Total number of errors during file move operations",
    ["cleanup_directory", "target_directory", "error_type"],
)

move_operation_duration = Histogram(
    "brronson_move_operation_duration_seconds",
    "Time spent on file move operations",
    ["operation_type", "cleanup_directory", "target_directory"],
)

move_duplicates_found = Gauge(
    "brronson_move_duplicates_found",
    "Number of duplicate subdirectories found during move operation",
    ["cleanup_directory", "target_directory", "dry_run"],
)

move_directories_moved = Gauge(
    "brronson_move_directories_moved",
    "Number of directories successfully moved",
    ["cleanup_directory", "target_directory", "dry_run"],
)

move_batch_operations_total = Counter(
    "brronson_move_batch_operations_total",
    "Total number of batch operations performed",
    ["cleanup_directory", "target_directory", "batch_size", "dry_run"],
)

# Custom Prometheus metrics for subtitle salvage operations
salvage_folders_scanned_total = Counter(
    "brronson_salvage_folders_scanned_total",
    "Total number of folders scanned for subtitle salvage",
    ["recycled_directory", "dry_run"],
)

salvage_folders_with_subtitles_found = Gauge(
    "brronson_salvage_folders_with_subtitles_found",
    "Current number of folders found with subtitles in root",
    ["recycled_directory", "dry_run"],
)

salvage_folders_copied_total = Counter(
    "brronson_salvage_folders_copied_total",
    "Total number of folders successfully copied during salvage",
    ["recycled_directory", "salvaged_directory", "dry_run"],
)

salvage_subtitle_files_copied_total = Counter(
    "brronson_salvage_subtitle_files_copied_total",
    "Total number of subtitle files copied during salvage",
    ["recycled_directory", "salvaged_directory", "dry_run"],
)

salvage_folders_skipped_total = Counter(
    "brronson_salvage_folders_skipped_total",
    "Total number of folders skipped during salvage (target already exists)",
    ["recycled_directory", "salvaged_directory", "dry_run"],
)

salvage_files_skipped_total = Counter(
    "brronson_salvage_files_skipped_total",
    "Total number of subtitle files skipped during salvage (target already exists)",
    ["recycled_directory", "salvaged_directory", "dry_run"],
)

salvage_errors_total = Counter(
    "brronson_salvage_errors_total",
    "Total number of errors during subtitle salvage operations",
    ["recycled_directory", "salvaged_directory", "error_type"],
)

salvage_operation_duration = Histogram(
    "brronson_salvage_operation_duration_seconds",
    "Time spent on subtitle salvage operations",
    ["operation_type", "recycled_directory", "salvaged_directory"],
)

brronson_info = Gauge("brronson_info", "Info about the server", ["version"])


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


def is_media_file(file_path: Path) -> bool:
    """
    Check if a file is a media file (video or image).

    Args:
        file_path: Path to the file to check

    Returns:
        True if file is a media file, False otherwise
    """
    media_extensions = [
        # Video formats
        ".mp4",
        ".avi",
        ".mkv",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",
        ".mpg",
        ".mpeg",
        ".3gp",
        ".ogv",
        ".divx",
        ".xvid",
        ".vob",
        ".ts",
        ".m2ts",
        ".mts",
        # Image formats
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".tiff",
        ".tif",
        ".webp",
        ".svg",
        ".ico",
        ".heic",
        ".heif",
    ]
    return file_path.suffix.lower() in media_extensions


# Create FastAPI app
app = FastAPI(title="Brronson", version=version)

# Log application startup
logger.info(f"Starting Brronson application version {version}")
logger.info(f"Cleanup directory: {get_cleanup_directory()}")
logger.info(f"Target directory: {get_target_directory()}")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure Prometheus metrics
instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_respect_env_var=False,  # Disable env var requirement for testing
    should_instrument_requests_inprogress=True,
    excluded_handlers=[".*admin.*", "/metrics"],
)

instrumentator.add(metrics.request_size())
instrumentator.add(metrics.response_size())
instrumentator.add(metrics.latency())
instrumentator.instrument(app).expose(
    app, include_in_schema=False, should_gzip=True
)

# Set info metric
brronson_info.labels(version=version).set(1)


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Welcome to Brronson", "version": version}


@app.get("/version")
async def get_version():
    """Version endpoint"""
    return {
        "message": f"The current version of Brronson is {version}",
        "version": version,
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "brronson",
        "version": version,
        "timestamp": time.time(),
    }


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


@app.post("/api/v1/cleanup/files")
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


@app.get("/api/v1/cleanup/scan")
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


@app.get("/api/v1/compare/directories")
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


@app.post("/api/v1/move/non-duplicates")
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


@app.post("/api/v1/salvage/subtitle-folders")
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

        # Validate both directories
        validate_directory(recycled_path, recycled_dir, "salvage")
        validate_directory(salvaged_path, salvaged_dir, "salvage")

        # Ensure salvaged directory exists
        salvaged_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Subtitle salvage: Scanning {recycled_path} for folders with subtitles"
        )

        # Get all subdirectories in recycled directory
        folders_to_check = []
        try:
            for item in recycled_path.iterdir():
                if item.is_dir():
                    folders_to_check.append(item)
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


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Brronson server on 0.0.0.0:1968")
    uvicorn.run(app, host="0.0.0.0", port=1968)
