"""Prometheus metrics definitions for the Brronson application."""

from prometheus_client import Counter, Gauge, Histogram

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
