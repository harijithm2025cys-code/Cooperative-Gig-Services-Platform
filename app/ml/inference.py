"""
Unified Inference API & Runtime Execution Engine for Phase 8 ML.
"""
import logging
from typing import Dict, Any, List, Optional
from app.ml.model_registry import model_registry

logger = logging.getLogger("ml_inference")

def predict_worker_suitability(
    worker: Dict[str, Any],
    booking: Dict[str, Any],
    distance_km: float = 3.5,
    active_workload: int = 0
) -> Dict[str, Any]:
    """
    Predicts candidate worker suitability for a specific booking.
    Safe against exceptions: automatically falls back if anything fails.
    """
    try:
        res = model_registry.worker_ranking_model.predict_suitability(
            worker=worker,
            booking=booking,
            distance_km=distance_km,
            active_workload=active_workload
        )
        model_registry.record_inference(is_fallback=res.get("is_fallback", False))
        return res
    except Exception as e:
        logger.warning(f"Worker ranking inference fallback triggered: {e}")
        model_registry.record_inference(is_fallback=True)
        # Deterministic fallback score
        rating = float(worker.get("rating") or 4.8)
        dist_factor = max(0.0, 1.0 - (distance_km / 30.0))
        return {
            "suitability_score": round(0.5 * (rating / 5.0) + 0.5 * dist_factor, 3),
            "confidence": 0.45,
            "model_version": "fallback-heuristic-v1",
            "is_fallback": True,
            "explanation": {"error": str(e), "fallback_reason": "exception_recovery"}
        }

def predict_service_duration(
    booking: Dict[str, Any],
    worker: Optional[Dict[str, Any]] = None,
    distance_km: float = 3.5
) -> Dict[str, Any]:
    """
    Predicts estimated duration in minutes for planning and customer ETAs.
    """
    try:
        return model_registry.duration_model.predict_duration(
            booking=booking,
            worker=worker,
            distance_km=distance_km
        )
    except Exception as e:
        logger.warning(f"Duration prediction fallback triggered: {e}")
        base_mins = 45.0 if booking.get("is_emergency") else 75.0
        return {
            "predicted_duration_minutes": base_mins,
            "duration_range_minutes": [30.0, 90.0],
            "confidence": 0.50,
            "model_version": "fallback-heuristic-v1",
            "is_fallback": True
        }

def forecast_service_demand(
    cooperative_id: Optional[str] = None,
    district: Optional[str] = "Chennai North"
) -> Dict[str, Any]:
    """
    Generates 7-day upcoming demand forecast and workforce recommendations.
    """
    try:
        return model_registry.demand_model.forecast_next_7_days(
            cooperative_id=cooperative_id,
            district=district
        )
    except Exception as e:
        logger.warning(f"Demand forecast fallback triggered: {e}")
        return {
            "success": True,
            "model_version": "fallback-baseline-v1",
            "forecast_type": "BASELINE FORECAST",
            "is_baseline_fallback": True,
            "district": district,
            "cooperative_id": cooperative_id,
            "forecast_horizon_days": 7,
            "confidence_score": 0.50,
            "seven_day_projections": [],
            "workforce_recommendations": []
        }
