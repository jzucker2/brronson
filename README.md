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
- `POST /api/v1/salvage/subtitle-folders` - Salvage folders with subtitles from recycled movies directory
- `POST /api/v1/migrate/non-movie-folders` - Move folders without movie files to migrated directory
- `POST /api/v1/sync/subtitles-to-target` - Move subtitle files from salvaged or migrated directory to target

### File Cleanup Endpoints

- `GET /api/v1/cleanup/scan` - Scan configured directory for unwanted files (dry run)
- `POST /api/v1/cleanup/files` - Remove unwanted files from configured directory
- `POST /api/v1/cleanup/empty-folders` - Remove empty folders from target directory

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

#### Empty Folder Cleanup Usage

The empty folder cleanup endpoint helps remove empty folders from the target directory. This is useful for cleaning up directory structures after files have been moved or deleted.

**Configuration:**

- `TARGET_DIRECTORY` - Directory to scan for empty folders (default: `/target`)

**Cleanup empty folders (dry run - default):**

```bash
curl -X POST "http://localhost:1968/api/v1/cleanup/empty-folders"
```

**Cleanup empty folders (actual removal):**

```bash
curl -X POST "http://localhost:1968/api/v1/cleanup/empty-folders?dry_run=false"
```

**Use batch_size for re-entrant operations:**

```bash
# Delete up to 50 empty folders per request
curl -X POST "http://localhost:1968/api/v1/cleanup/empty-folders?dry_run=false&batch_size=50"
```

**Response format:**

```json
{
  "directory": "/path/to/target",
  "dry_run": true,
  "batch_size": 100,
  "empty_folders_found": 5,
  "empty_folders_removed": 0,
  "errors": 0,
  "batch_limit_reached": false,
  "remaining_folders": 0,
  "empty_folders": ["empty1", "nested/empty2", "nested/empty2/empty3"],
  "removed_folders": [],
  "error_details": []
}
```

**Features:**

- **Recursive Scanning**: Finds all empty folders recursively, including nested structures
- **Deepest First Processing**: Processes folders from deepest to shallowest to handle nested empty folders correctly
- **Safe by Default**: Default `dry_run=true` prevents accidental deletions
- **Batch Processing**: Default `batch_size=100` allows processing in batches for re-entrant operations
- **Re-entrant**: Can be called multiple times to resume from where it stopped
- **Nested Folder Handling**: Correctly identifies and removes parent folders that only contain empty subdirectories
- **Error Handling**: Comprehensive error reporting for failed deletions
- **Progress Tracking**: `remaining_folders` field shows how many folders still need to be processed
- **Prometheus Metrics**: Records found, removed, and error metrics

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

### Subtitle Salvage Endpoints

- `POST /api/v1/salvage/subtitle-folders` - Salvage folders with subtitles from recycled movies directory

#### Subtitle Salvage Usage

The subtitle salvage endpoint helps move folders that contain subtitle files from the recycled movies directory to the salvaged movies directory. This is useful for salvaging movie folders that were moved to the recycled directory but still have subtitle files that should be preserved.

**Configuration:**

- `RECYCLED_MOVIES_DIRECTORY` - Source directory containing folders to scan (default: `/recycled/movies`)
- `SALVAGED_MOVIES_DIRECTORY` - Destination directory for folders with subtitles (default: `/salvaged/movies`)

**Salvage folders with subtitles (dry run - default):**

```bash
curl -X POST "http://localhost:1968/api/v1/salvage/subtitle-folders"
```

**Salvage folders with subtitles (actual move):**

```bash
curl -X POST "http://localhost:1968/api/v1/salvage/subtitle-folders?dry_run=false"
```

**Use custom subtitle extensions:**

```bash
curl -X POST "http://localhost:1968/api/v1/salvage/subtitle-folders?dry_run=false" \
  -H "Content-Type: application/json" \
  -d '[".srt", ".sub", ".vtt", ".custom"]'
```

**Use batch_size for re-entrant operations:**

```bash
# Copy up to 50 files per request (skipped files don't count)
curl -X POST "http://localhost:1968/api/v1/salvage/subtitle-folders?dry_run=false&batch_size=50"
```

**Response format:**

```json
{
  "recycled_directory": "/path/to/recycled/movies",
  "salvaged_directory": "/path/to/salvaged/movies",
  "dry_run": true,
  "batch_size": 100,
  "subtitle_extensions": [".srt", ".sub", ".vtt", ".ass", ".ssa", ".idx", ".sup", ".scc", ".ttml", ".dfxp", ".mcc", ".stl", ".sbv", ".smi", ".txt"],
  "folders_scanned": 5,
  "folders_with_subtitles_found": 2,
  "folders_copied": 2,
  "folders_skipped": 0,
  "subtitle_files_copied": 4,
  "subtitle_files_skipped": 0,
  "batch_limit_reached": false,
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
- **Batch Processing**: `batch_size` parameter limits files copied per request (default: 100), making operations re-entrant
- **Re-entrant**: Skipped files don't count toward batch_size, allowing safe resumption of interrupted operations
- **Error Handling**: Comprehensive error reporting for failed operations
- **Prometheus Metrics**: Records salvage operations including skipped items for monitoring

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

The salvage operation intelligently filters files:

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

### Non-Movie Folder Migration Endpoints

- `POST /api/v1/migrate/non-movie-folders` - Move folders without movie files to migrated directory

#### Non-Movie Folder Migration Usage

The non-movie folder migration endpoint helps move folders that contain files but no movie files (like .avi, .mkv, .mp4, etc.) from the target directory to the migrated movies directory. This is useful for organizing folders that don't contain actual movie content.

**Configuration:**

- `TARGET_DIRECTORY` - Directory to scan for folders without movie files (default: `/target`)
- `MIGRATED_MOVIES_DIRECTORY` - Destination directory for folders without movie files (default: `/migrated/movies`)

**Migrate folders without movie files (dry run - default):**

```bash
curl -X POST "http://localhost:1968/api/v1/migrate/non-movie-folders"
```

**Migrate folders without movie files (actual move):**

```bash
curl -X POST "http://localhost:1968/api/v1/migrate/non-movie-folders?dry_run=false"
```

**Use batch_size for re-entrant operations:**

```bash
# Move up to 50 folders per request (skipped folders don't count)
curl -X POST "http://localhost:1968/api/v1/migrate/non-movie-folders?dry_run=false&batch_size=50"
```

**Delete source when exact match exists (subtitle-only folders):**

```bash
# When destination exists with identical contents (only subtitles, same structure/sizes), delete source
curl -X POST "http://localhost:1968/api/v1/migrate/non-movie-folders?dry_run=false&delete_source_if_match=true"
```

**Merge missing files when destination exists:**

```bash
# Copy files from source that are not in destination, then optionally delete source
curl -X POST "http://localhost:1968/api/v1/migrate/non-movie-folders?dry_run=false&merge_missing_files=true"

# Merge and delete source after copying
curl -X POST "http://localhost:1968/api/v1/migrate/non-movie-folders?dry_run=false&merge_missing_files=true&delete_source_after_merge=true"

# Delete redundant source when nothing to merge (dest has all, source is subset)
curl -X POST "http://localhost:1968/api/v1/migrate/non-movie-folders?dry_run=false&merge_missing_files=true&delete_source_when_nothing_to_merge=true"
```

**Response format:**

```json
{
  "target_directory": "/path/to/target",
  "migrated_directory": "/path/to/migrated",
  "dry_run": true,
  "batch_size": 100,
  "delete_source_if_match": false,
  "merge_missing_files": false,
  "delete_source_after_merge": false,
  "delete_source_when_nothing_to_merge": false,
  "folders_found": 5,
  "folders_moved": 0,
  "folders_skipped": 0,
  "folders_deleted": 0,
  "folders_merged": 0,
  "files_merged": 0,
  "errors": 0,
  "batch_limit_reached": false,
  "remaining_folders": 0,
  "folders_to_migrate": ["folder1", "folder2", "folder3"],
  "moved_folders": [],
  "skipped_folders": [],
  "deleted_folders": [],
  "merged_folders": [],
  "error_details": []
}
```

**Features:**

- **Movie File Detection**: Identifies folders that contain files but no movie files based on extension list
- **Empty Folders Excluded**: Only migrates folders that contain at least one file; empty folders are left for the `/api/v1/cleanup/empty-folders` endpoint
- **First-Level Only**: Scans only immediate subdirectories of the target directory
- **Safe by Default**: Default `dry_run=true` prevents accidental moves
- **Batch Processing**: Default `batch_size=100` allows processing in batches for re-entrant operations
- **Re-entrant**: Can be called multiple times to resume from where it stopped
- **Skip Existing**: If a destination folder already exists, it is skipped (not overwritten) and logged
- **Delete Source If Match**: When `delete_source_if_match=true` and destination exists with exact contents (folder contains only subtitles, same structure and file sizes), the source folder is deleted instead of skipped
- **Merge Missing Files**: When `merge_missing_files=true` and destination exists, copies files from source that are not in destination; use `delete_source_after_merge=true` to remove the source folder after merging
- **Delete Source When Nothing To Merge**: When `merge_missing_files=true` and destination exists with no files to copy (source is subset or empty), use `delete_source_when_nothing_to_merge=true` to remove the redundant source folder
- **Error Handling**: Comprehensive error reporting for failed moves
- **Progress Tracking**: `remaining_folders` field shows how many folders still need to be processed
- **Prometheus Metrics**: Records found, moved, skipped, merged, deleted, and error metrics

**Movie File Extensions:**

The endpoint recognizes the following movie file extensions:

- `.avi`, `.mkv`, `.mp4`, `.m4v`, `.mov`, `.wmv`, `.flv`, `.webm`
- `.mpg`, `.mpeg`, `.m2v`, `.3gp`, `.ogv`, `.divx`, `.xvid`
- `.rm`, `.rmvb`, `.vob`, `.ts`, `.mts`, `.m2ts`

**How It Works:**

The migrate endpoint processes folders in a specific way to ensure safe and predictable behavior:

1. **Only First-Level Subdirectories**: The endpoint only scans immediate subdirectories of the target directory (first-level only). It does not process nested subdirectories separately.

2. **Recursive Movie File Check**: For each first-level subdirectory, the endpoint recursively checks the entire folder tree to see if it contains any movie files anywhere within it.

3. **Entire Folder Migration**: If a first-level subdirectory contains no movie files anywhere within it, the entire first-level subdirectory (including all nested content) is moved as one unit.

4. **Nested Folders Not Processed Separately**: Nested subdirectories are never processed individually - they only move as part of their parent first-level folder.

**Examples:**

**Example 1: Simple Case**

```text
/target/
  ├── folder_a/
  │   └── file.txt          ← No movie files
  └── folder_b/
      └── movie.mp4         ← Has movie file
```

- `folder_a` → **MIGRATED** (no movies found)
- `folder_b` → **NOT migrated** (has movie.mp4)

**Example 2: Nested Structure**

```text
/target/
  ├── folder_a/
  │   ├── subfolder/
  │   │   └── file.txt      ← No movie files anywhere
  │   └── readme.txt
  └── folder_b/
      ├── subfolder/
      │   └── movie.mkv    ← Has movie file
      └── file.txt
```

- `folder_a` → **MIGRATED** (entire folder_a, including subfolder, moved)
- `folder_b` → **NOT migrated** (has movie.mkv in subfolder)

**Example 3: Movie at Same Level as Nested Folder**

```text
/target/
  ├── folder_a/
  │   ├── subfolder/
  │   │   └── file.txt      ← No movie files
  │   └── movie.mp4         ← Has movie file at first level
  └── folder_b/
      └── subfolder/
          └── file.txt      ← No movie files anywhere
```

- `folder_a` → **NOT migrated** (has movie.mp4, even though subfolder has no movies)
- `folder_b` → **MIGRATED** (entire folder_b, including subfolder, moved)

**Example 4: Multiple Nested Levels**

```text
/target/
  └── folder_a/
      ├── level1/
      │   └── level2/
      │       └── level3/
      │           └── file.txt    ← No movie files anywhere
      └── readme.txt
```

- `folder_a` → **MIGRATED** (entire folder_a, including all nested levels, moved as one unit)

**Example 5: Mixed Content**

```text
/target/
  ├── folder_a/
  │   ├── file1.txt
  │   ├── file2.jpg
  │   └── subfolder/
  │       └── file3.txt     ← No movie files anywhere
  └── folder_b/
      ├── file1.txt
      └── subfolder/
          └── movie.avi     ← Has movie file
```

- `folder_a` → **MIGRATED** (no movies found anywhere in folder_a)
- `folder_b` → **NOT migrated** (has movie.avi in subfolder)

**Key Points:**

- ✅ **Only first-level subdirectories are considered** - Nested folders like `folder_a/subfolder` are never processed separately
- ✅ **Recursive movie file check** - If `folder_a` contains a movie anywhere (even deep in nested subdirectories), `folder_a` is NOT migrated
- ✅ **Entire folder moves** - If `folder_a` has no movies, the whole `folder_a` (including all nested content) is moved
- ✅ **Nested folders never move individually** - They only move as part of their parent first-level folder

This design ensures that if a first-level folder has no movie files anywhere within it, the entire folder (and all its nested content) is moved as one atomic unit, preventing partial moves and maintaining folder structure integrity.

#### Sync Subtitles to Target Usage

The sync subtitles endpoint moves subtitle files from either the salvaged or migrated movies directory into the target directory. **Only movie folders that already exist in the target and contain at least one movie file are processed** – if there is no matching movie directory in target, or the target directory has no movie file (e.g. only .nfo, .sfv), the entire folder is skipped (the movie directory is never created). For each matching movie, subtitles are placed at the equivalent path (root or `Subs/`); the `Subs` folder is created if needed. Files are only moved when the destination does not already exist. Skipped items do not count toward `batch_size`, making the operation re-entrant.

**Configuration:**

- `source` (query, required): `salvaged` or `migrated` – which directory to use as the source of subtitles
- `SALVAGED_MOVIES_DIRECTORY` – Used when `source=salvaged` (default: `/salvaged/movies`)
- `MIGRATED_MOVIES_DIRECTORY` – Used when `source=migrated` (default: `/migrated/movies`)
- `TARGET_DIRECTORY` – Destination for subtitle files (default: `/target`)

**Sync from salvaged (dry run - default):**

```bash
curl -X POST "http://localhost:1968/api/v1/sync/subtitles-to-target?source=salvaged"
```

**Sync from migrated (actual move):**

```bash
curl -X POST "http://localhost:1968/api/v1/sync/subtitles-to-target?source=migrated&dry_run=false"
```

**Use batch_size for re-entrant operations:**

```bash
# Move up to 50 files per request (skipped files don't count)
curl -X POST "http://localhost:1968/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false&batch_size=50"
```

**Include metadata files (.nfo, .sfv, .jpg, etc.):**

```bash
# Also move .nfo, .sfv, .srr, .jpg, .png, .gif in addition to subtitles
curl -X POST "http://localhost:1968/api/v1/sync/subtitles-to-target?source=salvaged&dry_run=false&include_metadata_files=true"
```

**Response format:**

```json
{
  "source": "salvaged",
  "source_directory": "/path/to/salvaged/movies",
  "target_directory": "/path/to/target",
  "dry_run": true,
  "batch_size": 100,
  "subtitle_extensions": [".srt", ".sub", ".vtt", ...],
  "include_metadata_files": false,
  "subtitle_files_moved": 0,
  "subtitle_files_skipped": 0,
  "moved_files": [],
  "skipped_files": [],
  "batch_limit_reached": false,
  "errors": 0,
  "error_details": []
}
```

**Features:**

- **Source choice**: Query param `source=salvaged` or `source=migrated` selects the subtitle source
- **Include metadata files**: When `include_metadata_files=true`, also moves .nfo, .sfv, .srr, .jpg, .png, .gif in addition to subtitles
- **Target movie must exist**: Only processes source movie folders that have a matching directory in target; skips entirely when no match (never creates movie directories)
- **Target must have movie file**: Skips target directories that have no movie file (e.g. only .nfo, .sfv, or empty); prevents syncing subtitles into orphan metadata folders
- **Equivalent path**: Preserves hierarchy; each file goes to the same relative path under target (e.g. root stays root, Subs/en.srt stays Subs/en.srt); creates `Subs` folder when needed
- **Skip existing**: Does not overwrite; if a file (or path) already exists in target, it is skipped and not counted toward `batch_size`
- **Batch processing**: `batch_size` limits how many files are moved per request (default: 100); only actually moved files count
- **Re-entrant**: Safe to call repeatedly; skipped files do not count toward the limit
- **Dry run**: Default `dry_run=true` only reports what would be moved

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

#### Subtitle Salvage Metrics

- `brronson_salvage_folders_scanned_total` - Total number of folders scanned for subtitle salvage (labels: recycled_directory, dry_run)
- `brronson_salvage_folders_with_subtitles_found` - Current number of folders found with subtitles in root (labels: recycled_directory, dry_run)
- `brronson_salvage_folders_copied_total` - Total number of folders successfully copied during salvage (labels: recycled_directory, salvaged_directory, dry_run)
- `brronson_salvage_folders_skipped_total` - Total number of folders skipped during salvage (target already exists) (labels: recycled_directory, salvaged_directory, dry_run)
- `brronson_salvage_subtitle_files_copied_total` - Total number of subtitle files copied during salvage (labels: recycled_directory, salvaged_directory, dry_run)
- `brronson_salvage_files_skipped_total` - Total number of subtitle files skipped during salvage (target already exists) (labels: recycled_directory, salvaged_directory, dry_run)
- `brronson_salvage_errors_total` - Total errors during subtitle salvage operations (labels: recycled_directory, salvaged_directory, error_type)
- `brronson_salvage_operation_duration_seconds` - Time spent on subtitle salvage operations (labels: operation_type, recycled_directory, salvaged_directory)

#### Empty Folder Cleanup Metrics

- `brronson_empty_folders_found_total` - Total number of empty folders found (labels: target_directory, dry_run)
- `brronson_empty_folders_removed_total` - Total number of empty folders successfully removed (labels: target_directory, dry_run)
- `brronson_empty_folders_errors_total` - Total errors during empty folder cleanup operations (labels: target_directory, error_type)
- `brronson_empty_folders_operation_duration_seconds` - Time spent on empty folder cleanup operations (labels: operation_type, target_directory)
- `brronson_empty_folders_batch_operations_total` - Total number of batch operations performed (labels: target_directory, batch_size, dry_run)

#### Non-Movie Folder Migration Metrics

- `brronson_migrate_folders_found_total` - Total number of folders without movie files found (labels: target_directory, dry_run)
- `brronson_migrate_folders_moved_total` - Total number of folders successfully moved to migrated directory (labels: target_directory, migrated_directory, dry_run)
- `brronson_migrate_folders_skipped_total` - Total number of folders skipped during migration (target already exists) (labels: target_directory, migrated_directory, dry_run)
- `brronson_migrate_folders_deleted_total` - Total number of source folders deleted when exact match exists in migrated (labels: target_directory, migrated_directory, dry_run)
- `brronson_migrate_errors_total` - Total errors during folder migration operations (labels: target_directory, migrated_directory, error_type)
- `brronson_migrate_operation_duration_seconds` - Time spent on folder migration operations (labels: operation_type, target_directory, migrated_directory)
- `brronson_migrate_batch_operations_total` - Total number of batch operations performed (labels: target_directory, migrated_directory, batch_size, dry_run)

#### Subtitle Sync Metrics

- `brronson_sync_subtitles_files_moved_total` - Total subtitle files moved to target (labels: source_directory, target_directory, dry_run)
- `brronson_sync_subtitles_files_skipped_total` - Total subtitle files skipped (target already exists) (labels: source_directory, target_directory, dry_run)
- `brronson_sync_subtitles_errors_total` - Total errors during subtitle sync (labels: source_directory, target_directory, error_type)
- `brronson_sync_subtitles_operation_duration_seconds` - Time spent on subtitle sync (labels: operation_type, source_directory, target_directory)
- `brronson_sync_subtitles_batch_operations_total` - Total batch operations (labels: source_directory, target_directory, batch_size, dry_run)

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
- **Timeouts**: Configurable request timeout (default: `600` seconds / 10 minutes) with 30-second graceful shutdown. Can be set via `GUNICORN_TIMEOUT` environment variable. Longer timeout allows for operations like empty folder cleanup on large directory trees.
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
- `SALVAGED_MOVIES_DIRECTORY` - Directory for salvaged movie folders with subtitles (default: `/salvaged/movies`)

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
