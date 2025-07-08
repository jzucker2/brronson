#!/usr/bin/env python3
"""
Simple test script to verify Redis queue functionality
"""

import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from app.main import (
        execute_move_operation,
        get_move_queue,
        get_redis_connection,
    )
except ImportError:
    print(
        "Error: Could not import app.main. Make sure you're running from the project root."
    )
    sys.exit(1)


def test_redis_connection():
    """Test Redis connection"""
    print("Testing Redis connection...")
    try:
        redis_conn = get_redis_connection()
        redis_conn.ping()
        print("✓ Redis connection successful")
        return True
    except Exception as e:
        print(f"✗ Redis connection failed: {e}")
        return False


def test_queue_operations():
    """Test queue operations"""
    print("\nTesting queue operations...")
    try:
        queue = get_move_queue()
        print(f"✓ Queue created: {queue.name}")

        # Test enqueueing a job
        test_data = {
            "operation_id": "test-123",
            "subdir_name": "test_dir",
            "source_path": "/tmp/test_source",
            "target_path": "/tmp/test_target",
            "dry_run": True,
        }

        job = queue.enqueue(
            execute_move_operation,
            test_data,
            job_id="test-123",
            job_timeout="1h",
        )
        print(f"✓ Job enqueued: {job.id}")

        # Check queue size
        queue_size = len(queue)
        print(f"✓ Queue size: {queue_size}")

        return True
    except Exception as e:
        print(f"✗ Queue operations failed: {e}")
        return False


def main():
    """Main test function"""
    print("Redis Queue Test")
    print("=" * 50)

    # Test Redis connection
    if not test_redis_connection():
        print("\nPlease start Redis server first:")
        print("docker run -d -p 6379:6379 redis:7-alpine")
        return

    # Test queue operations
    if not test_queue_operations():
        return

    print("\n✓ All tests passed!")
    print("\nTo start the worker:")
    print("python worker.py")


if __name__ == "__main__":
    main()
