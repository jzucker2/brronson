# Gunicorn configuration file for Brronson FastAPI application

import multiprocessing
import os

# Get configuration from environment variables with defaults
PORT = int(os.getenv("PORT", "1968"))
WORKERS = int(
    os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1)
)
LOG_LEVEL = os.getenv("GUNICORN_LOG_LEVEL", "info").lower()

# Server socket
bind = f"0.0.0.0:{PORT}"
backlog = 2048

# Worker processes
workers = WORKERS
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
preload_app = True

# Timeout settings
timeout = 120
keepalive = 2
graceful_timeout = 30

# Logging
accesslog = "-"
errorlog = "-"
loglevel = LOG_LEVEL
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
)

# Process naming
proc_name = "brronson"

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Performance
worker_tmp_dir = "/dev/shm"
worker_exit_on_app_exit = True

# Environment variables
raw_env = [
    "PROMETHEUS_MULTIPROC_DIR=/tmp",
    "PYTHONUNBUFFERED=1",
]


# Health check endpoint for gunicorn
def when_ready(server):
    """Called just after the server is started."""
    server.log.info(
        f"Server is ready. Spawning {workers} workers on port {PORT}"
    )


def worker_int(worker):
    """Called just after a worker has been initialized."""
    worker.log.info("Worker spawned (pid: %s)", worker.pid)


def pre_fork(server, worker):
    """Called just before a worker has been forked."""
    server.log.info("Worker will be spawned")


def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)


def post_worker_init(worker):
    """Called just after a worker has initialized the application."""
    worker.log.info("Worker initialized (pid: %s)", worker.pid)


def worker_abort(worker):
    """Called when a worker received the SIGABRT signal."""
    worker.log.info("Worker received SIGABRT!")


def pre_exec(server):
    """Called just before a new master process is forked."""
    server.log.info("Forked child, re-executing.")


def on_starting(server):
    """Called just after the master process is initialized."""
    server.log.info(f"Starting server on port {PORT} with {workers} workers")


def on_reload(server):
    """Called to reload the server."""
    server.log.info("Reloading server")


def on_exit(server):
    """Called just before exiting the server."""
    server.log.info("Exiting server")
