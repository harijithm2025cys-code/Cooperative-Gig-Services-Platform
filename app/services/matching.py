import math
from typing import List, Dict, Any, Optional

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on the Earth in kilometers.
    Uses the standard Haversine formula.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 999.0  # Return large distance if coordinates are missing

    # Earth radius in kilometers
    R = 6371.0
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    
    return round(R * c, 2)

def calculate_worker_score(
    worker_skill: Optional[str],
    requested_skill: Optional[str],
    worker_lat: Optional[float],
    worker_lng: Optional[float],
    request_lat: Optional[float],
    request_lng: Optional[float],
    worker_rating: float = 0.0,
    active_bookings_count: int = 0
) -> Dict[str, Any]:
    """
    Calculate the multi-factor weighted match score for a worker candidate.
    
    Formula:
        Score = (skill_match * 50) + max(0, 20 - distance_km) + (rating * 5) - (active_bookings * 3)
    
    Returns a dict containing the individual point components and total score.
    """
    # 1. Skill Match (50 points maximum)
    skill_match_flag = 0
    if worker_skill and requested_skill:
        ws = worker_skill.strip().lower()
        rs = requested_skill.strip().lower()
        if rs in ws or ws in rs:
            skill_match_flag = 1
    
    skill_points = 50.0 * skill_match_flag

    # 2. Distance Score (20 points maximum, 0 if distance >= 20km)
    if (worker_lat is not None and worker_lng is not None and 
        request_lat is not None and request_lng is not None):
        distance_km = haversine_distance(request_lat, request_lng, worker_lat, worker_lng)
        distance_points = max(0.0, 20.0 - distance_km)
    else:
        distance_km = 999.0
        distance_points = 0.0

    # 3. Rating Score (Rating * 5 points, max 25 for 5.0 rating)
    rating_val = float(worker_rating) if worker_rating is not None else 0.0
    # Clamping rating between 0 and 5
    rating_val = max(0.0, min(5.0, rating_val))
    rating_points = rating_val * 5.0

    # 4. Active Bookings Penalty (-(active_bookings * 3) points)
    active_count = max(0, int(active_bookings_count or 0))
    active_penalty = active_count * 3.0

    # Total Score
    total_score = skill_points + distance_points + rating_points - active_penalty

    return {
        "skill_match_points": round(skill_points, 2),
        "distance_points": round(distance_points, 2),
        "rating_points": round(rating_points, 2),
        "active_bookings_penalty": round(active_penalty, 2),
        "total_score": round(total_score, 2),
        "distance_km": distance_km,
        "is_skill_match": bool(skill_match_flag),
        "active_bookings_count": active_count
    }

def rank_workers_for_booking(
    requested_skill: str,
    request_lat: float,
    request_lng: float,
    available_workers: List[Dict[str, Any]],
    worker_active_counts: Optional[Dict[str, int]] = None
) -> List[Dict[str, Any]]:
    """
    Ranks a list of candidate workers against a booking request using calculate_worker_score.
    Returns the candidates sorted by total score in descending order.
    """
    active_counts = worker_active_counts or {}
    scored_candidates = []

    for worker in available_workers:
        worker_id = str(worker.get("id"))
        w_skill = worker.get("skill", "")
        w_lat = worker.get("latitude")
        w_lng = worker.get("longitude")
        w_rating = float(worker.get("rating") or 0.0)
        active_cnt = active_counts.get(worker_id, 0)

        score_res = calculate_worker_score(
            worker_skill=w_skill,
            requested_skill=requested_skill,
            worker_lat=w_lat,
            worker_lng=w_lng,
            request_lat=request_lat,
            request_lng=request_lng,
            worker_rating=w_rating,
            active_bookings_count=active_cnt
        )

        user_info = worker.get("users") or {}
        coop_info = worker.get("cooperatives") or {}

        scored_candidates.append({
            "worker_id": worker_id,
            "user_id": worker.get("user_id"),
            "name": user_info.get("name") or user_info.get("email", "Worker"),
            "phone": user_info.get("phone"),
            "skill": w_skill,
            "cooperative_id": worker.get("cooperative_id"),
            "cooperative_name": coop_info.get("name") if isinstance(coop_info, dict) else None,
            "rating": w_rating,
            "verified_status": bool(worker.get("verified_status", False)),
            "availability": bool(worker.get("availability", True)),
            "distance_km": score_res["distance_km"],
            "current_active_bookings": active_cnt,
            "score": score_res["total_score"],
            "breakdown": {
                "skill_match_points": score_res["skill_match_points"],
                "distance_points": score_res["distance_points"],
                "rating_points": score_res["rating_points"],
                "active_bookings_penalty": score_res["active_bookings_penalty"],
                "total_score": score_res["total_score"]
            }
        })

    # Sort descending by total score
    scored_candidates.sort(key=lambda x: x["score"], reverse=True)
    return scored_candidates
