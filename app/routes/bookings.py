from datetime import datetime, timezone
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.db.supabase_client import get_supabase_client
from app.core.dependencies import get_current_user
from app.models.booking import (
    BookingCreate,
    BookingStatusUpdate,
    BookingResponse,
    BookingListResponse,
)

router = APIRouter(prefix="/bookings", tags=["Bookings"])

@router.post("/", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: BookingCreate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Create a new booking request.
    If household_id is omitted, it is inferred from the authenticated user.
    """
    try:
        household_id = payload.household_id
        
        # If household_id not provided, look up from user_id
        if not household_id:
            h_res = db.table("households").select("id").eq("user_id", current_user["id"]).execute()
            if h_res.data and len(h_res.data) > 0:
                household_id = h_res.data[0]["id"]
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No household profile found for current user. Please provide household_id."
                )

        # Validate household exists
        hh_check = db.table("households").select("id, address, latitude, longitude").eq("id", household_id).execute()
        if not hh_check.data or len(hh_check.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Household with ID '{household_id}' does not exist."
            )

        # Validate service exists
        srv_check = db.table("services").select("id, name, base_price").eq("id", payload.service_id).execute()
        if not srv_check.data or len(srv_check.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service with ID '{payload.service_id}' does not exist."
            )

        # If worker_id is provided, validate worker exists
        if payload.worker_id:
            w_check = db.table("workers").select("id, availability, verified_status").eq("id", payload.worker_id).execute()
            if not w_check.data or len(w_check.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Worker with ID '{payload.worker_id}' does not exist."
                )

        booking_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        scheduled_iso = payload.scheduled_time.isoformat() if payload.scheduled_time else now_iso

        booking_record = {
            "id": booking_id,
            "household_id": household_id,
            "worker_id": payload.worker_id,
            "service_id": payload.service_id,
            "status": "pending",
            "scheduled_time": scheduled_iso,
            "created_at": now_iso
        }

        res = db.table("bookings").insert(booking_record).execute()
        if not res.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record booking in database."
            )

        created_booking = res.data[0]
        return BookingResponse(
            id=str(created_booking["id"]),
            household_id=str(created_booking["household_id"]),
            worker_id=str(created_booking["worker_id"]) if created_booking.get("worker_id") else None,
            service_id=str(created_booking["service_id"]),
            status=created_booking["status"],
            scheduled_time=created_booking.get("scheduled_time"),
            created_at=created_booking.get("created_at"),
            check_in_time=created_booking.get("check_in_time"),
            check_out_time=created_booking.get("check_out_time"),
            household=hh_check.data[0],
            service=srv_check.data[0]
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating booking: {str(e)}"
        )

@router.get("/{booking_id}", response_model=BookingResponse)
def get_booking_by_id(
    booking_id: str,
    db: Client = Depends(get_supabase_client)
):
    """
    Retrieve booking by ID with joined household, worker, and service metadata.
    """
    try:
        res = db.table("bookings").select(
            "*, households(*), workers(*, users(name, phone)), services(*)"
        ).eq("id", booking_id).execute()

        if not res.data or len(res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Booking with ID '{booking_id}' not found."
            )

        b = res.data[0]
        return BookingResponse(
            id=str(b["id"]),
            household_id=str(b["household_id"]),
            worker_id=str(b["worker_id"]) if b.get("worker_id") else None,
            service_id=str(b["service_id"]),
            status=b["status"],
            scheduled_time=b.get("scheduled_time"),
            created_at=b.get("created_at"),
            check_in_time=b.get("check_in_time"),
            check_out_time=b.get("check_out_time"),
            household=b.get("households"),
            worker=b.get("workers"),
            service=b.get("services")
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving booking: {str(e)}"
        )

@router.patch("/{booking_id}/status", response_model=BookingResponse)
def update_booking_status(
    booking_id: str,
    payload: BookingStatusUpdate,
    db: Client = Depends(get_supabase_client)
):
    """
    Update booking lifecycle status:
    - pending -> accepted / cancelled
    - accepted -> in_progress (records check_in_time)
    - in_progress -> completed (records check_out_time)
    """
    try:
        # Check current booking
        existing_res = db.table("bookings").select("*").eq("id", booking_id).execute()
        if not existing_res.data or len(existing_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Booking with ID '{booking_id}' not found."
            )

        current_booking = existing_res.data[0]
        new_status = payload.status
        action = payload.action

        # If action mapped
        if action == "check_in":
            new_status = "in_progress"
        elif action == "check_out" or action == "complete":
            new_status = "completed"
        elif action == "accept":
            new_status = "accepted"
        elif action == "reject" or action == "cancel":
            new_status = "cancelled"

        now_iso = datetime.now(timezone.utc).isoformat()
        update_data = {"status": new_status}

        if new_status == "in_progress" and not current_booking.get("check_in_time"):
            update_data["check_in_time"] = now_iso
        elif new_status == "completed" and not current_booking.get("check_out_time"):
            update_data["check_out_time"] = now_iso

        res = db.table("bookings").update(update_data).eq("id", booking_id).execute()
        if not res.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update booking status."
            )

        updated_b = res.data[0]
        return BookingResponse(
            id=str(updated_b["id"]),
            household_id=str(updated_b["household_id"]),
            worker_id=str(updated_b["worker_id"]) if updated_b.get("worker_id") else None,
            service_id=str(updated_b["service_id"]),
            status=updated_b["status"],
            scheduled_time=updated_b.get("scheduled_time"),
            created_at=updated_b.get("created_at"),
            check_in_time=updated_b.get("check_in_time"),
            check_out_time=updated_b.get("check_out_time")
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating booking status: {str(e)}"
        )

@router.get("/household/{household_id}", response_model=List[BookingResponse])
def get_household_bookings(
    household_id: str,
    db: Client = Depends(get_supabase_client)
):
    """
    Get all bookings requested by a given household.
    """
    try:
        res = db.table("bookings").select(
            "*, services(*), workers(*, users(name, phone))"
        ).eq("household_id", household_id).order("created_at", desc=True).execute()

        bookings = res.data or []
        return [
            BookingResponse(
                id=str(b["id"]),
                household_id=str(b["household_id"]),
                worker_id=str(b["worker_id"]) if b.get("worker_id") else None,
                service_id=str(b["service_id"]),
                status=b["status"],
                scheduled_time=b.get("scheduled_time"),
                created_at=b.get("created_at"),
                check_in_time=b.get("check_in_time"),
                check_out_time=b.get("check_out_time"),
                worker=b.get("workers"),
                service=b.get("services")
            )
            for b in bookings
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching household bookings: {str(e)}"
        )

@router.get("/worker/{worker_id}", response_model=List[BookingResponse])
def get_worker_bookings(
    worker_id: str,
    db: Client = Depends(get_supabase_client)
):
    """
    Get all bookings assigned to a given worker.
    """
    try:
        res = db.table("bookings").select(
            "*, services(*), households(*, users(name, phone))"
        ).eq("worker_id", worker_id).order("created_at", desc=True).execute()

        bookings = res.data or []
        return [
            BookingResponse(
                id=str(b["id"]),
                household_id=str(b["household_id"]),
                worker_id=str(b["worker_id"]) if b.get("worker_id") else None,
                service_id=str(b["service_id"]),
                status=b["status"],
                scheduled_time=b.get("scheduled_time"),
                created_at=b.get("created_at"),
                check_in_time=b.get("check_in_time"),
                check_out_time=b.get("check_out_time"),
                household=b.get("households"),
                service=b.get("services")
            )
            for b in bookings
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching worker bookings: {str(e)}"
        )
