from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from supabase import Client
from app.config import settings
from app.db.supabase_client import get_supabase_client
from app.ml.model_registry import model_registry

router = APIRouter(tags=["Health & Status"])

@router.get("/health")
def health_check():
    """Service health check endpoint for monitoring and uptime probes."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@router.get("/ready")
def readiness_check(db: Client = Depends(get_supabase_client)):
    """Comprehensive readiness probe verifying subsystems (DB, ML Registry, Gateway config)."""
    db_ok = bool(db is not None)
    ml_stat = model_registry.get_model_status()
    models_ready = bool(ml_stat.get("worker_ranking_loaded"))
    
    return {
        "status": "ready" if db_ok else "degraded",
        "subsystems": {
            "database_connected": db_ok,
            "ml_engine_loaded": models_ready,
            "payment_gateway_configured": bool(settings.RAZORPAY_KEY_ID),
            "maps_configured": bool(settings.GOOGLE_MAPS_API_KEY)
        },
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
