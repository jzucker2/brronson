from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator, metrics
import time
from .version import version

app = FastAPI(title="Bronson", version=version)


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create Prometheus instrumentator
instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_respect_env_var=False,  # Disable env var requirement for testing
    should_instrument_requests_inprogress=True,
    excluded_handlers=[".*admin.*", "/metrics"],
    env_var_name="ENABLE_METRICS",
    inprogress_name="http_requests_inprogress",
    inprogress_labels=True,
)

# Add default metrics
instrumentator.add(metrics.latency(buckets=(0.1, 0.5, 1.0, 2.0, 5.0)))
instrumentator.add(metrics.request_size())
instrumentator.add(metrics.response_size())
instrumentator.instrument(app).expose(
    app, include_in_schema=False, should_gzip=True)


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Welcome to Bronson", "version": version}


@app.get("/version")
async def get_version():
    """Version endpoint"""
    return {"message": f"The current version of the Bronson is {version}", "version": version}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "bronson",
        "version": version,
        "timestamp": time.time(),
    }


@app.get("/api/v1/items")
async def get_items():
    """Get list of items"""
    return {"items": ["item1", "item2", "item3"]}


@app.post("/api/v1/items")
async def create_item(item: dict):
    """Create a new item"""
    return {"message": "Item created", "item": item}


@app.get("/api/v1/items/{item_id}")
async def get_item(item_id: int):
    """Get a specific item by ID"""
    return {"item_id": item_id, "name": f"Item {item_id}"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=1968)
