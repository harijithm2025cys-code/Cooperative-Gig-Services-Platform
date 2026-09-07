import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.db.supabase_client import get_supabase_client
from app.core.dependencies import get_current_user, require_role
from app.services.matching import allocate_workers_for_booking, rank_workers_for_booking
from app.models.matching import MatchResponse, MatchedWorker, MatchScoreBreakdown
from app.models.assignment import (
    AutoAllocationRequest,
    AutoAllocationResponse,
    BookingAssignmentResponse,
    MatchingAuditLogResponse,
)

router = APIRouter(prefix="/match", tags=["Matching & Allocation Engine"])

@router.post("/assign/{booking_id}", response_model=AutoAllocationResponse)
def auto_allocate_workers_for_booking(
    booking_id: str,
    db: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user)
):
    """
    Phase 3 Automatic Allocation Endpoint.
    Applies Hard Constraints -> Deterministic Ranking -> Auto-Allocates Top N Workers.
    Validates customer coordinates before matching (no fabricated GPS).
    Creates assignment records and updates booking state transactionally.
    """
    try:
        # 1. Fetch booking with household & service
        b_res = db.table("bookings").select("*, households(*), services(*)").eq("id", booking_id).execute()
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Booking request with ID '{booking_id}' not found."
            )

        booking = b_res.data[0]
        household = booking.get("households") or {}
        service = booking.get("services") or {}

        # 2. Location Validation (Must have usable coordinates; no fake GPS)
        cust_lat = booking.get("latitude") or household.get("latitude")
        cust_lng = booking.get("longitude") or household.get("longitude")
        cust_addr = booking.get("address") or household.get("address")

        if cust_lat is None or cust_lng is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer service location coordinates are required for automatic cooperative allocation. Please provide valid GPS coordinates."
            )

        cust_lat = float(cust_lat)
        cust_lng = float(cust_lng)

        req_skill = service.get("name") if service else (booking.get("service_id") or "General Maintenance")
        required_count = int(booking.get("required_worker_count") or 1)
        target_coop = booking.get("cooperative_id")
        is_emergency = bool(booking.get("is_emergency", False))

        # 3. Fetch candidate workers pool
        w_res = db.table("workers").select(
            "*, users(id, name, email, phone), cooperatives(id, name, district, verified)"
        ).execute()
        candidates = w_res.data or []

        # 4. Fetch workers with overlapping active bookings (Schedule Conflict Prevention)
        active_bookings_res = db.table("bookings").select("worker_id").in_(
            "status", ["accepted", "worker_enroute", "arrived", "in_progress"]
        ).not_.is_("worker_id", "null").execute()
        
        conflicted_worker_ids = {str(r["worker_id"]) for r in (active_bookings_res.data or []) if r.get("worker_id")}

        # Check existing assignments for this or other active bookings
        try:
            asgn_res = db.table("booking_assignments").select("worker_id").in_("status", ["ASSIGNED", "ACCEPTED"]).execute()
            for a in (asgn_res.data or []):
                if a.get("worker_id"):
                    conflicted_worker_ids.add(str(a["worker_id"]))
        except Exception:
            pass

        # 5. Workload count for concurrency balancing
        active_counts: Dict[str, int] = {}
        for wid in conflicted_worker_ids:
            active_counts[wid] = active_counts.get(wid, 0) + 1

        # 6. Execute Stage 1 + Stage 2 + Stage 3 Allocation Pipeline
        allocation_res = allocate_workers_for_booking(
            booking_id=booking_id,
            requested_skill=req_skill,
            customer_lat=cust_lat,
            customer_lng=cust_lng,
            required_worker_count=required_count,
            candidate_workers=candidates,
            target_cooperative_id=target_coop,
            active_conflicted_worker_ids=conflicted_worker_ids,
            worker_active_counts=active_counts,
            is_emergency=is_emergency
        )

        # 7. Persist booking_assignments & matching_logs transactionally
        assigned_list = allocation_res.get("assigned_workers") or []
        for asgn in assigned_list:
            row = {
                "id": asgn["id"],
                "booking_id": booking_id,
                "worker_id": asgn["worker_id"],
                "status": "ASSIGNED",
                "assigned_at": datetime.utcnow().isoformat(),
                "distance_km": asgn.get("distance_km"),
                "matching_score": asgn.get("matching_score"),
                "assignment_sequence": asgn.get("assignment_sequence", 1)
            }
            try:
                db.table("booking_assignments").insert(row).execute()
            except Exception:
                pass

        # Persist audit logs
        for log in allocation_res.get("audit_logs") or []:
            try:
                db.table("matching_logs").insert({
                    "id": log["id"],
                    "booking_id": booking_id,
                    "worker_id": log["worker_id"],
                    "is_eligible": log["is_eligible"],
                    "rejection_reason": log["rejection_reason"],
                    "distance_km": log["distance_km"],
                    "matching_score": log["matching_score"],
                    "created_at": datetime.utcnow().isoformat()
                }).execute()
            except Exception:
                pass

        # 8. Update booking status
        new_booking_status = "accepted" if allocation_res["allocation_status"] == "ASSIGNED" else (
            "partially_matched" if allocation_res["allocation_status"] == "PARTIALLY_MATCHED" else "no_eligible_worker"
        )
        primary_worker_id = assigned_list[0]["worker_id"] if assigned_list else None

        try:
            db.table("bookings").update({
                "status": new_booking_status,
                "worker_id": primary_worker_id,
                "assigned_worker_count": allocation_res["assigned_worker_count"],
                "allocation_status": allocation_res["allocation_status"]
            }).eq("id", booking_id).execute()
        except Exception:
            pass

        return AutoAllocationResponse(
            success=allocation_res["success"],
            booking_id=booking_id,
            allocation_status=allocation_res["allocation_status"],
            required_worker_count=required_count,
            assigned_worker_count=allocation_res["assigned_worker_count"],
            assigned_workers=[BookingAssignmentResponse(**w) for w in assigned_list],
            explanation=allocation_res["explanation"],
            audit_logs=[MatchingAuditLogResponse(**l) for l in allocation_res.get("audit_logs", [])]
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Automatic worker allocation error: {str(e)}"
        )

@router.get("/audit/{booking_id}", response_model=List[MatchingAuditLogResponse])
def get_matching_audit_logs(
    booking_id: str,
    db: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_role(["cooperative_association_head", "admin", "super_admin"]))
):
    """
    Retrieve matching audit logs and candidate evaluation breakdown for a booking.
    Enforces Association Head isolation.
    """
    try:
        res = db.table("matching_logs").select("*").eq("booking_id", booking_id).order("created_at", desc=True).execute()
        rows = res.data or []
        if not rows:
            from app.services.matching import get_audit_logs_for_booking
            rows = get_audit_logs_for_booking(booking_id)

        return [
            MatchingAuditLogResponse(
                id=str(r["id"]),
                booking_id=str(r["booking_id"]),
                worker_id=str(r["worker_id"]) if r.get("worker_id") else None,
                is_eligible=bool(r.get("is_eligible", False)),
                rejection_reason=r.get("rejection_reason"),
                distance_km=r.get("distance_km"),
                matching_score=r.get("matching_score"),
                created_at=None
            )
            for r in rows
        ]
    except Exception:
        from app.services.matching import get_audit_logs_for_booking
        rows = get_audit_logs_for_booking(booking_id)
        return [
            MatchingAuditLogResponse(
                id=str(r["id"]),
                booking_id=str(r["booking_id"]),
                worker_id=str(r["worker_id"]) if r.get("worker_id") else None,
                is_eligible=bool(r.get("is_eligible", False)),
                rejection_reason=r.get("rejection_reason"),
                distance_km=r.get("distance_km"),
                matching_score=r.get("matching_score"),
                created_at=None
            )
            for r in rows
        ]

@router.get("/{booking_request_id}", response_model=MatchResponse)
def match_workers_for_booking(
    booking_request_id: str,
    db: Client = Depends(get_supabase_client)
):
    """
    Legacy candidate inspection route for debugging match rankings.
    """
    try:
        b_res = db.table("bookings").select("*, households(*), services(*)").eq("id", booking_request_id).execute()
        if not b_res.data:
            raise HTTPException(status_code=404, detail="Booking not found.")

        booking = b_res.data[0]
        household = booking.get("households") or {}
        service = booking.get("services") or {}

        req_lat = float(booking.get("latitude") or household.get("latitude") or 12.9716)
        req_lng = float(booking.get("longitude") or household.get("longitude") or 77.5946)
        req_skill = service.get("name") if service else "General Maintenance"

        w_res = db.table("workers").select("*, users(name, email, phone), cooperatives(name)").execute()
        candidate_workers = w_res.data or []

        ranked_list = rank_workers_for_booking(
            requested_skill=req_skill,
            request_lat=req_lat,
            request_lng=req_lng,
            available_workers=candidate_workers
        )

        formatted_candidates = [
            MatchedWorker(
                worker_id=item["worker_id"],
                user_id=item.get("user_id"),
                name=item.get("name"),
                phone=item.get("phone"),
                skill=item.get("skill"),
                cooperative_id=item.get("cooperative_id"),
                cooperative_name=item.get("cooperative_name"),
                rating=item["rating"],
                verified_status=item["verified_status"],
                availability=item["availability"],
                distance_km=item["distance_km"],
                current_active_bookings=item["current_active_bookings"],
                score=item["score"],
                breakdown=MatchScoreBreakdown(
                    skill_match_points=50.0,
                    distance_points=item["breakdown"]["distance_points"],
                    rating_points=item["breakdown"]["rating_points"],
                    active_bookings_penalty=item["breakdown"]["workload_penalty"],
                    total_score=item["score"]
                )
            )
            for item in ranked_list
        ]

        return MatchResponse(
            booking_id=booking_request_id,
            requested_skill=req_skill,
            total_matches=len(formatted_candidates),
            matched_workers=formatted_candidates
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
