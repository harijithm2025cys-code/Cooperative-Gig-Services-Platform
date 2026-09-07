"""
Phase 8 Machine Learning Router: Worker Ranking, Service Duration Prediction,
Demand Forecasting, Model Health Telemetry, and Evaluation Metrics.
"""
import time
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.dependencies import get_current_user
from app.ml.inference import (
    predict_worker_suitability,
    predict_service_duration,
    forecast_service_demand
)
from app.ml.fallback import compute_hybrid_matching_score
from app.ml.model_registry import model_registry
from app.ml.train_pipeline import run_training_pipeline
from app.services.matching import evaluate_worker_eligibility, calculate_worker_score

logger = logging.getLogger("ml_router")

router = APIRouter(prefix="/ml", tags=["Phase 8 Machine Learning & Intelligence"])

# ---------------------------------------------------------------------------
# Multi-tenant Scoping Helper
# ---------------------------------------------------------------------------
def _enforce_coop_access(current_user: dict, requested_coop_id: Optional[str]) -> Optional[str]:
    user_role = (current_user.get("role") or current_user.get("token_role") or "").lower()
    user_coop = current_user.get("cooperative_id")

    if user_role == "super_admin":
        return requested_coop_id

    if user_role in ["cooperative_association_head", "admin"]:
        if not user_coop:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is not affiliated with any Cooperative Society."
            )
        if requested_coop_id and str(requested_coop_id) != str(user_coop):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. You are authorized only for Cooperative Society '{user_coop}'."
            )
        return str(user_coop)

    # Customer and worker roles can access general ML endpoints (like duration prediction)
    return requested_coop_id

# ---------------------------------------------------------------------------
# Request/Response Schemas
# ---------------------------------------------------------------------------
class WorkerCandidate(BaseModel):
    id: str
    name: Optional[str] = "Worker"
    skill: str
    rating: Optional[float] = 4.8
    experience_years: Optional[int] = 3
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: Optional[bool] = True
    is_available: Optional[bool] = True
    availability_status: Optional[str] = "available"
    verified_status: Optional[bool] = True
    cooperative_id: Optional[str] = None
    worker_type: Optional[str] = "cooperative"
    active_workload: Optional[int] = 0
    monthly_jobs: Optional[int] = 0
    certifications: Optional[List[str]] = []

class BookingContext(BaseModel):
    booking_id: Optional[str] = None
    service_name: str
    category: Optional[str] = None
    customer_lat: float = 12.9716
    customer_lng: float = 77.5946
    is_emergency: Optional[bool] = False
    target_cooperative_id: Optional[str] = None
    required_certification: Optional[str] = None
    amount: Optional[float] = 350.0

class WorkerRankingRequest(BaseModel):
    booking: BookingContext
    candidates: List[WorkerCandidate]

class DurationPredictionRequest(BaseModel):
    service_name: str
    category: Optional[str] = None
    is_emergency: Optional[bool] = False
    worker_rating: Optional[float] = 4.8
    experience_years: Optional[int] = 3
    distance_km: Optional[float] = 3.5
    amount: Optional[float] = 350.0

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/worker-ranking", summary="Predict ML Suitability & Hybrid Ranking for Candidate Workers")
def rank_workers_endpoint(
    req: WorkerRankingRequest,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Evaluates candidate workers against hard eligibility constraints first,
    then applies Phase 8 Machine Learning Suitability Inference + Deterministic Hybrid Scoring.
    """
    start_time = time.time()
    b = req.booking
    req_coop = _enforce_coop_access(current_user, b.target_cooperative_id)

    eligible_candidates = []
    rejected_candidates = []

    for c in req.candidates:
        w_dict = c.dict()
        is_eligible, rej_reason, dist_km = evaluate_worker_eligibility(
            worker=w_dict,
            requested_skill=b.service_name,
            target_cooperative_id=req_coop,
            required_certification=b.required_certification,
            customer_lat=b.customer_lat,
            customer_lng=b.customer_lng
        )

        if not is_eligible:
            rejected_candidates.append({
                "worker_id": c.id,
                "name": c.name,
                "is_eligible": False,
                "rejection_reason": rej_reason,
                "distance_km": dist_km if dist_km < 900 else None
            })
            continue

        # Rule score calculation
        rule_res = calculate_worker_score(
            worker_skill=c.skill,
            requested_skill=b.service_name,
            worker_lat=c.latitude,
            worker_lng=c.longitude,
            request_lat=b.customer_lat,
            request_lng=b.customer_lng,
            worker_rating=c.rating or 4.8,
            active_bookings_count=c.active_workload or 0,
            is_cooperative_worker=(c.worker_type != "independent"),
            monthly_jobs_completed=c.monthly_jobs or 0,
            experience_years=c.experience_years or 3,
            is_emergency=b.is_emergency or False
        )

        # ML Suitability Inference
        ml_res = predict_worker_suitability(
            worker=w_dict,
            booking=b.dict(),
            distance_km=rule_res["distance_km"],
            active_workload=c.active_workload or 0
        )

        # Hybrid Matching Calculation
        hybrid_res = compute_hybrid_matching_score(
            rule_score=rule_res["total_score"],
            ml_suitability=ml_res.get("suitability_score", 0.5),
            fairness_points=rule_res["fairness_points"],
            confidence=ml_res.get("confidence", 0.85),
            fallback_forced=ml_res.get("is_fallback", False)
        )

        eligible_candidates.append({
            "worker_id": c.id,
            "name": c.name,
            "skill": c.skill,
            "cooperative_id": c.cooperative_id,
            "rating": c.rating,
            "distance_km": rule_res["distance_km"],
            "hybrid_score": hybrid_res["hybrid_score"],
            "rule_score": hybrid_res["rule_score"],
            "ml_score": hybrid_res["ml_score"],
            "ml_confidence": hybrid_res["confidence"],
            "ml_version": ml_res.get("model_version", "worker-ranking-v1"),
            "fallback_used": hybrid_res["fallback_used"],
            "fallback_reason": hybrid_res.get("fallback_reason"),
            "breakdown": {
                "rule_points": rule_res,
                "hybrid_weights": {
                    "rule_weight": 0.45,
                    "ml_weight": 0.35,
                    "fairness_weight": 0.20
                }
            }
        })

    # Sort eligible candidates descending by hybrid score
    eligible_candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)
    latency = round((time.time() - start_time) * 1000, 2)

    return {
        "success": True,
        "booking_service": b.service_name,
        "eligible_candidate_count": len(eligible_candidates),
        "rejected_candidate_count": len(rejected_candidates),
        "ranked_candidates": eligible_candidates,
        "rejected_candidates": rejected_candidates,
        "telemetry": {
            "model_version": "worker-ranking-v1",
            "latency_ms": latency,
            "cooperative_filtered": bool(req_coop)
        }
    }

@router.post("/duration-prediction", summary="Predict Estimated Service Duration in Minutes")
def predict_duration_endpoint(
    req: DurationPredictionRequest,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Predicts service duration in minutes for planning, dispatch windows, and customer ETAs.
    """
    booking_dict = {
        "service_name": req.service_name,
        "category": req.category or req.service_name,
        "is_emergency": req.is_emergency,
        "amount": req.amount
    }
    worker_dict = {
        "rating": req.worker_rating,
        "experience_years": req.experience_years
    }
    res = predict_service_duration(
        booking=booking_dict,
        worker=worker_dict,
        distance_km=req.distance_km or 3.5
    )
    return {
        "success": True,
        "service_name": req.service_name,
        "prediction": res
    }

@router.get("/demand-forecast", summary="7-Day Service Demand Forecast & Workforce Allocation")
def demand_forecast_endpoint(
    cooperative_id: Optional[str] = Query(None, description="Optional target cooperative"),
    district: Optional[str] = Query("Chennai North", description="Target administrative district"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Provides a 7-day projected service demand forecast, peak busy hours,
    and workforce allocation recommendations scoped to the requesting role.
    """
    scoped_coop = _enforce_coop_access(current_user, cooperative_id)
    forecast_data = forecast_service_demand(
        cooperative_id=scoped_coop,
        district=district
    )
    return forecast_data

@router.get("/model-status", summary="Real-Time Health & Operational Telemetry of ML Models")
def model_status_endpoint(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Returns the loaded status, inference volume, fallback rate, and version metadata of all ML models.
    """
    return model_registry.get_model_status()

@router.get("/model-metrics", summary="Offline Evaluation Metrics of Trained ML Models")
def model_metrics_endpoint(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Returns offline evaluation benchmarks:
    - Worker Ranking: Accuracy, Precision, Recall, F1, Top-1/Top-3 Ranking Accuracy
    - Duration Prediction: MAE, RMSE, R²
    - Demand Forecast: WAPE, RMSE, Peak Accuracy
    """
    return model_registry.get_offline_metrics()

@router.post("/train", summary="Trigger On-Demand Retraining Pipeline (Super Admin Only)")
def trigger_retraining_endpoint(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Retrains ML models on real historical data + labeled synthetic baseline.
    Restricted strictly to Super Admin.
    """
    user_role = (current_user.get("role") or current_user.get("token_role") or "").lower()
    if user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Super Administrators can trigger machine learning model retraining."
        )

    pipeline_result = run_training_pipeline()
    return pipeline_result
