from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client import CollectorRegistry, multiprocess
import time
import os

# Create a custom registry for multiprocess support
registry = CollectorRegistry()
multiprocess.MultiProcessCollector(registry)

# Prometheus metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status'],
    registry=registry
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint'],
    registry=registry
)

app = FastAPI(title="Bronson API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    start_time = time.time()
    
    response = await call_next(request)
    
    # Record metrics
    duration = time.time() - start_time
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)
    
    return response

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Welcome to Bronson API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "bronson-api"}

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

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
    uvicorn.run(app, host="0.0.0.0", port=8000) 