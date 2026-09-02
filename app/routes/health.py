from datetime import datetime, timezone
from fastapi import APIRouter
from app.config import settings

router = APIRouter(tags=["Health & Status"])

@router.get("/health")
def health_check():
    """Service health check endpoint for monitoring and Render uptime checks."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@router.get("/")
def root_status():
    """Root metadata endpoint."""
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "version": settings.VERSION,
        "docs_url": "/docs",
        "status": "operational"
    }
