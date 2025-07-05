# Bronson

A FastAPI application with Docker containerization, Prometheus metrics, and comprehensive unit tests.

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
   uvicorn app.main:app --reload --host 0.0.0.0 --port 1968
   ```

3. **Run tests**:

   ```bash
   # Run tests locally
   pytest

   # Or run tests in Docker
   docker build -t bronson-api .
   docker run --rm bronson-api pytest
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

## Monitoring

### Health Check

The application provides a simple health check endpoint at `/health` that includes:

- Service status (always "healthy" when the service is running)
- Service name and version
- Timestamp of the health check

### Prometheus Metrics

The application uses [prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator) to automatically collect and expose the following Prometheus metrics:

- `requests_total` - Total HTTP requests with method, handler, and status labels
- `request_duration_seconds` - HTTP request latency with method and handler labels
- `request_size_bytes` - Size of incoming requests
- `response_size_bytes` - Size of outgoing responses
- `http_requests_inprogress` - Number of requests currently being processed

The metrics endpoint is automatically exposed at `/metrics` and supports gzip compression for efficient data transfer.

### Viewing Metrics

You can view the Prometheus metrics directly at <http://localhost:1968/metrics> or use any Prometheus-compatible monitoring system to scrape this endpoint.

## Testing

### Running Tests

```bash
# Install dependencies (choose one):
pip install -r requirements.txt          # Production + test deps
pip install -r requirements-dev.txt      # Production + dev + test deps

# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run specific test file
pytest tests/test_main.py

# Run tests with coverage
pytest --cov=app

# Run tests in Docker
docker build -t bronson-api .
docker run --rm bronson-api pytest
```

### Test Structure

- `tests/test_main.py` - Main API endpoint and metrics tests
- Tests cover:
  - API endpoint functionality
  - Prometheus metrics generation
  - Error handling
  - Response formats

## Development

### Code Quality and Linting

This project uses several tools to ensure code quality and consistency:

#### Automatic Linting Setup

1. **Pre-commit Hooks** (Recommended)
   - Automatically runs linting checks before each commit
   - Installed with: `make pre-commit-install`
   - Runs: black formatting, flake8 linting, trailing whitespace removal
   - If hooks fail, the commit is blocked until issues are fixed

2. **VS Code Integration**
   - Automatic formatting on save
   - Real-time linting error display
   - Import organization on save
   - Settings configured in `.vscode/settings.json`

3. **Manual Commands**

   ```bash
   make format      # Format code with black
   make lint        # Check code with flake8
   make lint-fix    # Auto-fix linting issues where possible
   make check       # Run both format and lint
   make ci-check    # Run all CI checks (pre-commit + tests)
   ```

#### Linting Rules

- **Line length**: 79 characters maximum
- **Formatter**: Black (uncompromising)
- **Linter**: Flake8 with custom configuration
- **Auto-fixing**: Available for whitespace and basic formatting issues

#### Best Practices

1. **Always run `make check` before committing**
2. **Use pre-commit hooks** to catch issues automatically
3. **Fix linting errors immediately** when they appear
4. **Use `make lint-fix`** for automatic fixes when possible

### Project Structure

```
bronson/
├── app/
│   ├── __init__.py
│   └── main.py          # FastAPI application
├── tests/
│   ├── __init__.py
│   └── test_main.py     # Unit tests
├── Dockerfile           # Docker configuration
├── docker-compose.yml   # Docker Compose configuration
├── requirements.txt     # Python dependencies
├── pytest.ini          # Pytest configuration
└── README.md           # This file
```

### Environment Variables

- `PROMETHEUS_MULTIPROC_DIR` - Directory for Prometheus multiprocess metrics (set to `/tmp` in Docker)
- `ENABLE_METRICS` - Set to `true` to enable Prometheus metrics collection (default: enabled)
- `CLEANUP_DIRECTORY` - Directory to scan and clean for unwanted files (default: `/tmp`)
- `TARGET_DIRECTORY` - Directory to compare with CLEANUP_DIRECTORY for duplicates (default: `/tmp`)

### Building Docker Image

```bash
docker build -t bronson-api .
```

### Docker Health Checks

The Docker image includes built-in health checks that:

- Run every 30 seconds
- Check the `/health` endpoint
- Consider the container healthy if the health check passes
- Retry up to 3 times before marking as unhealthy

You can check the health status with:

```bash
docker ps  # Shows health status
docker inspect <container_id>  # Shows detailed health check info
```

### Running Individual Services

```bash
# Run only the FastAPI app
docker-compose up app

# Run the application
docker-compose up app
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## License

This project is licensed under the MIT License.
