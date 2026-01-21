"""Health check and version endpoints."""

import time

from fastapi import APIRouter

from ..version import version

router = APIRouter()


@router.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Welcome to Brronson", "version": version}


@router.get("/version")
async def get_version():
    """Version endpoint"""
    return {
        "message": f"The current version of Brronson is {version}",
        "version": version,
    }


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "brronson",
        "version": version,
        "timestamp": time.time(),
    }
