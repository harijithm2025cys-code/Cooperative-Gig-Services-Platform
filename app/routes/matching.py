from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.db.supabase_client import get_supabase_client
from app.services.matching import rank_workers_for_booking
from app.models.matching import MatchResponse, MatchedWorker, MatchScoreBreakdown

router = APIRouter(prefix="/match", tags=["Matching Engine"])

@router.get("/{booking_request_id}", response_model=MatchResponse)
def match_workers_for_booking(
    booking_request_id: str,
    db: Client = Depends(get_supabase_client)
):
    """
    Ranks available cooperative workers for a specific booking request using the weighted formula:
    score = (skill_match * 50) + max(0, 20 - distance_km) + (rating * 5) - (active_bookings * 3)
    """
    try:
        # 1. Fetch booking with household and service details
        b_res = db.table("bookings").select(
            "*, households(*), services(*)"
        ).eq("id", booking_request_id).execute()

        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Booking request with ID '{booking_request_id}' not found."
            )

        booking = b_res.data[0]
        household = booking.get("households")
        service = booking.get("services")

        if not household:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking is missing associated household details."
            )

        req_lat = float(household.get("latitude") or 12.9716)
        req_lng = float(household.get("longitude") or 77.5946)
        req_skill = service.get("name") if service else "General Maintenance"

        # 2. Fetch all available workers with user and cooperative metadata
        w_res = db.table("workers").select(
            "*, users(id, name, email, phone), cooperatives(id, name, district, verified)"
        ).eq("availability", True).execute()

        candidate_workers = w_res.data or []

        # 3. Calculate active bookings per worker to apply workload penalty
        active_bookings_res = db.table("bookings").select(
            "worker_id"
        ).in_("status", ["pending", "accepted", "in_progress"]).not_.is_("worker_id", "null").execute()

        active_counts: Dict[str, int] = {}
        for row in (active_bookings_res.data or []):
            w_id = str(row.get("worker_id"))
            active_counts[w_id] = active_counts.get(w_id, 0) + 1

        # 4. Invoke isolated matching engine service
        ranked_list = rank_workers_for_booking(
            requested_skill=req_skill,
            request_lat=req_lat,
            request_lng=req_lng,
            available_workers=candidate_workers,
            worker_active_counts=active_counts
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
                    skill_match_points=item["breakdown"]["skill_match_points"],
                    distance_points=item["breakdown"]["distance_points"],
                    rating_points=item["breakdown"]["rating_points"],
                    active_bookings_penalty=item["breakdown"]["active_bookings_penalty"],
                    total_score=item["breakdown"]["total_score"]
                )
            )
            for item in ranked_list
        ]

        return MatchResponse(
            booking_id=booking_request_id,
            requested_skill=req_skill,
            household_location={"latitude": req_lat, "longitude": req_lng},
            total_candidates_evaluated=len(candidate_workers),
            ranked_workers=formatted_candidates
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Matching engine computation error: {str(e)}"
        )
