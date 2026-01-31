"""Main FastAPI application for Brronson."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator, metrics

from . import logging_config  # noqa: F401 - Import to setup logging
from .config import get_cleanup_directory, get_target_directory
from .metrics import brronson_info
from .routes import (
    cleanup,
    comparison,
    empty_folders,
    health,
    migrate,
    move,
    salvage,
    subtitle_sync,
)
from .version import version

logger = logging.getLogger(__name__)

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

# Register routes
app.include_router(health.router)
app.include_router(cleanup.router)
app.include_router(comparison.router)
app.include_router(move.router)
app.include_router(salvage.router)
app.include_router(empty_folders.router)
app.include_router(migrate.router)
app.include_router(subtitle_sync.router)

if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Brronson server on 0.0.0.0:1968")
    uvicorn.run(app, host="0.0.0.0", port=1968)
