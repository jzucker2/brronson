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
   - FastAPI App: http://localhost:8000
   - API Documentation: http://localhost:8000/docs
   - Prometheus Metrics: http://localhost:8000/metrics

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
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
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
- `GET /health` - Health check endpoint
- `GET /metrics` - Prometheus metrics endpoint

### API v1 Endpoints

- `GET /api/v1/items` - Get list of items
- `POST /api/v1/items` - Create a new item
- `GET /api/v1/items/{item_id}` - Get a specific item by ID

## Monitoring

### Prometheus Metrics

The application exposes the following Prometheus metrics:

- `http_requests_total` - Total HTTP requests with method, endpoint, and status labels
- `http_request_duration_seconds` - HTTP request latency with method and endpoint labels

### Viewing Metrics

You can view the Prometheus metrics directly at http://localhost:8000/metrics or use any Prometheus-compatible monitoring system to scrape this endpoint.

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

### Building Docker Image

```bash
docker build -t bronson-api .
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
