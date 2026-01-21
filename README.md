# Brronson

A simple self hosted application for helping with media management for the -arr stack.

## Features

- **FastAPI Application**: Modern, fast web framework for building APIs
- **Docker Containerization**: Easy deployment and development
- **Prometheus Metrics**: Built-in monitoring and observability
- **Docker Compose**: Simple containerized deployment
- **Unit Tests**: Comprehensive test coverage with pytest
- **Health Checks**: Built-in health monitoring endpoints

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for local development)

### Running with Docker Compose

1. **Start the complete stack**:

   ```bash
   docker-compose up -d
   ```

2. **Access the services**:
   - FastAPI App: <http://localhost:1968>
   - API Documentation: <http://localhost:1968/docs>
   - Prometheus Metrics: <http://localhost:1968/metrics>

3. **Stop the services**:

   ```bash
   docker-compose down
   ```

### Running Locally

1. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application**:

   ```bash
   # Development mode with auto-reload
   uvicorn app.main:app --reload --host 0.0.0.0 --port 1968

   # Production mode with gunicorn
   gunicorn --config gunicorn.conf.py app.main:app

   # Or run gunicorn directly with command line options
   gunicorn app.main:app --bind 0.0.0.0:1968 --worker-class uvicorn.workers.UvicornWorker --workers 4
   ```

3. **Run tests**:

   ```bash
   # Run tests locally
   pytest

   # Or run tests in Docker
   docker build -t brronson-api .
   docker run --rm brronson-api pytest
   ```

## API Endpoints

### Core Endpoints

- `GET /` - Root endpoint with API information
- `GET /health` - Health check endpoint with system metrics
- `GET /metrics` - Prometheus metrics endpoint

### API v1 Endpoints

- `GET /api/v1/items` - Get list of items
- `POST /api/v1/items` - Create a new item
- `GET /api/v1/items/{item_id}` - Get a specific item by ID
- `GET /api/v1/compare/directories` - Compare subdirectories between directories
- `POST /api/v1/move/non-duplicates` - Move non-duplicate subdirectories between directories
- `POST /api/v1/recover/subtitle-folders` - Recover folders with subtitles from recycled movies directory

### File Cleanup Endpoints

- `GET /api/v1/cleanup/scan` - Scan configured directory for unwanted files (dry run)
- `POST /api/v1/cleanup/files` - Remove unwanted files from configured directory

#### File Cleanup Usage

The cleanup endpoints help remove unwanted files like:

- `www.YTS.MX.jpg`
- `YIFYStatus.com.txt`
- `.DS_Store` (macOS)
- `Thumbs.db` (Windows)
- Temporary files (`.tmp`, `.temp`, `.log`, `.cache`, `.bak`, `.backup`)

**Configuration:**
The cleanup directory is controlled by the `CLEANUP_DIRECTORY` environment variable (default: `/tmp`).

**Scan for unwanted files:**

```bash
curl "http://localhost:1968/api/v1/cleanup/scan"
```

**Remove unwanted files (dry run first):**

```bash
# Dry run to see what would be deleted
curl -X POST "http://localhost:1968/api/v1/cleanup/files?dry_run=true"

# Actually remove the files
curl -X POST "http://localhost:1968/api/v1/cleanup/files?dry_run=false"
```

**Use custom patterns:**

```bash
curl -X POST "http://localhost:1968/api/v1/cleanup/files?dry_run=false" \
  -H "Content-Type: application/json" \
  -d '{"patterns": ["\\.mp4$", "\\.avi$"]}'
```

**Safety Features:**

- Default `dry_run=true` prevents accidental deletions
- Single directory controlled by environment variable for security
- Critical system directories are protected
- Recursive search through all subdirectories
- Detailed response with file counts and error reporting

### Directory Comparison Endpoints

- `GET /api/v1/compare/directories` - Compare subdirectories between CLEANUP_DIRECTORY and TARGET_DIRECTORY

#### Directory Comparison Usage

The directory comparison endpoint helps identify duplicate subdirectories between two configured directories.

**Configuration:**

- `CLEANUP_DIRECTORY` - First directory to scan for subdirectories (default: `/tmp`)
- `TARGET_DIRECTORY` - Second directory to scan for subdirectories (default: `/tmp`)

**Compare directories (default - counts only):**

```bash
curl "http://localhost:1968/api/v1/compare/directories"
```

**Compare directories with verbose output:**

```bash
curl "http://localhost:1968/api/v1/compare/directories?verbose=true"
```

**Response format (default):**

```json
{
  "cleanup_directory": "/path/to/cleanup",
  "target_directory": "/path/to/target",
  "duplicates": ["dir2"],
  "duplicate_count": 1,
  "non_duplicate_count": 2,
  "total_cleanup_subdirectories": 3,
  "total_target_subdirectories": 3
}
```

**Response format (verbose):**

```json
{
  "cleanup_directory": "/path/to/cleanup",
  "target_directory": "/path/to/target",
  "cleanup_subdirectories": ["dir1", "dir2", "dir3"],
  "target_subdirectories": ["dir2", "dir4", "dir5"],
  "duplicates": ["dir2"],
  "duplicate_count": 1,
  "non_duplicate_count": 2,
  "total_cleanup_subdirectories": 3,
  "total_target_subdirectories": 3
}
```

**Features:**

- Compares only subdirectories (ignores files)
- Returns lists of all subdirectories from both directories
- Identifies duplicates that exist in both directories
- Provides counts for monitoring and analysis
- Safe operation - read-only, no modifications
- Detailed response with comprehensive directory information

### File Move Endpoints

- `POST /api/v1/move/non-duplicates` - Move non-duplicate subdirectories from CLEANUP_DIRECTORY to TARGET_DIRECTORY

#### File Move Usage

The file move endpoint helps move non-duplicate subdirectories from the cleanup directory to the target directory, reusing the existing directory comparison logic. **By default, this endpoint runs cleanup files before moving to remove unwanted files from the directories being moved.**

**Configuration:**

- `CLEANUP_DIRECTORY` - Source directory containing subdirectories to move (default: `/tmp`)
- `TARGET_DIRECTORY` - Destination directory for non-duplicate subdirectories (default: `/tmp`)

**Move non-duplicate directories (dry run - default, with cleanup):**

```bash
curl -X POST "http://localhost:1968/api/v1/move/non-duplicates"
```

**Move non-duplicate directories (actual move, with cleanup):**

```bash
curl -X POST "http://localhost:1968/api/v1/move/non-duplicates?dry_run=false"
```

**Skip cleanup and just move files:**

```bash
curl -X POST "http://localhost:1968/api/v1/move/non-duplicates?skip_cleanup=true"
```

**Move non-duplicate directories with custom batch size:**

```bash
curl -X POST "http://localhost:1968/api/v1/move/non-duplicates?dry_run=false&batch_size=5"
```

**Move with cleanup disabled and custom batch size:**

```bash
curl -X POST "http://localhost:1968/api/v1/move/non-duplicates?skip_cleanup=true&batch_size=3"
```

**Response format (with cleanup):**

```json
{
  "cleanup_directory": "/path/to/cleanup",
  "target_directory": "/path/to/target",
  "dry_run": true,
  "batch_size": 1,
  "skip_cleanup": false,
  "non_duplicates_found": 2,
  "files_moved": 1,
  "errors": 0,
  "non_duplicate_subdirectories": ["cleanup_only", "another_cleanup_only"],
  "moved_subdirectories": ["cleanup_only"],
  "error_details": [],
  "remaining_files": 1,
  "cleanup_results": {
    "directory": "/path/to/cleanup",
    "dry_run": true,
    "patterns_used": ["www\\.YTS\\.MX\\.jpg$", "\\.DS_Store$", ...],
    "files_found": 3,
    "files_removed": 0,
    "errors": 0,
    "found_files": ["/path/to/cleanup/file1.jpg", "/path/to/cleanup/file2.txt"],
    "removed_files": [],
    "error_details": []
  }
}
```

**Response format (skip cleanup):**

```json
{
  "cleanup_directory": "/path/to/cleanup",
  "target_directory": "/path/to/target",
  "dry_run": true,
  "batch_size": 1,
  "skip_cleanup": true,
  "non_duplicates_found": 2,
  "files_moved": 1,
  "errors": 0,
  "non_duplicate_subdirectories": ["cleanup_only", "another_cleanup_only"],
  "moved_subdirectories": ["cleanup_only"],
  "error_details": [],
  "remaining_files": 1
}
```

**Features:**

- **Cleanup Integration**: By default, runs cleanup files before moving to remove unwanted files
- **Skip Cleanup Option**: Use `skip_cleanup=true` to bypass the cleanup step
- **Safe by Default**: Default `dry_run=true` prevents accidental moves
- **Batch Processing**: Default `batch_size=1` processes one file at a time for controlled operations
- **Duplicate Detection**: Only moves subdirectories that don't exist in target directory
- **Error Handling**: Comprehensive error reporting for failed moves and cleanup operations
- **File Preservation**: Preserves all file contents during moves
- **Cross-Device Support**: Uses `shutil.move()` for cross-device compatibility
- **Detailed Reporting**: Provides complete information about what was moved and cleaned
- **Progress Tracking**: `remaining_files` field shows how many files still need to be moved
- **Prometheus Metrics**: Records both move operations and cleanup operations

### Subtitle Recovery Endpoints

- `POST /api/v1/recover/subtitle-folders` - Recover folders with subtitles from recycled movies directory

#### Subtitle Recovery Usage

The subtitle recovery endpoint helps move folders that contain subtitle files from the recycled movies directory to the recovered movies directory. This is useful for recovering movie folders that were moved to the recycled directory but still have subtitle files that should be preserved.

**Configuration:**

- `RECYCLED_MOVIES_DIRECTORY` - Source directory containing folders to scan (default: `/recycled/movies`)
- `RECOVERED_MOVIES_DIRECTORY` - Destination directory for folders with subtitles (default: `/recovered/movies`)

**Recover folders with subtitles (dry run - default):**

```bash
curl -X POST "http://localhost:1968/api/v1/recover/subtitle-folders"
```

**Recover folders with subtitles (actual move):**

```bash
curl -X POST "http://localhost:1968/api/v1/recover/subtitle-folders?dry_run=false"
```

**Use custom subtitle extensions:**

```bash
curl -X POST "http://localhost:1968/api/v1/recover/subtitle-folders?dry_run=false" \
  -H "Content-Type: application/json" \
  -d '[".srt", ".sub", ".vtt", ".custom"]'
```

**Response format:**

```json
{
  "recycled_directory": "/path/to/recycled/movies",
  "recovered_directory": "/path/to/recovered/movies",
  "dry_run": true,
  "subtitle_extensions": [".srt", ".sub", ".vtt", ".ass", ".ssa", ".idx", ".sup", ".scc", ".ttml", ".dfxp", ".mcc", ".stl", ".sbv", ".smi", ".txt"],
  "folders_scanned": 5,
  "folders_with_subtitles_found": 2,
  "folders_copied": 2,
  "folders_skipped": 0,
  "subtitle_files_copied": 4,
  "subtitle_files_skipped": 0,
  "errors": 0,
  "folders_with_subtitles": ["Movie1", "Movie2"],
  "copied_folders": ["Movie1", "Movie2"],
  "skipped_folders": [],
  "error_details": []
}
```

**Features:**

- **Subtitle Detection**: Automatically detects folders with subtitle files in the root directory
- **Selective File Copying**: Only copies subtitle files and folder structure, skips media files (video/images)
- **Preserves Structure**: Maintains the complete folder structure during the copy
- **Multiple Formats**: Supports common subtitle formats (.srt, .sub, .vtt, .ass, .ssa, etc.)
- **Custom Extensions**: Allows custom subtitle file extensions to be specified
- **Safe by Default**: Default `dry_run=true` prevents accidental copies
- **Skip Existing**: Does not overwrite existing destination folders or files (skips them instead)
- **Error Handling**: Comprehensive error reporting for failed operations
- **Prometheus Metrics**: Records recovery operations including skipped items for monitoring

**Supported Subtitle Formats:**

The default configuration supports the following subtitle file extensions:

- `.srt` - SubRip
- `.sub` - SubViewer
- `.vtt` - WebVTT
- `.ass` - Advanced SubStation Alpha
- `.ssa` - SubStation Alpha
- `.idx` - VobSub index
- `.sup` - Blu-ray subtitle
- `.scc` - Scenarist Closed Caption
- `.ttml` - Timed Text Markup Language
- `.dfxp` - Distribution Format Exchange Profile
- `.mcc` - MacCaption
- `.stl` - Spruce subtitle
- `.sbv` - YouTube subtitle
- `.smi` - SAMI
- `.txt` - Plain text (some subtitle files use this extension)

**File Filtering:**

The recovery operation intelligently filters files:

- **Copies**: Subtitle files (based on extension list) only
- **Skips**: Video files (.mp4, .avi, .mkv, etc.), image files (.jpg, .png, etc.), and other non-subtitle files (like .nfo, .txt, etc.)
- **Skip Existing**: If a destination folder or file already exists, it is skipped (not overwritten) and logged in the response

**Cleanup Integration:**

The move operation now includes automatic cleanup by default:

- **Default Behavior**: Runs cleanup files before moving directories
- **Cleanup Patterns**: Uses the same default patterns as the standalone cleanup endpoint
- **Cleanup Mode**: Respects the `dry_run` parameter (cleanup is dry run if move is dry run)
- **Error Resilience**: If cleanup fails, the move operation continues anyway
- **Results Included**: Cleanup results are included in the move response
- **Skip Option**: Use `skip_cleanup=true` to disable the cleanup step

**Safety Features:**

- Default `dry_run=true` prevents accidental moves
- Default cleanup integration removes unwanted files before moving
- Only moves subdirectories (ignores individual files)
- Preserves existing files in target directory
- Comprehensive error reporting for failed operations
- Uses existing directory validation and security checks
- Cleanup failures don't prevent move operations from continuing

## Monitoring

### Health Check

The application provides a simple health check endpoint at `/health` that includes:

- Service status (always "healthy" when the service is running)
- Service name and version
- Timestamp of the health check

### Prometheus Metrics

The application uses [prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator) to automatically collect and expose the following Prometheus metrics:

#### HTTP Metrics (Automatic)

- `requests_total` - Total HTTP requests with method, handler, and status labels
- `request_duration_seconds` - HTTP request latency with method and handler labels
- `request_size_bytes` - Size of incoming requests
- `response_size_bytes` - Size of outgoing responses
- `http_requests_inprogress` - Number of requests currently being processed

#### File Cleanup Metrics

- `brronson_cleanup_files_found_total` - Total unwanted files found during cleanup (labels: directory, pattern, dry_run)
- `brronson_cleanup_current_files` - Current number of unwanted files in directory (labels: directory, pattern, dry_run)
- `brronson_cleanup_files_removed_total` - Total files successfully removed during cleanup (labels: directory, pattern, dry_run)
- `brronson_cleanup_errors_total` - Total errors during file cleanup operations
- `brronson_cleanup_operation_duration_seconds` - Time spent on cleanup operations

#### Directory Comparison Metrics

- `brronson_comparison_duplicates_found_total` - Current number of duplicate subdirectories found between directories (labels: cleanup_directory, target_directory)
- `brronson_comparison_non_duplicates_found_total` - Current number of non-duplicate subdirectories in cleanup directory (labels: cleanup_directory, target_directory)
- `brronson_comparison_operation_duration_seconds` - Time spent on directory comparison operations (labels: operation_type, cleanup_directory, target_directory)

#### File Move Metrics

- `brronson_move_files_found_total` - Total files found for moving (labels: cleanup_directory, target_directory)
- `brronson_move_files_moved_total` - Total files successfully moved (labels: cleanup_directory, target_directory)
- `brronson_move_errors_total` - Total errors during file move operations (labels: cleanup_directory, target_directory, error_type)
- `brronson_move_operation_duration_seconds` - Time spent on file move operations (labels: operation_type, cleanup_directory, target_directory)
- `brronson_move_duplicates_found` - Number of duplicate subdirectories found during move operation

#### Subtitle Recovery Metrics

- `brronson_recovery_folders_scanned_total` - Total number of folders scanned for subtitle recovery (labels: recycled_directory, dry_run)
- `brronson_recovery_folders_with_subtitles_found` - Current number of folders found with subtitles in root (labels: recycled_directory, dry_run)
- `brronson_recovery_folders_copied_total` - Total number of folders successfully copied during recovery (labels: recycled_directory, recovered_directory, dry_run)
- `brronson_recovery_folders_skipped_total` - Total number of folders skipped during recovery (target already exists) (labels: recycled_directory, recovered_directory, dry_run)
- `brronson_recovery_subtitle_files_copied_total` - Total number of subtitle files copied during recovery (labels: recycled_directory, recovered_directory, dry_run)
- `brronson_recovery_files_skipped_total` - Total number of subtitle files skipped during recovery (target already exists) (labels: recycled_directory, recovered_directory, dry_run)
- `brronson_recovery_errors_total` - Total errors during subtitle recovery operations (labels: recycled_directory, recovered_directory, error_type)
- `brronson_recovery_operation_duration_seconds` - Time spent on subtitle recovery operations (labels: operation_type, recycled_directory, recovered_directory)

## Deployment

### Gunicorn Configuration

The application is configured to run with Gunicorn using Uvicorn workers for production deployments. This provides:

- **Process Management**: Multiple worker processes for better performance
- **Load Balancing**: Automatic distribution of requests across workers
- **Graceful Restarts**: Workers can be restarted without dropping connections
- **Monitoring**: Built-in logging and process monitoring

#### Configuration Options

The `gunicorn.conf.py` file includes optimized settings that can be configured via environment variables:

- **Port**: `PORT` - Server port (default: `1968`)
- **Workers**: `GUNICORN_WORKERS` - Number of worker processes (default: `cpu_count * 2 + 1`)
- **Log Level**: `GUNICORN_LOG_LEVEL` - Logging level (default: `info`)
- **Worker Class**: Uses `uvicorn.workers.UvicornWorker` for ASGI support
- **Timeouts**: 120-second request timeout with 30-second graceful shutdown
- **Logging**: Structured access and error logging
- **Security**: Request size limits and field restrictions
- **Performance**: Shared memory for temporary files

#### Running with Gunicorn

```bash
# Using configuration file (recommended)
gunicorn --config gunicorn.conf.py app.main:app

# Using command line options
gunicorn app.main:app --bind 0.0.0.0:1968 --worker-class uvicorn.workers.UvicornWorker --workers 4

# Development mode (single worker with auto-reload)
gunicorn app.main:app --bind 0.0.0.0:1968 --worker-class uvicorn.workers.UvicornWorker --workers 1 --reload

# With custom configuration
PORT=8080 GUNICORN_WORKERS=2 GUNICORN_LOG_LEVEL=debug gunicorn --config gunicorn.conf.py app.main:app
```

#### Docker Deployment

The Docker image automatically uses Gunicorn with the optimized configuration:

```bash
# Build and run with Docker (default settings)
docker build -t brronson-api .
docker run -p 1968:1968 brronson-api

# Run with custom configuration
docker run -p 8080:8080 \
  -e PORT=8080 \
  -e GUNICORN_WORKERS=2 \
  -e GUNICORN_LOG_LEVEL=debug \
  brronson-api

# Or use Docker Compose
docker-compose up -d

# Docker Compose with custom configuration
PORT=8080 GUNICORN_WORKERS=2 GUNICORN_LOG_LEVEL=debug docker-compose up -d
```

### Environment Variables

#### Gunicorn Environment Variables

- `PORT` - Server port (default: `1968`)
- `GUNICORN_WORKERS` - Number of worker processes (default: `cpu_count * 2 + 1`)
- `GUNICORN_LOG_LEVEL` - Logging level (default: `info`)

#### Application Environment Variables

- `PROMETHEUS_MULTIPROC_DIR` - Directory for Prometheus multiprocess metrics (set to `/tmp` in Docker)
- `ENABLE_METRICS` - Set to `true` to enable Prometheus metrics collection (default: enabled)
- `CLEANUP_DIRECTORY` - Directory to scan for unwanted files (default: `/data`)
- `TARGET_DIRECTORY` - Directory to move non-duplicate files to (default: `/target`)
- `RECYCLED_MOVIES_DIRECTORY` - Directory containing recycled movie folders (default: `/recycled/movies`)
- `RECOVERED_MOVIES_DIRECTORY` - Directory for recovered movie folders with subtitles (default: `/recovered/movies`)

### Logging Configuration

The application includes a configurable logging framework with the following environment variables:

- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) (default: `INFO`)
- `LOG_FILE`: Name of the log file (default: `brronson.log`)
- `LOG_FORMAT`: Log message format (default: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`)

Logs are written to both console and a rotating file in the `logs/` directory. The log file is automatically rotated when it reaches 10MB and keeps up to 5 backup files.

### Example Log Output

```text
2024-01-15 10:30:15 - app.main - INFO - Starting Brronson application version 1.0.0
2024-01-15 10:30:15 - app.main - INFO - Cleanup directory: /data
2024-01-15 10:30:15 - app.main - INFO - Target directory: /target
2024-01-15 10:30:20 - app.main - INFO - Move operation: Found 3 subdirectories in cleanup, 1 in target
2024-01-15 10:30:20 - app.main - INFO - Move analysis: 1 duplicates, 2 non-duplicates to move
2024-01-15 10:30:20 - app.main - INFO - Directories to move: cleanup_only, another_cleanup_only
2024-01-15 10:30:20 - app.main - INFO - Starting to move directory: cleanup_only from /data/cleanup_only to /target/cleanup_only
2024-01-15 10:30:20 - app.main - INFO - Successfully finished moving directory: cleanup_only
```

The metrics endpoint is automatically exposed at `/metrics` and supports gzip compression for efficient data transfer.

### Viewing Metrics

You can view the Prometheus metrics directly at <http://localhost:1968/metrics> or use any Prometheus-compatible monitoring system to scrape this endpoint.
