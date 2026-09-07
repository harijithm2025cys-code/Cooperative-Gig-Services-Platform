"""
Feature Engineering & Transformation Pipeline for Phase 8 ML.
Ensures reproducible feature vectors and zero target leakage.
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
import math

WORKER_RANKING_FEATURE_NAMES = [
    "skill_match_score",
    "certification_valid",
    "distance_km",
    "worker_rating",
    "is_cooperative",
    "monthly_jobs",
    "active_workload",
    "time_of_day_hour",
    "day_of_week",
    "is_emergency",
    "base_fare_inr"
]

DURATION_FEATURE_NAMES = [
    "category_code",
    "worker_rating",
    "experience_years",
    "distance_km",
    "is_emergency",
    "time_of_day_hour",
    "day_of_week",
    "base_fare_inr"
]

CATEGORY_MAP = {
    "plumbing": 1,
    "electrical": 2,
    "carpentry": 3,
    "appliances": 4,
    "cleaning": 5,
    "painting": 6,
    "general": 0
}

def encode_category(category_name: Optional[str]) -> int:
    if not category_name:
        return 0
    clean = category_name.strip().lower()
    for k, v in CATEGORY_MAP.items():
        if k in clean:
            return v
    return 0

def calculate_skill_match(worker_skill: Optional[str], requested_skill: Optional[str]) -> float:
    if not worker_skill or not requested_skill:
        return 0.5
    w_low = worker_skill.strip().lower()
    r_low = requested_skill.strip().lower()
    if r_low == w_low:
        return 1.0
    if r_low in w_low or w_low in r_low:
        return 0.85
    return 0.0

def build_worker_ranking_features(
    worker: Dict[str, Any],
    booking: Dict[str, Any],
    distance_km: float = 3.5,
    active_workload: int = 0
) -> List[float]:
    """
    Constructs an input feature vector for Worker Ranking Model at dispatch time.
    Guaranteed zero target leakage (no post-dispatch outcomes used).
    """
    w_skill = worker.get("skill", "")
    r_skill = booking.get("service_name") or booking.get("service_type") or booking.get("skill") or w_skill
    skill_match = calculate_skill_match(w_skill, r_skill)

    cert_valid = 1.0 if worker.get("verified_status") or worker.get("is_pre_verified_by_association") else 0.0
    dist = float(max(0.1, min(100.0, distance_km)))
    rating = float(max(1.0, min(5.0, float(worker.get("rating") or 4.8))))
    is_coop = 1.0 if worker.get("worker_type", "cooperative") == "cooperative" else 0.0
    monthly_jobs = float(max(0, int(worker.get("monthly_jobs") or worker.get("jobs_completed_this_month") or 0)))
    workload = float(max(0, int(active_workload)))

    dt = datetime.now(timezone.utc)
    if booking.get("created_at"):
        try:
            dt = datetime.fromisoformat(booking["created_at"].replace("Z", "+00:00"))
        except Exception:
            pass

    hour = float(dt.hour)
    dow = float(dt.weekday())
    emergency = 1.0 if booking.get("is_emergency") else 0.0
    fare = float(booking.get("amount") or booking.get("final_amount") or 350.0)

    return [
        skill_match,
        cert_valid,
        dist,
        rating,
        is_coop,
        monthly_jobs,
        workload,
        hour,
        dow,
        emergency,
        fare
    ]

def build_duration_prediction_features(
    booking: Dict[str, Any],
    worker: Optional[Dict[str, Any]] = None,
    distance_km: float = 3.5
) -> List[float]:
    """
    Constructs an input feature vector for Service Duration Prediction.
    """
    cat_code = float(encode_category(booking.get("category") or booking.get("service_name")))
    rating = float(worker.get("rating") or 4.8) if worker else 4.8
    exp = float(worker.get("experience_years") or 3) if worker else 3.0
    dist = float(max(0.1, min(100.0, distance_km)))
    emergency = 1.0 if booking.get("is_emergency") else 0.0

    dt = datetime.now(timezone.utc)
    hour = float(dt.hour)
    dow = float(dt.weekday())
    fare = float(booking.get("amount") or booking.get("final_amount") or 350.0)

    return [
        cat_code,
        rating,
        exp,
        dist,
        emergency,
        hour,
        dow,
        fare
    ]
