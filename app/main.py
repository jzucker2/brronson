from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator, metrics
import time
import os
import re
from pathlib import Path
from typing import List, Optional
from .version import version


def get_cleanup_directory():
    """Get the cleanup directory from environment variable"""
    return os.getenv("CLEANUP_DIRECTORY", "/tmp")


app = FastAPI(title="Bronson", version=version)

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
    # should_group_status_codes=False,
    # should_ignore_untemplated=True,
    should_respect_env_var=False,  # Disable env var requirement for testing
    should_instrument_requests_inprogress=True,
    excluded_handlers=[".*admin.*", "/metrics"],
)

instrumentator.add(metrics.request_size())
instrumentator.add(metrics.response_size())
instrumentator.instrument(app).expose(
    app, include_in_schema=False, should_gzip=True
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Welcome to Bronson", "version": version}


@app.get("/version")
async def get_version():
    """Version endpoint"""
    return {
        "message": f"The current version of Bronson is {version}",
        "version": version,
    }


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


@app.post("/api/v1/cleanup/files")
async def cleanup_unwanted_files(
    dry_run: bool = True, patterns: Optional[List[str]] = Body(None)
):
    """
    Recursively search the configured directory and remove unwanted files.

    Args:
        dry_run: If True, only show what would be deleted (default: True)
        patterns: List of regex patterns to match unwanted files
    """
    if patterns is None:
        # Default patterns for common unwanted files
        patterns = [
            r"www\.YTS\.MX\.jpg$",
            r"YIFYStatus\.com\.txt$",
            r"\.DS_Store$",
            r"Thumbs\.db$",
            r"desktop\.ini$",
            r"\.tmp$",
            r"\.temp$",
            r"\.log$",
            r"\.cache$",
            r"\.bak$",
            r"\.backup$",
        ]

    # Use the configured cleanup directory
    cleanup_dir = get_cleanup_directory()
    try:
        directory_path = Path(cleanup_dir).resolve()
        if not directory_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Configured cleanup directory {cleanup_dir} not found",
            )

        # Security check: prevent deletion from critical system directories
        critical_dirs = [
            "/",
            "/home",
            "/usr",
            "/etc",
            "/var",
            "/bin",
            "/sbin",
            "/boot",
            "/root",
        ]
        dir_str = str(directory_path)
        # Allow /tmp, /private/tmp, and /private/var and their subdirectories
        allowed_tmp_paths = [
            str(Path(p).resolve())
            for p in ["/tmp", "/private/tmp", "/private/var"]
        ]
        if any(
            dir_str == tmp_path or dir_str.startswith(tmp_path + "/")
            for tmp_path in allowed_tmp_paths
        ):
            pass  # temp dirs are allowed
        else:
            for sys_dir in critical_dirs:
                sys_dir_path = str(Path(sys_dir).resolve())
                if dir_str == sys_dir_path or dir_str.startswith(
                    sys_dir_path + "/"
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="Configured cleanup directory is in a protected "  # noqa: E501
                        "system location",
                    )

    except Exception as e:  # noqa: E501
        msg = (
            "Invalid cleanup directory: "
            f"{str(e)}"
        )
        raise HTTPException(
            status_code=400,
            detail=msg
        )

    found_files = []
    removed_files = []
    errors = []

    try:
        # Walk through directory recursively
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = Path(root) / file

                # Check if file matches any unwanted pattern
                for pattern in patterns:
                    if re.search(pattern, file, re.IGNORECASE):
                        found_files.append(str(file_path))

                        if not dry_run:
                            try:
                                file_path.unlink()
                                removed_files.append(str(file_path))
                            except Exception as e:
                                errors.append(
                                    f"Failed to remove {file_path}: {str(e)}"
                                )
                        break

        return {
            "directory": str(directory_path),
            "dry_run": dry_run,
            "patterns_used": patterns,
            "files_found": len(found_files),
            "files_removed": len(removed_files),
            "errors": len(errors),
            "found_files": found_files,
            "removed_files": removed_files,
            "error_details": errors,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error during cleanup: {str(e)}"
        )


@app.get("/api/v1/cleanup/scan")
async def scan_for_unwanted_files(patterns: List[str] = None):
    """
    Scan the configured directory for unwanted files without removing them.

    Args:
        patterns: List of regex patterns to match unwanted files
    """
    if patterns is None:
        # Default patterns for common unwanted files
        patterns = [
            r"www\.YTS\.MX\.jpg$",
            r"YIFYStatus\.com\.txt$",
            r"\.DS_Store$",
            r"Thumbs\.db$",
            r"desktop\.ini$",
            r"\.tmp$",
            r"\.temp$",
            r"\.log$",
            r"\.cache$",
            r"\.bak$",
            r"\.backup$",
        ]

    # Use the configured cleanup directory
    cleanup_dir = get_cleanup_directory()
    try:
        directory_path = Path(cleanup_dir).resolve()
        if not directory_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Configured cleanup directory {cleanup_dir} not found",
            )

        # Security check: prevent scanning critical system directories
        critical_dirs = [
            "/",
            "/home",
            "/usr",
            "/etc",
            "/var",
            "/bin",
            "/sbin",
            "/boot",
            "/root",
        ]
        dir_str = str(directory_path)
        # Allow /tmp, /private/tmp, and /private/var and their subdirectories
        allowed_tmp_paths = [
            str(Path(p).resolve())
            for p in ["/tmp", "/private/tmp", "/private/var"]
        ]
        if any(
            dir_str == tmp_path or dir_str.startswith(tmp_path + "/")
            for tmp_path in allowed_tmp_paths
        ):
            pass  # temp dirs are allowed
        else:
            for sys_dir in critical_dirs:
                sys_dir_path = str(Path(sys_dir).resolve())
                if dir_str == sys_dir_path or dir_str.startswith(
                    sys_dir_path + "/"
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="Configured cleanup directory is in a protected "  # noqa: E501
                        "system location",
                    )

    except Exception as e:  # noqa: E501
        msg = (
            "Invalid cleanup directory: "
            f"{str(e)}"
        )
        raise HTTPException(
            status_code=400,
            detail=msg
        )

    found_files = []
    file_sizes = {}

    try:
        # Walk through directory recursively
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = Path(root) / file

                # Check if file matches any unwanted pattern
                for pattern in patterns:
                    if re.search(pattern, file, re.IGNORECASE):
                        found_files.append(str(file_path))
                        try:
                            file_sizes[str(file_path)] = (
                                file_path.stat().st_size
                            )
                        except Exception:
                            file_sizes[str(file_path)] = 0
                        break

        total_size = sum(file_sizes.values())

        return {
            "directory": str(directory_path),
            "patterns_used": patterns,
            "files_found": len(found_files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "found_files": found_files,
            "file_sizes": file_sizes,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error during scan: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=1968)
