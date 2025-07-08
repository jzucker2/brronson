#!/usr/bin/env python3
"""
Redis Queue Worker for Bronson

This script runs a worker to process move operations from the Redis queue.
"""

import logging
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from rq import Queue, Worker

    from app.main import get_redis_connection
except ImportError:
    print(
        "Error: Could not import required modules. Make sure you're running from the project root."
    )
    sys.exit(1)


def setup_logging():
    """Setup logging for the worker"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("worker.log"),
        ],
    )


def main():
    """Main worker function"""
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting Bronson Redis Queue Worker")

    try:
        # Get Redis connection
        redis_conn = get_redis_connection()

        # Test Redis connection
        redis_conn.ping()
        logger.info("Successfully connected to Redis")

        # Create queue
        queue = Queue("move_operations", connection=redis_conn)

        # Create worker
        worker = Worker([queue], connection=redis_conn, name="bronson-worker")

        logger.info(f"Worker created: {worker.name}")
        logger.info(f"Listening to queue: {queue.name}")

        # Start the worker
        worker.work()

    except Exception as e:
        logger.error(f"Worker error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
