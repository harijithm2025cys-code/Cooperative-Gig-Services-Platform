import math
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

def haversine_distance(lat1: Optional[float], lon1: Optional[float], lat2: Optional[float], lon2: Optional[float]) -> float:
    """
    Calculate the great-circle distance between two points on Earth in kilometers.
    Uses the standard Haversine formula.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 999.0

    R = 6371.0  # Earth radius in kilometers
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)

def evaluate_worker_eligibility(
    worker: Dict[str, Any],
    requested_skill: str,
    target_cooperative_id: Optional[str] = None,
    required_certification: Optional[str] = None,
    customer_lat: Optional[float] = None,
    customer_lng: Optional[float] = None,
    max_service_radius_km: float = 25.0,
    active_conflicted_worker_ids: Optional[set] = None
) -> Tuple[bool, Optional[str], float]:
    """
    Stage 1 Hard Constraint Filters.
    Evaluates whether a worker candidate meets strict mandatory eligibility criteria.
    Returns: (is_eligible: bool, rejection_reason: Optional[str], distance_km: float)
    
    Hard Filters:
    1. Active Status (worker not suspended or disabled)
    2. Cooperative Society Membership match (if targeted)
    3. Mandatory Skill match
    4. Mandatory Certification (if service requires special license)
    5. Operational Availability Status ('available' vs 'unavailable'/'working'/'leave')
    6. Service Area / Distance Radius check
    7. Schedule / Overlapping Booking Conflict check
    """
    active_conflicts = active_conflicted_worker_ids or set()
    worker_id = str(worker.get("id"))

    # 1. Active Worker Check
    if worker.get("is_active") is False:
        return False, "worker_inactive", 999.0

    # 2. Cooperative Match (if specific cooperative requested)
    w_coop_id = worker.get("cooperative_id")
    w_type = worker.get("worker_type", "cooperative")
    if target_cooperative_id and w_coop_id:
        if str(w_coop_id) != str(target_cooperative_id):
            return False, "cooperative_mismatch", 999.0
    elif target_cooperative_id and not w_coop_id:
        return False, "independent_worker_excluded_from_cooperative_request", 999.0

    # 3. Mandatory Skill Match
    w_skill = (worker.get("skill") or "").strip().lower()
    r_skill = (requested_skill or "").strip().lower()
    if not (r_skill in w_skill or w_skill in r_skill):
        return False, "skill_mismatch", 999.0

    # 4. Mandatory Certification Check (if service demands certification)
    if required_certification:
        w_certs = [c.lower() for c in (worker.get("certifications") or [])]
        req_cert = required_certification.strip().lower()
        if not any(req_cert in c or c in req_cert for c in w_certs):
            return False, "missing_required_certification", 999.0

    # 5. Availability Status Check
    avail_status = (worker.get("availability_status") or "available").lower()
    is_avail_bool = worker.get("is_available")
    if is_avail_bool is None:
        is_avail_bool = worker.get("availability", True)

    if not is_avail_bool or avail_status != "available":
        return False, f"worker_unavailable_{avail_status}", 999.0

    # 6. Schedule / Booking Conflict Check
    if worker_id in active_conflicts:
        return False, "booking_schedule_conflict", 999.0

    # 7. Service Area / Proximity Radius Check
    w_lat = worker.get("latitude")
    w_lng = worker.get("longitude")
    service_radius = float(worker.get("service_radius_km") or max_service_radius_km)

    if customer_lat is not None and customer_lng is not None and w_lat is not None and w_lng is not None:
        dist_km = haversine_distance(customer_lat, customer_lng, float(w_lat), float(w_lng))
        if dist_km > service_radius:
            return False, "outside_service_area", dist_km
    else:
        dist_km = 999.0

    return True, None, dist_km

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
    Stage 2 Deterministic Multi-Factor Ranking Score.
    Applied ONLY to candidate workers who have passed Stage 1 hard eligibility filters.
    
    Formula:
        Score = DistanceScore(25-35) + RatingScore(20) + FairnessMonthly(Fi, 25)
                + CoopPriority(15) + Experience(10) - ActiveWorkloadPenalty(count * 6)
    """
    # 1. Distance Score (max 25 normal, max 35 if emergency)
    max_dist_pts = 35.0 if is_emergency else 25.0
    if (worker_lat is not None and worker_lng is not None and 
        request_lat is not None and request_lng is not None):
        distance_km = haversine_distance(request_lat, request_lng, worker_lat, worker_lng)
        distance_points = max(0.0, max_dist_pts - distance_km)
    else:
        distance_km = 999.0
        distance_points = 0.0

    # 2. Rating Score (Rating * 4.0 points, max 20 for 5.0 rating)
    rating_val = float(worker_rating) if worker_rating is not None else 0.0
    rating_val = max(0.0, min(5.0, rating_val))
    rating_points = rating_val * 4.0

    # 3. Fair Workload Balancing Factor (Fi) - Up to 25 points
    # Balances monthly earnings: workers with fewer jobs this month gain up to +25 score
    jobs_done = max(0, int(monthly_jobs_completed or 0))
    fairness_points = max(0.0, 25.0 - (jobs_done * 2.5))

    # 4. Current Workload Penalty (-(active_assignments * 6) points)
    # Immediate concurrency fairness: workers with 0 active jobs rank above workers with active jobs
    active_count = max(0, int(active_bookings_count or 0))
    workload_penalty = active_count * 6.0

    # 5. Cooperative Priority Boost (15 points)
    coop_boost_points = 15.0 if is_cooperative_worker else 0.0

    # 6. Experience Points (1 point per year, max 10 points)
    exp = max(0, min(10, int(experience_years or 0)))
    experience_points = float(exp)

    total_score = (
        distance_points +
        rating_points +
        fairness_points +
        coop_boost_points +
        experience_points -
        workload_penalty
    )

    return {
        "distance_points": round(distance_points, 2),
        "rating_points": round(rating_points, 2),
        "fairness_points": round(fairness_points, 2),
        "coop_boost_points": round(coop_boost_points, 2),
        "experience_points": round(experience_points, 2),
        "workload_penalty": round(workload_penalty, 2),
        "total_score": round(total_score, 2),
        "distance_km": distance_km,
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
                "distance_points": score_res["distance_points"],
                "rating_points": score_res["rating_points"],
                "fairness_points": score_res["fairness_points"],
                "coop_boost_points": score_res["coop_boost_points"],
                "experience_points": score_res["experience_points"],
                "workload_penalty": score_res["workload_penalty"]
            }
        })

    scored_candidates.sort(key=lambda c: c["score"], reverse=True)
    return scored_candidates

def allocate_workers_for_booking(
    booking_id: str,
    requested_skill: str,
    customer_lat: float,
    customer_lng: float,
    required_worker_count: int,
    candidate_workers: List[Dict[str, Any]],
    target_cooperative_id: Optional[str] = None,
    required_certification: Optional[str] = None,
    active_conflicted_worker_ids: Optional[set] = None,
    worker_active_counts: Optional[Dict[str, int]] = None,
    worker_monthly_counts: Optional[Dict[str, int]] = None,
    is_emergency: bool = False
) -> Dict[str, Any]:
    """
    Phase 3 Complete Two-Stage Matching & Multi-Worker Allocation Pipeline:
    
    1. STAGE 1 (Hard Eligibility Filter):
       - Filters candidate pool by skill, certification, active status, availability, distance, schedule conflicts.
       - Records audit log entries for all evaluated candidates (both eligible and rejected).
       
    2. STAGE 2 (Deterministic Ranking):
       - Ranks eligible candidates using multi-factor formula (distance + rating + Fi fairness - workload).
       
    3. STAGE 3 (Automatic Allocation):
       - Selects the top N required workers.
       - Produces assignment records with sequence index and matching metadata.
       - Determines status: ASSIGNED, PARTIALLY_MATCHED, or NO_ELIGIBLE_WORKER.
    """
    eligible_workers = []
    audit_logs = []

    for worker in candidate_workers:
        worker_id = str(worker.get("id"))
        user_info = worker.get("users") or {}
        w_name = user_info.get("name") or worker.get("name") or "Worker"

        is_eligible, rejection_reason, dist_km = evaluate_worker_eligibility(
            worker=worker,
            requested_skill=requested_skill,
            target_cooperative_id=target_cooperative_id,
            required_certification=required_certification,
            customer_lat=customer_lat,
            customer_lng=customer_lng,
            active_conflicted_worker_ids=active_conflicted_worker_ids
        )

        if is_eligible:
            eligible_workers.append(worker)
            audit_logs.append({
                "id": str(uuid.uuid4()),
                "booking_id": booking_id,
                "worker_id": worker_id,
                "worker_name": w_name,
                "is_eligible": True,
                "rejection_reason": None,
                "distance_km": dist_km,
                "matching_score": 0.0,
                "created_at": datetime.utcnow()
            })
        else:
            audit_logs.append({
                "id": str(uuid.uuid4()),
                "booking_id": booking_id,
                "worker_id": worker_id,
                "worker_name": w_name,
                "is_eligible": False,
                "rejection_reason": rejection_reason,
                "distance_km": dist_km if dist_km < 900 else None,
                "matching_score": 0.0,
                "created_at": datetime.utcnow()
            })

    # Stage 2: Rank eligible candidates only
    if not eligible_workers:
        record_allocation_assignments(booking_id, [], audit_logs)
        return {
            "success": False,
            "booking_id": booking_id,
            "allocation_status": "NO_ELIGIBLE_WORKER",
            "required_worker_count": required_worker_count,
            "assigned_worker_count": 0,
            "assigned_workers": [],
            "explanation": f"No eligible cooperative workers available with skill '{requested_skill}' within service radius.",
            "audit_logs": audit_logs
        }

    ranked = rank_workers_for_booking(
        requested_skill=requested_skill,
        request_lat=customer_lat,
        request_lng=customer_lng,
        available_workers=eligible_workers,
        worker_active_counts=worker_active_counts,
        worker_monthly_counts=worker_monthly_counts,
        is_emergency=is_emergency
    )

    # Attach calculated scores to eligible audit logs
    score_map = {r["worker_id"]: r["score"] for r in ranked}
    for log in audit_logs:
        if log["is_eligible"] and log["worker_id"] in score_map:
            log["matching_score"] = score_map[log["worker_id"]]

    # Stage 3: Auto-select required worker count
    allocated_candidates = ranked[:required_worker_count]
    assigned_count = len(allocated_candidates)

    assignments = []
    for idx, c in enumerate(allocated_candidates):
        assignments.append({
            "id": str(uuid.uuid4()),
            "booking_id": booking_id,
            "worker_id": c["worker_id"],
            "status": "ASSIGNED",
            "assigned_at": datetime.utcnow(),
            "distance_km": c["distance_km"],
            "matching_score": c["score"],
            "assignment_sequence": idx + 1,
            "worker_name": c["name"],
            "worker_phone": c["phone"],
            "worker_skill": c["skill"],
            "cooperative_name": c["cooperative_name"] or "Labour Cooperative Society"
        })

    if assigned_count >= required_worker_count:
        status_code = "ASSIGNED"
        explanation = f"Successfully auto-allocated {assigned_count} of {required_worker_count} requested specialists."
    else:
        status_code = "PARTIALLY_MATCHED"
        explanation = f"Partially allocated {assigned_count} of {required_worker_count} requested specialists. Awaiting additional members."

    record_allocation_assignments(booking_id, assignments, audit_logs)

    return {
        "success": True,
        "booking_id": booking_id,
        "allocation_status": status_code,
        "required_worker_count": required_worker_count,
        "assigned_worker_count": assigned_count,
        "assigned_workers": assignments,
        "explanation": explanation,
        "audit_logs": audit_logs
    }

# ---------------------------------------------------------------------------
# In-memory assignment and audit log stores (guarantees fast query fallback)
# ---------------------------------------------------------------------------

_ASSIGNMENTS_BY_BOOKING: Dict[str, List[Dict[str, Any]]] = {}
_ASSIGNMENTS_BY_WORKER: Dict[str, List[Dict[str, Any]]] = {}
_ASSIGNMENTS_BY_ID: Dict[str, Dict[str, Any]] = {}
_AUDIT_LOGS_BY_BOOKING: Dict[str, List[Dict[str, Any]]] = {}

def record_allocation_assignments(booking_id: str, assignments: List[Dict[str, Any]], audit_logs: List[Dict[str, Any]]) -> None:
    bid = str(booking_id)
    _ASSIGNMENTS_BY_BOOKING[bid] = assignments
    for a in assignments:
        wid = str(a["worker_id"])
        if wid not in _ASSIGNMENTS_BY_WORKER:
            _ASSIGNMENTS_BY_WORKER[wid] = []
        if not any(x.get("id") == a.get("id") for x in _ASSIGNMENTS_BY_WORKER[wid]):
            _ASSIGNMENTS_BY_WORKER[wid].insert(0, a)
        _ASSIGNMENTS_BY_ID[str(a.get("id"))] = a
        
    _AUDIT_LOGS_BY_BOOKING[bid] = audit_logs

def get_assignments_for_booking(booking_id: str) -> List[Dict[str, Any]]:
    return _ASSIGNMENTS_BY_BOOKING.get(str(booking_id), [])

def get_assignments_for_worker(worker_id: str, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    asgns = _ASSIGNMENTS_BY_WORKER.get(str(worker_id), [])
    if status_filter:
        return [a for a in asgns if (a.get("status") or "").upper() == status_filter.upper()]
    return asgns

def update_assignment_status_in_memory(assignment_id: str, new_status: str) -> Optional[Dict[str, Any]]:
    aid = str(assignment_id)
    if aid in _ASSIGNMENTS_BY_ID:
        _ASSIGNMENTS_BY_ID[aid]["status"] = new_status
        return _ASSIGNMENTS_BY_ID[aid]
    return None

def get_audit_logs_for_booking(booking_id: str) -> List[Dict[str, Any]]:
    return _AUDIT_LOGS_BY_BOOKING.get(str(booking_id), [])

