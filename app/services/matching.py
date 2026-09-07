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
    active_bookings_count: int = 0,
    is_cooperative_worker: bool = True,
    monthly_jobs_completed: int = 0,
    experience_years: int = 2,
    is_emergency: bool = False
) -> Dict[str, Any]:
    """
    Calculate the multi-factor weighted match score for a worker candidate.
    
    Formula:
        Score = SkillMatch(50) + DistanceScore(20-30) + RatingScore(25)
                + FairWorkloadBalancing(Fi, 25) + CoopPriority(15) + Experience(10)
                - ActiveBookingsPenalty(count * 4)
    """
    # 1. Skill Match (50 points maximum)
    skill_match_flag = 0
    if worker_skill and requested_skill:
        ws = worker_skill.strip().lower()
        rs = requested_skill.strip().lower()
        if rs in ws or ws in rs:
            skill_match_flag = 1
    
    skill_points = 50.0 * skill_match_flag

    # 2. Distance Score (20 points normal, 30 points if emergency)
    max_dist_pts = 30.0 if is_emergency else 20.0
    if (worker_lat is not None and worker_lng is not None and 
        request_lat is not None and request_lng is not None):
        distance_km = haversine_distance(request_lat, request_lng, worker_lat, worker_lng)
        distance_points = max(0.0, max_dist_pts - distance_km)
    else:
        distance_km = 999.0
        distance_points = 0.0

    # 3. Rating Score (Rating * 5 points, max 25 for 5.0 rating)
    rating_val = float(worker_rating) if worker_rating is not None else 0.0
    rating_val = max(0.0, min(5.0, rating_val))
    rating_points = rating_val * 5.0

    # 4. Fair Workload Balancing Factor (Fi) - Up to 25 points
    # Prevents monopoly by allocating higher scores to under-dispatched workers
    # If a worker has 0 jobs this month, Fi = 25.0 points. Decreases gradually as jobs increase.
    jobs_done = max(0, int(monthly_jobs_completed or 0))
    fairness_points = max(0.0, 25.0 - (jobs_done * 2.5))

    # 5. Cooperative Member Priority Boost (15 points)
    coop_boost_points = 15.0 if is_cooperative_worker else 0.0

    # 6. Experience Points (1 point per year, max 10 points)
    exp = max(0, min(10, int(experience_years or 0)))
    experience_points = float(exp)

    # 7. Active Bookings Penalty (-(active_bookings * 4) points)
    active_count = max(0, int(active_bookings_count or 0))
    active_penalty = active_count * 4.0

    # Total Multi-Factor Score
    total_score = (
        skill_points +
        distance_points +
        rating_points +
        fairness_points +
        coop_boost_points +
        experience_points -
        active_penalty
    )

    return {
        "skill_match_points": round(skill_points, 2),
        "distance_points": round(distance_points, 2),
        "rating_points": round(rating_points, 2),
        "fairness_points": round(fairness_points, 2),
        "coop_boost_points": round(coop_boost_points, 2),
        "experience_points": round(experience_points, 2),
        "active_bookings_penalty": round(active_penalty, 2),
        "total_score": round(total_score, 2),
        "distance_km": distance_km,
        "is_skill_match": bool(skill_match_flag),
        "active_bookings_count": active_count,
        "monthly_jobs_completed": jobs_done,
        "is_cooperative_worker": is_cooperative_worker
    }

def rank_workers_for_booking(
    requested_skill: str,
    request_lat: float,
    request_lng: float,
    available_workers: List[Dict[str, Any]],
    worker_active_counts: Optional[Dict[str, int]] = None,
    worker_monthly_counts: Optional[Dict[str, int]] = None,
    is_emergency: bool = False
) -> List[Dict[str, Any]]:
    """
    Ranks candidate workers against a booking request using enhanced Fair Balancing Score (Fi).
    Returns candidates sorted by total score in descending order.
    """
    active_counts = worker_active_counts or {}
    monthly_counts = worker_monthly_counts or {}
    scored_candidates = []

    for worker in available_workers:
        worker_id = str(worker.get("id"))
        w_skill = worker.get("skill", "")
        w_lat = worker.get("latitude")
        w_lng = worker.get("longitude")
        w_rating = float(worker.get("rating") or 0.0)
        w_exp = int(worker.get("experience_years") or 2)
        active_cnt = active_counts.get(worker_id, 0)
        monthly_cnt = monthly_counts.get(worker_id, int(worker.get("jobs_completed_this_month") or 0))

        # Check if worker is cooperative member
        coop_id = worker.get("cooperative_id")
        w_type = worker.get("worker_type", "cooperative")
        is_coop = bool(coop_id) and (w_type != "independent")

        score_res = calculate_worker_score(
            worker_skill=w_skill,
            requested_skill=requested_skill,
            worker_lat=w_lat,
            worker_lng=w_lng,
            request_lat=request_lat,
            request_lng=request_lng,
            worker_rating=w_rating,
            active_bookings_count=active_cnt,
            is_cooperative_worker=is_coop,
            monthly_jobs_completed=monthly_cnt,
            experience_years=w_exp,
            is_emergency=is_emergency
        )

        user_info = worker.get("users") or {}
        coop_info = worker.get("cooperatives") or {}

        scored_candidates.append({
            "worker_id": worker_id,
            "user_id": worker.get("user_id"),
            "name": user_info.get("name") or user_info.get("email", "Worker"),
            "phone": user_info.get("phone"),
            "skill": w_skill,
            "cooperative_id": coop_id,
            "cooperative_name": coop_info.get("name") if isinstance(coop_info, dict) else None,
            "worker_type": w_type,
            "rating": w_rating,
            "hourly_rate": float(worker.get("hourly_rate") or 350.0),
            "verified_status": bool(worker.get("verified_status", True)),
            "availability": bool(worker.get("availability", True)),
            "distance_km": score_res["distance_km"],
            "current_active_bookings": active_cnt,
            "monthly_jobs_completed": monthly_cnt,
            "score": score_res["total_score"],
            "breakdown": {
                "skill_match_points": score_res["skill_match_points"],
                "distance_points": score_res["distance_points"],
                "rating_points": score_res["rating_points"],
                "fairness_points": score_res["fairness_points"],
                "coop_boost_points": score_res["coop_boost_points"],
                "experience_points": score_res["experience_points"],
                "active_bookings_penalty": score_res["active_bookings_penalty"]
            }
        })

    # Sort descending by final score
    scored_candidates.sort(key=lambda c: c["score"], reverse=True)
    return scored_candidates
