from datetime import datetime, timezone
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.db.supabase_client import get_supabase_client
from app.core.dependencies import get_current_user
from app.models.rating import (
    RatingCreate,
    RatingResponse,
    WorkerRatingsSummaryResponse,
)

router = APIRouter(prefix="/ratings", tags=["Ratings & Reviews"])

@router.post("/", response_model=RatingResponse, status_code=status.HTTP_201_CREATED)
def submit_rating(
    payload: RatingCreate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Submit a star rating and review for a completed booking.
    Directly maps to Supabase schema: rating_value, comment, created_at.
    Automatically updates the worker's average rating in the workers table.
    """
    try:
        # 1. Fetch booking
        b_res = db.table("bookings").select("*, households(*)").eq("id", payload.booking_id).execute()
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Booking with ID '{payload.booking_id}' not found."
            )

        booking = b_res.data[0]
        worker_id = booking.get("worker_id")

        if not worker_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot rate a booking that does not have an assigned worker."
            )

        # Check if already rated
        existing_rating = db.table("ratings").select("id").eq("booking_id", payload.booking_id).execute()
        if existing_rating.data and len(existing_rating.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A review has already been submitted for this booking."
            )

        rating_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        # Schema matches rating_value / comment
        rating_record = {
            "id": rating_id,
            "booking_id": payload.booking_id,
            "rating_value": payload.rating,
            "comment": payload.review_text,
            "created_at": now_iso
        }

        try:
            res = db.table("ratings").insert(rating_record).execute()
        except Exception:
            # Fallback if rating / review_text column names are used
            rating_record = {
                "id": rating_id,
                "booking_id": payload.booking_id,
                "rating": payload.rating,
                "review_text": payload.review_text,
                "created_at": now_iso
            }
            res = db.table("ratings").insert(rating_record).execute()

        if not res.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record rating."
            )

        # 2. Recalculate worker's average rating across all completed bookings
        try:
            worker_ratings_res = db.table("ratings").select(
                "rating_value, bookings!inner(worker_id)"
            ).eq("bookings.worker_id", worker_id).execute()
            ratings_list = worker_ratings_res.data or []
            if ratings_list:
                total_score = sum(int(r.get("rating_value") or r.get("rating", 0)) for r in ratings_list)
                avg_rating = round(total_score / len(ratings_list), 2)
                db.table("workers").update({"rating": avg_rating}).eq("id", worker_id).execute()
        except Exception:
            pass

        created = res.data[0]
        return RatingResponse(
            id=str(created["id"]),
            booking_id=str(created["booking_id"]),
            rating=int(created.get("rating_value") or created.get("rating", payload.rating)),
            review_text=created.get("comment") or created.get("review_text"),
            created_at=created.get("created_at")
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error submitting rating: {str(e)}"
        )

@router.get("/worker/{worker_id}", response_model=WorkerRatingsSummaryResponse)
def get_worker_ratings(
    worker_id: str,
    db: Client = Depends(get_supabase_client)
):
    """
    Retrieve all ratings and calculated average score for a specific worker.
    """
    try:
        w_check = db.table("workers").select("id, rating").eq("id", worker_id).execute()
        if not w_check.data or len(w_check.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Worker with ID '{worker_id}' not found."
            )

        worker = w_check.data[0]

        res = db.table("ratings").select(
            "*, bookings!inner(worker_id, household_id, households(users(name)))"
        ).eq("bookings.worker_id", worker_id).order("created_at", desc=True).execute()

        reviews_data = res.data or []
        formatted_reviews = []
        for r in reviews_data:
            hh_name = None
            try:
                hh_name = r.get("bookings", {}).get("households", {}).get("users", {}).get("name")
            except Exception:
                pass

            rating_val = int(r.get("rating_value") or r.get("rating") or 5)
            review_txt = r.get("comment") or r.get("review_text")

            formatted_reviews.append(
                RatingResponse(
                    id=str(r["id"]),
                    booking_id=str(r["booking_id"]),
                    rating=rating_val,
                    review_text=review_txt,
                    created_at=r.get("created_at"),
                    household_name=hh_name
                )
            )

        avg = float(worker.get("rating") or 0.0)
        return WorkerRatingsSummaryResponse(
            worker_id=worker_id,
            average_rating=avg,
            total_reviews=len(formatted_reviews),
            reviews=formatted_reviews
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving worker reviews: {str(e)}"
        )
