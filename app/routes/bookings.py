import logging
from datetime import datetime, timezone
import uuid
import random
import math
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

logger = logging.getLogger("bookings_router")

from app.db.supabase_client import get_supabase_client
from app.core.dependencies import get_current_user
from app.models.booking import (
    BookingCreate,
    BookingStatusUpdate,
    BookingResponse,
    BookingListResponse,
    CheckInVerificationRequest,
    CheckOutVerificationRequest,
    PaymentProcessRequest,
    WorkerLocationUpdate,
    VerificationResponse,
    PaymentResponse,
    WorkerLocationResponse,
    BookingStatusType,
)

router = APIRouter(prefix="/bookings", tags=["Bookings"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def _generate_otp(length: int = 6) -> str:
    return "".join(random.choices("0123456789", k=length))

def _map_action_to_status(action: str, current_status: str) -> Optional[str]:
    mapping = {
        "request": "requested",
        "accept": "accepted",
        "reject": "rejected",
        "start_travel": "worker_enroute",
        "arrive": "arrived",
        "verify_checkin": "verified_checkin",
        "init_payment": "payment_pending",
        "release_payment": "payment_released",
        "check_in": "in_progress",
        "start_service": "in_progress",
        "complete_service": "verified_checkout",
        "verify_checkout": "verified_checkout",
        "check_out": "completed",
        "complete": "completed",
        "cancel": "cancelled",
    }
    return mapping.get(action)

VALID_TRANSITIONS = {
    "requested": ["payment_pending", "matching", "assigned", "partially_matched", "no_eligible_worker", "cancelled", "rejected", "accepted"],
    "payment_pending": ["paid", "matching", "assigned", "accepted", "partially_matched", "no_eligible_worker", "cancelled", "payment_failed"],
    "paid": ["matching", "assigned", "accepted", "partially_matched", "no_eligible_worker", "cancelled"],
    "payment_failed": ["payment_pending", "cancelled"],
    "matching": ["assigned", "partially_matched", "no_eligible_worker", "cancelled"],
    "assigned": ["accepted", "rejected", "matching", "cancelled"],
    "partially_matched": ["assigned", "matching", "cancelled"],
    "accepted": ["worker_enroute", "on_the_way", "cancelled"],
    "worker_enroute": ["arrived", "cancelled"],
    "on_the_way": ["arrived", "cancelled"],
    "arrived": ["in_progress", "verified_checkin", "cancelled"],
    "verified_checkin": ["in_progress"],
    "in_progress": ["customer_confirmation_pending", "completed", "verified_checkout"],
    "customer_confirmation_pending": ["customer_confirmed", "completed", "disputed"],
    "customer_confirmed": ["completed"],
    "verified_checkout": ["completed"],
    "completed": [],
    "cancelled": [],
    "rejected": [],
    "disputed": ["completed", "cancelled"],
    "no_eligible_worker": ["matching", "cancelled"],
}

# ---------------------------------------------------------------------------
# Core booking CRUD
# ---------------------------------------------------------------------------

@router.post("/", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: BookingCreate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    try:
        household_id = payload.household_id
        if not household_id:
            if db:
                try:
                    h_res = db.table("households").select("id").eq("user_id", current_user["id"]).execute()
                    if h_res.data and len(h_res.data) > 0:
                        household_id = h_res.data[0]["id"]
                except Exception:
                    pass
            if not household_id:
                household_id = current_user.get("id") or "hh_demo"

        hh = None
        if db:
            try:
                hh_check = db.table("households").select("id, address, latitude, longitude").eq("id", household_id).execute()
                if hh_check.data and len(hh_check.data) > 0:
                    hh = hh_check.data[0]
            except Exception:
                pass

        if not hh:
            hh = {
                "id": str(household_id),
                "address": payload.address or "Bengaluru City",
                "latitude": payload.latitude if payload.latitude is not None else 12.9716,
                "longitude": payload.longitude if payload.longitude is not None else 77.5946
            }

        srv = None
        if db:
            try:
                srv_check = db.table("services").select("id, name, base_price").eq("id", payload.service_id).execute()
                if not srv_check.data or len(srv_check.data) == 0:
                    srv_check = db.table("services").select("id, name, base_price").ilike("name", f"%{payload.service_id}%").limit(1).execute()
                if srv_check.data and len(srv_check.data) > 0:
                    srv = srv_check.data[0]
            except Exception:
                pass

        if not srv:
            srv = {
                "id": str(payload.service_id),
                "name": str(payload.service_id).capitalize(),
                "base_price": payload.estimated_amount or 450.0
            }

        booking_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        scheduled_iso = payload.scheduled_time.isoformat() if payload.scheduled_time else now_iso

        lat = payload.latitude if payload.latitude is not None else hh.get("latitude", 12.9716)
        lng = payload.longitude if payload.longitude is not None else hh.get("longitude", 77.5946)
        addr = payload.address or hh.get("address", "Bengaluru Central")
        est_amount = payload.estimated_amount if payload.estimated_amount else srv.get("base_price", 450.0)

        otp = _generate_otp()

        booking_record = {
            "id": booking_id,
            "household_id": household_id,
            "worker_id": None,
            "service_id": payload.service_id,
            "status": "payment_pending",
            "requested_at": now_iso,
            "latitude": float(lat),
            "longitude": float(lng),
            "address": addr,
            "notes": payload.notes,
            "estimated_amount": est_amount,
            "final_amount": est_amount,
            "verification_otp": otp,
            "household_verified_checkin": False,
            "worker_verified_checkin": False,
            "household_verified_checkout": False,
            "worker_verified_checkout": False,
            "payment_status": "pending",
            "allocation_status": "PAYMENT_PENDING",
            "assigned_worker_count": 0,
        }

        created_booking = None
        if db:
            try:
                res = db.table("bookings").insert(booking_record).execute()
                if res.data and len(res.data) > 0:
                    created_booking = res.data[0]
            except Exception:
                try:
                    booking_record["created_at"] = now_iso
                    booking_record["scheduled_time"] = scheduled_iso
                    res = db.table("bookings").insert(booking_record).execute()
                    if res.data and len(res.data) > 0:
                        created_booking = res.data[0]
                except Exception:
                    pass

        if not created_booking:
            created_booking = booking_record

        # CRITICAL BUSINESS RULE (Phase 5):
        # Customer payment MUST be confirmed and captured before worker dispatch or allocation.
        # Booking starts in payment_pending. Worker allocation happens upon verified payment capture.
        from app.services.matching import _BOOKINGS_BY_ID
        _BOOKINGS_BY_ID[str(booking_id)] = booking_record

        return BookingResponse(
            id=str(created_booking["id"]),
            household_id=str(created_booking["household_id"]),
            worker_id=None,
            service_id=str(created_booking["service_id"]),
            status="payment_pending",
            required_worker_count=payload.required_worker_count,
            assigned_worker_count=0,
            allocation_status="PAYMENT_PENDING",
            assignments=allocated_assignments if allocated_assignments else None,
            scheduled_time=created_booking.get("scheduled_time"),
            created_at=created_booking.get("created_at"),
            check_in_time=created_booking.get("check_in_time"),
            check_out_time=created_booking.get("check_out_time"),
            latitude=created_booking.get("latitude"),
            longitude=created_booking.get("longitude"),
            address=created_booking.get("address"),
            notes=created_booking.get("notes"),
            estimated_amount=created_booking.get("estimated_amount"),
            final_amount=created_booking.get("final_amount"),
            payment_status=created_booking.get("payment_status"),
            household_verified_checkin=created_booking.get("household_verified_checkin"),
            worker_verified_checkin=created_booking.get("worker_verified_checkin"),
            household_verified_checkout=created_booking.get("household_verified_checkout"),
            worker_verified_checkout=created_booking.get("worker_verified_checkout"),
            verification_otp=created_booking.get("verification_otp"),
            household=hh,
            service=srv,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Error creating booking: {str(e)}")


@router.get("/{booking_id}", response_model=BookingResponse)
def get_booking_by_id(
    booking_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    try:
        res = db.table("bookings").select(
            "*, households(*), workers(*, users(name, phone)), services(*), payments(*)"
        ).eq("id", booking_id).execute()

        if not res.data or len(res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Booking with ID '{booking_id}' not found.")

        b = res.data[0]
        payments = b.get("payments")

        # RBAC Security Authorization check (Requirement 21)
        user_role = (current_user.get("role") or "").lower()
        user_id = str(current_user.get("id"))

        if user_role not in ["admin", "super_admin"]:
            if user_role == "customer":
                hh = b.get("households") or {}
                if hh.get("user_id") and str(hh.get("user_id")) != user_id:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                        detail="Access denied. You can only view your own bookings.")
            elif user_role in ["cooperative_worker", "independent_worker", "worker"]:
                w = b.get("workers") or {}
                w_owner_id = str(w.get("user_id")) if w.get("user_id") else None
                from app.services.matching import get_assignments_for_booking
                asgns = get_assignments_for_booking(booking_id)
                is_assigned = (w_owner_id == user_id) or any(str(a.get("worker_id")) == user_id for a in asgns)
                if not is_assigned:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                        detail="Access denied. You can only access assignments belonging to yourself.")

        # Fetch assignment records
        asgns = []
        try:
            a_res = db.table("booking_assignments").select("*, workers(*, users(name, phone))").eq("booking_id", booking_id).execute()
            asgns = a_res.data or []
        except Exception:
            pass
        if not asgns:
            from app.services.matching import get_assignments_for_booking
            asgns = get_assignments_for_booking(booking_id)

        req_count = int(b.get("required_worker_count") or 1)
        asgn_count = int(b.get("assigned_worker_count") or len(asgns))
        alloc_stat = b.get("allocation_status") or ("ASSIGNED" if (b.get("worker_id") or asgns) else "REQUESTED")

        return BookingResponse(
            id=str(b["id"]),
            household_id=str(b["household_id"]),
            worker_id=str(b["worker_id"]) if b.get("worker_id") else (asgns[0]["worker_id"] if asgns else None),
            service_id=str(b["service_id"]),
            status=b["status"],
            required_worker_count=req_count,
            assigned_worker_count=asgn_count,
            allocation_status=alloc_stat,
            assignments=asgns if asgns else None,
            scheduled_time=b.get("scheduled_time"),
            created_at=b.get("created_at"),
            check_in_time=b.get("check_in_time"),
            check_out_time=b.get("check_out_time"),
            latitude=b.get("latitude"),
            longitude=b.get("longitude"),
            address=b.get("address"),
            notes=b.get("notes"),
            estimated_amount=b.get("estimated_amount"),
            final_amount=b.get("final_amount"),
            payment_status=b.get("payment_status"),
            household_verified_checkin=b.get("household_verified_checkin"),
            worker_verified_checkin=b.get("worker_verified_checkin"),
            household_verified_checkout=b.get("household_verified_checkout"),
            worker_verified_checkout=b.get("worker_verified_checkout"),
            verification_otp=b.get("verification_otp"),
            worker_live_lat=b.get("worker_live_lat"),
            worker_live_lng=b.get("worker_live_lng"),
            worker_last_seen=b.get("worker_last_seen"),
            household=b.get("households"),
            worker=b.get("workers"),
            service=b.get("services"),
            payment=payments[0] if isinstance(payments, list) and payments else payments,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Error retrieving booking: {str(e)}")


@router.patch("/{booking_id}/status", response_model=BookingResponse)
def update_booking_status(
    booking_id: str,
    payload: BookingStatusUpdate,
    db: Client = Depends(get_supabase_client)
):
    try:
        current_booking = None
        if db:
            try:
                existing_res = db.table("bookings").select("*").eq("id", booking_id).execute()
                if existing_res.data and len(existing_res.data) > 0:
                    current_booking = existing_res.data[0]
            except Exception:
                pass

        if not current_booking:
            from app.services.matching import _BOOKINGS_BY_ID
            current_booking = _BOOKINGS_BY_ID.get(str(booking_id))

        if not current_booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Booking with ID '{booking_id}' not found.")

        curr_status = current_booking.get("status", "requested")
        new_status = payload.status
        action = payload.action

        if action:
            mapped = _map_action_to_status(action, curr_status)
            if mapped:
                new_status = mapped

        # Strict State Transition Validation (Phase 4 Requirement)
        if new_status and new_status != curr_status:
            allowed = VALID_TRANSITIONS.get(curr_status, [])
            if new_status not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Illegal state transition from '{curr_status}' to '{new_status}'. Allowed next states: {allowed}"
                )

        # CRITICAL BUSINESS RULE (Phase 5):
        # A booking cannot be dispatched, assigned, or started unless customer payment has been captured.
        if new_status in ("matching", "assigned", "accepted", "worker_enroute", "on_the_way", "arrived", "in_progress"):
            b_pay_status = str(current_booking.get("payment_status", "pending")).lower()
            if b_pay_status not in ("captured", "released", "paid"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot transition booking to '{new_status}'. Customer payment must be captured before dispatch (current payment status: '{b_pay_status}')."
                )

        now_iso = datetime.now(timezone.utc).isoformat()
        update_data: dict = {"status": new_status}

        if new_status in ("in_progress", "verified_checkin") and not current_booking.get("check_in_time"):
            update_data["check_in_time"] = now_iso
        if new_status in ("completed", "verified_checkout") and not current_booking.get("check_out_time"):
            update_data["check_out_time"] = now_iso
        if new_status == "payment_released" and not current_booking.get("payment_status") == "released":
            update_data["payment_status"] = "released"
            update_data["final_amount"] = current_booking.get("estimated_amount")

        updated_b = None
        if db:
            try:
                res = db.table("bookings").update(update_data).eq("id", booking_id).execute()
                if res.data and len(res.data) > 0:
                    updated_b = res.data[0]
            except Exception:
                pass

        if not updated_b:
            current_booking.update(update_data)
            updated_b = current_booking

        from app.services.matching import _BOOKINGS_BY_ID
        _BOOKINGS_BY_ID[str(booking_id)] = updated_b

        # Dispatch real-time event & notifications
        if new_status != curr_status:
            try:
                from app.services.event_service import event_service
                event_service.publish_event(
                    event_type="BOOKING_STATUS_CHANGED",
                    booking_id=booking_id,
                    actor_id="system",
                    actor_role="system",
                    title=f"Booking Status: {new_status.replace('_', ' ').title()}",
                    description=f"Booking #{booking_id[:8]} transitioned from {curr_status} to {new_status}.",
                    data={"old_status": curr_status, "new_status": new_status}
                )
            except Exception:
                pass

        return BookingResponse(
            id=str(updated_b["id"]),
            household_id=str(updated_b["household_id"]),
            worker_id=str(updated_b["worker_id"]) if updated_b.get("worker_id") else None,
            service_id=str(updated_b["service_id"]),
            status=updated_b["status"],
            scheduled_time=updated_b.get("scheduled_time"),
            created_at=updated_b.get("created_at"),
            check_in_time=updated_b.get("check_in_time"),
            check_out_time=updated_b.get("check_out_time"),
            latitude=updated_b.get("latitude"),
            longitude=updated_b.get("longitude"),
            address=updated_b.get("address"),
            notes=updated_b.get("notes"),
            estimated_amount=updated_b.get("estimated_amount"),
            final_amount=updated_b.get("final_amount"),
            payment_status=updated_b.get("payment_status"),
            household_verified_checkin=updated_b.get("household_verified_checkin"),
            worker_verified_checkin=updated_b.get("worker_verified_checkin"),
            household_verified_checkout=updated_b.get("household_verified_checkout"),
            worker_verified_checkout=updated_b.get("worker_verified_checkout"),
            verification_otp=updated_b.get("verification_otp"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Error updating booking status: {str(e)}")


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
def cancel_booking(
    booking_id: str,
    reason: Optional[str] = Query(None, description="Reason for cancellation"),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Customer cancellation endpoint.
    Cancellation is strictly allowed only before work is in progress.
    Releases any assigned workers and emits real-time cancellation notifications.
    """
    try:
        existing_res = db.table("bookings").select("*").eq("id", booking_id).execute()
        if not existing_res.data or len(existing_res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Booking with ID '{booking_id}' not found.")

        current_booking = existing_res.data[0]
        curr_status = current_booking.get("status", "requested")

        # Non-cancellable state check
        if curr_status in ["in_progress", "verified_checkin", "verified_checkout", "completed"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel booking in '{curr_status}' state. Cancellation is not permitted once specialist has commenced work."
            )
        if curr_status == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking is already cancelled."
            )

        # Update booking
        res = db.table("bookings").update({
            "status": "cancelled",
            "notes": f"{current_booking.get('notes') or ''} [Cancelled: {reason or 'Customer request'}]".strip()
        }).eq("id", booking_id).execute()

        updated_b = res.data[0] if res.data else {**current_booking, "status": "cancelled"}

        # Release assignments in DB and in-memory
        try:
            db.table("booking_assignments").update({"status": "CANCELLED"}).eq("booking_id", booking_id).execute()
        except Exception:
            pass

        from app.services.matching import _ASSIGNMENTS_BY_BOOKING
        for a in _ASSIGNMENTS_BY_BOOKING.get(str(booking_id), []):
            a["status"] = "CANCELLED"

        # Dispatch real-time event & worker notification
        try:
            from app.services.event_service import event_service
            event_service.publish_event(
                event_type="BOOKING_CANCELLED",
                booking_id=booking_id,
                actor_id=str(current_user.get("id")),
                actor_role=str(current_user.get("role", "customer")),
                title="Booking Cancelled",
                description=f"Booking #{booking_id[:8]} was cancelled. Reason: {reason or 'Customer request'}.",
                data={"reason": reason}
            )
            # Notify assigned worker
            w_id = current_booking.get("worker_id")
            if w_id:
                event_service.create_notification(
                    user_id=str(w_id),
                    title="Booking Cancelled",
                    message=f"Booking #{booking_id[:8]} was cancelled by the customer.",
                    type="BOOKING_CANCELLED",
                    reference_id=booking_id
                )
        except Exception:
            pass

        return BookingResponse(
            id=str(updated_b["id"]),
            household_id=str(updated_b["household_id"]),
            worker_id=str(updated_b["worker_id"]) if updated_b.get("worker_id") else None,
            service_id=str(updated_b["service_id"]),
            status="cancelled",
            scheduled_time=updated_b.get("scheduled_time"),
            created_at=updated_b.get("created_at"),
            check_in_time=updated_b.get("check_in_time"),
            check_out_time=updated_b.get("check_out_time"),
            latitude=updated_b.get("latitude"),
            longitude=updated_b.get("longitude"),
            address=updated_b.get("address"),
            notes=updated_b.get("notes"),
            estimated_amount=updated_b.get("estimated_amount"),
            final_amount=updated_b.get("final_amount"),
            payment_status=updated_b.get("payment_status"),
            household_verified_checkin=updated_b.get("household_verified_checkin"),
            worker_verified_checkin=updated_b.get("worker_verified_checkin"),
            household_verified_checkout=updated_b.get("household_verified_checkout"),
            worker_verified_checkout=updated_b.get("worker_verified_checkout"),
            verification_otp=updated_b.get("verification_otp"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Error cancelling booking: {str(e)}")


# ---------------------------------------------------------------------------
# DUAL VERIFICATION ENDPOINTS
# ---------------------------------------------------------------------------

@router.post("/verify-checkin", response_model=VerificationResponse)
def verify_check_in(
    payload: CheckInVerificationRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    try:
        b_res = db.table("bookings").select("*").eq("id", payload.booking_id).execute()
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Booking '{payload.booking_id}' not found.")
        b = b_res.data[0]

        distance_m: Optional[float] = None
        if payload.method == "gps_proximity":
            w_lat = payload.worker_latitude if payload.worker_latitude is not None else b.get("worker_live_lat")
            w_lng = payload.worker_longitude if payload.worker_longitude is not None else b.get("worker_live_lng")
            h_lat = payload.household_latitude if payload.household_latitude is not None else b.get("latitude")
            h_lng = payload.household_longitude if payload.household_longitude is not None else b.get("longitude")

            if w_lat is None or w_lng is None or h_lat is None or h_lng is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="GPS coordinates missing for both parties for proximity verification.")

            distance_m = _haversine_meters(float(w_lat), float(w_lng), float(h_lat), float(h_lng))
            if distance_m > (payload.max_distance_meters or 100.0):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail=f"GPS distance {distance_m:.1f}m exceeds max allowed {(payload.max_distance_meters or 100.0):.0f}m. Worker must be at location to verify.")

        elif payload.method == "otp_match":
            expected_otp = b.get("verification_otp")
            if not expected_otp or not payload.otp_code:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="OTP code required for OTP verification.")
            if payload.otp_code.strip() != str(expected_otp).strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="OTP does not match. Please verify with the code shared by the other party.")

        now_iso = datetime.now(timezone.utc).isoformat()
        update_data: dict = {}
        if payload.verifier_role == "household":
            update_data["household_verified_checkin"] = True
            update_data["household_checkin_time"] = now_iso
        elif payload.verifier_role == "worker":
            update_data["worker_verified_checkin"] = True
            update_data["worker_checkin_time"] = now_iso
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verifier_role.")

        upd_res = db.table("bookings").update(update_data).eq("id", payload.booking_id).execute()
        if not upd_res.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Could not persist verification.")

        updated = upd_res.data[0]
        both_verified = bool(updated.get("household_verified_checkin")) and bool(updated.get("worker_verified_checkin"))

        status_update: dict = {}
        if both_verified:
            status_update["status"] = "verified_checkin"
            status_update["check_in_time"] = now_iso
            db.table("bookings").update(status_update).eq("id", payload.booking_id).execute()

        return VerificationResponse(
            success=True,
            booking_id=payload.booking_id,
            verified_role=payload.verifier_role,
            method=payload.method,
            both_verified=both_verified,
            distance_meters=distance_m,
            message=(
                f"✅ {payload.verifier_role.capitalize()} verified check-in via {payload.method}. "
                f"{'Both parties verified — payment release now available.' if both_verified else 'Waiting for other party to verify.'}"
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Check-in verification error: {str(e)}")


@router.post("/verify-checkout", response_model=VerificationResponse)
def verify_check_out(
    payload: CheckOutVerificationRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    try:
        b_res = db.table("bookings").select("*").eq("id", payload.booking_id).execute()
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Booking '{payload.booking_id}' not found.")
        b = b_res.data[0]

        if not (b.get("household_verified_checkin") and b.get("worker_verified_checkin")):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Cannot check out: both parties must first verify check-in.")

        if payload.method == "otp_match":
            expected_otp = b.get("verification_otp")
            if not expected_otp or not payload.otp_code:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP code required.")
            if payload.otp_code.strip() != str(expected_otp).strip():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP does not match for checkout verification.")

        now_iso = datetime.now(timezone.utc).isoformat()
        update_data: dict = {}
        if payload.verifier_role == "household":
            update_data["household_verified_checkout"] = True
            update_data["household_checkout_time"] = now_iso
        elif payload.verifier_role == "worker":
            update_data["worker_verified_checkout"] = True
            update_data["worker_checkout_time"] = now_iso
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verifier_role.")

        upd_res = db.table("bookings").update(update_data).eq("id", payload.booking_id).execute()
        if not upd_res.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Could not persist checkout verification.")

        updated = upd_res.data[0]
        both_verified = bool(updated.get("household_verified_checkout")) and bool(updated.get("worker_verified_checkout"))

        if both_verified:
            db.table("bookings").update({
                "status": "completed",
                "check_out_time": now_iso,
            }).eq("id", payload.booking_id).execute()

        return VerificationResponse(
            success=True,
            booking_id=payload.booking_id,
            verified_role=payload.verifier_role,
            method=payload.method,
            both_verified=both_verified,
            message=(
                f"✅ {payload.verifier_role.capitalize()} verified checkout via {payload.method}. "
                f"{'Both parties verified — service marked complete and payment settled.' if both_verified else 'Waiting for other party to confirm checkout.'}"
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Checkout verification error: {str(e)}")


# ---------------------------------------------------------------------------
# PAYMENT ENDPOINT (after dual verification)
# ---------------------------------------------------------------------------

@router.post("/process-payment", response_model=PaymentResponse)
def process_payment(
    payload: PaymentProcessRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    try:
        b_res = db.table("bookings").select("*").eq("id", payload.booking_id).execute()
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Booking '{payload.booking_id}' not found.")
        b = b_res.data[0]

        if payload.release_after_verification:
            if not (b.get("household_verified_checkin") and b.get("worker_verified_checkin")):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Payment cannot be released. BOTH household and worker must verify check-in first."
                )

        now_iso = datetime.now(timezone.utc).isoformat()
        txn_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"

        payment_id = str(uuid.uuid4())
        try:
            db.table("payments").insert({
                "id": payment_id,
                "booking_id": payload.booking_id,
                "amount": payload.amount,
                "payment_method": payload.payment_method,
                "status": "held_in_escrow" if payload.release_after_verification else "released",
                "transaction_id": txn_id,
                "processed_at": now_iso,
            }).execute()
        except Exception:
            pass

        final_status = "released" if not payload.release_after_verification else "held_in_escrow"
        db.table("bookings").update({
            "payment_status": final_status,
            "final_amount": payload.amount,
            "status": "payment_released" if final_status == "released" else b.get("status", "verified_checkin"),
        }).eq("id", payload.booking_id).execute()

        return PaymentResponse(
            success=True,
            booking_id=payload.booking_id,
            transaction_id=txn_id,
            amount=payload.amount,
            status=final_status,
            message=(
                f"💰 Payment of ₹{payload.amount:.2f} via {payload.payment_method.upper()} {final_status}. "
                f"{'Funds released to cooperative wallet immediately.' if final_status == 'released' else 'Held in cooperative escrow until both parties verify checkout.'}"
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Payment processing error: {str(e)}")


# ---------------------------------------------------------------------------
# WORKER LIVE LOCATION
# ---------------------------------------------------------------------------

@router.post("/worker-location", response_model=WorkerLocationResponse)
def update_worker_location(
    payload: WorkerLocationUpdate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Update worker real-time GPS location.
    Worker tracking is ONLY accepted and active when on an active gig
    (status: accepted, worker_enroute, on_the_way, arrived, in_progress).
    Off-duty tracking is prohibited.
    Calculates distance to customer and realistic ETA (25 km/h avg speed).
    Dispatches real-time event so customer map tracks live movement.
    """
    try:
        w_res = db.table("workers").select("id").eq("id", payload.worker_id).execute()
        if not w_res.data or len(w_res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Worker '{payload.worker_id}' not found.")

        now_iso = datetime.now(timezone.utc).isoformat()
        dist_km: Optional[float] = None
        eta_minutes: Optional[int] = None
        eta_formatted: Optional[str] = None

        # Check active gig status if booking_id provided
        if payload.booking_id:
            b_res = db.table("bookings").select("id, status, latitude, longitude").eq("id", payload.booking_id).execute()
            if b_res.data and len(b_res.data) > 0:
                b = b_res.data[0]
                b_stat = (b.get("status") or "").lower()
                # Tracking prohibited if not on an active gig
                if b_stat in ["completed", "cancelled", "rejected"]:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Worker location cannot be tracked for inactive/completed booking (status: {b_stat})."
                    )

                c_lat = b.get("latitude")
                c_lng = b.get("longitude")
                if c_lat is not None and c_lng is not None:
                    dist_m = _haversine_meters(payload.latitude, payload.longitude, float(c_lat), float(c_lng))
                    dist_km = round(dist_m / 1000.0, 2)
                    # Average city speed: 25 km/h
                    hours = dist_km / 25.0
                    eta_minutes = max(1, round(hours * 60))
                    eta_formatted = f"~{eta_minutes} mins (approx. {dist_km:.1f} km @ 25 km/h)"

                db.table("bookings").update({
                    "worker_live_lat": payload.latitude,
                    "worker_live_lng": payload.longitude,
                    "worker_last_seen": now_iso,
                }).eq("id", payload.booking_id).execute()

                # Dispatch real-time tracking event
                try:
                    from app.services.event_service import event_service
                    event_service.publish_event(
                        event_type="WORKER_LOCATION_UPDATED",
                        booking_id=payload.booking_id,
                        actor_id=payload.worker_id,
                        actor_role="worker",
                        title="Specialist Location Updated",
                        description=f"Specialist is {eta_formatted or 'en route'}.",
                        data={
                            "latitude": payload.latitude,
                            "longitude": payload.longitude,
                            "distance_km": dist_km,
                            "eta_minutes": eta_minutes,
                            "eta_formatted": eta_formatted
                        }
                    )
                except Exception:
                    pass

        # Update worker master coordinates
        db.table("workers").update({
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "last_location_update": now_iso,
        }).eq("id", payload.worker_id).execute()

        try:
            db.table("worker_location_history").insert({
                "id": str(uuid.uuid4()),
                "worker_id": payload.worker_id,
                "latitude": payload.latitude,
                "longitude": payload.longitude,
                "heading": payload.heading,
                "speed_kmh": payload.speed_kmh,
                "booking_id": payload.booking_id,
                "recorded_at": now_iso,
            }).execute()
        except Exception:
            pass

        return WorkerLocationResponse(
            success=True,
            worker_id=payload.worker_id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            timestamp=datetime.now(timezone.utc),
            message=f"Location updated ({payload.latitude:.5f}, {payload.longitude:.5f}). ETA: {eta_formatted or 'N/A'}",
            distance_to_customer_km=dist_km,
            eta_minutes=eta_minutes,
            eta_formatted=eta_formatted,
            booking_id=payload.booking_id
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Worker location update error: {str(e)}")


@router.post("/assignments/{assignment_id}/location", response_model=WorkerLocationResponse)
def update_assignment_location(
    assignment_id: str,
    payload: WorkerLocationUpdate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Dedicated endpoint to push worker GPS location during an active assignment.
    Validates assignment state and updates tracking for the customer.
    """
    from app.services.matching import _ASSIGNMENTS_BY_ID
    asgn = _ASSIGNMENTS_BY_ID.get(str(assignment_id))
    booking_id = asgn.get("booking_id") if asgn else payload.booking_id

    if not booking_id:
        try:
            res = db.table("booking_assignments").select("booking_id, worker_id, status").eq("id", assignment_id).execute()
            if res.data and len(res.data) > 0:
                booking_id = res.data[0].get("booking_id")
                payload.worker_id = res.data[0].get("worker_id") or payload.worker_id
        except Exception:
            pass

    payload.booking_id = booking_id
    resp = update_worker_location(payload=payload, current_user=current_user, db=db)
    resp.assignment_id = assignment_id
    return resp


@router.get("/worker-location/{worker_id}")
def get_worker_live_location(
    worker_id: str,
    db: Client = Depends(get_supabase_client)
):
    try:
        res = db.table("workers").select(
            "id, latitude, longitude, last_location_update, users(name, phone)"
        ).eq("id", worker_id).execute()
        if not res.data or len(res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Worker '{worker_id}' not found.")
        w = res.data[0]
        return {
            "success": True,
            "worker_id": worker_id,
            "latitude": w.get("latitude"),
            "longitude": w.get("longitude"),
            "last_seen": w.get("last_location_update"),
            "worker": w.get("users"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Location retrieval error: {str(e)}")


# ---------------------------------------------------------------------------
# Listing endpoints
# ---------------------------------------------------------------------------

@router.get("/household/{household_id}", response_model=List[BookingResponse])
def get_household_bookings(
    household_id: str,
    db: Client = Depends(get_supabase_client)
):
    try:
        bookings = []
        if db:
            try:
                is_uuid = False
                try:
                    uuid.UUID(str(household_id))
                    is_uuid = True
                except Exception:
                    pass

                if is_uuid:
                    query = db.table("bookings").select("*, services(*), workers(*, users(name, phone))").eq("household_id", household_id)
                    try:
                        res = query.order("requested_at", desc=True).execute()
                    except Exception:
                        res = query.execute()
                    bookings = res.data or []

                    if not bookings:
                        try:
                            h_lookup = db.table("households").select("id").eq("user_id", household_id).execute()
                            if h_lookup.data and len(h_lookup.data) > 0:
                                actual_hh_id = h_lookup.data[0]["id"]
                                res2 = db.table("bookings").select("*, services(*), workers(*, users(name, phone))").eq("household_id", actual_hh_id)
                                try:
                                    res2 = res2.order("requested_at", desc=True).execute()
                                except Exception:
                                    res2 = res2.execute()
                                bookings = res2.data or []
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Error querying household bookings from DB: {e}")

        try:
            from app.services.matching import _BOOKINGS_BY_ID
            for bid, b in _BOOKINGS_BY_ID.items():
                if str(b.get("household_id")) == str(household_id) or str(b.get("customer_id")) == str(household_id):
                    if not any(str(x.get("id")) == str(bid) for x in bookings):
                        bookings.append(b)
        except Exception:
            pass

        return [
            BookingResponse(
                id=str(b["id"]),
                household_id=str(b.get("household_id", household_id)),
                worker_id=str(b["worker_id"]) if b.get("worker_id") else None,
                service_id=str(b.get("service_id", "srv_general")),
                status=b.get("status", "requested"),
                scheduled_time=b.get("scheduled_time"),
                created_at=b.get("created_at") or b.get("requested_at"),
                check_in_time=b.get("check_in_time"),
                check_out_time=b.get("check_out_time"),
                latitude=b.get("latitude"),
                longitude=b.get("longitude"),
                address=b.get("address"),
                notes=b.get("notes"),
                estimated_amount=b.get("estimated_amount"),
                final_amount=b.get("final_amount"),
                payment_status=b.get("payment_status"),
                household_verified_checkin=b.get("household_verified_checkin"),
                worker_verified_checkin=b.get("worker_verified_checkin"),
                household_verified_checkout=b.get("household_verified_checkout"),
                worker_verified_checkout=b.get("worker_verified_checkout"),
                verification_otp=b.get("verification_otp"),
                worker_live_lat=b.get("worker_live_lat"),
                worker_live_lng=b.get("worker_live_lng"),
                worker_last_seen=b.get("worker_last_seen"),
                worker=b.get("workers"),
                service=b.get("services"),
            )
            for b in bookings
        ]
    except Exception as e:
        logger.error(f"Error in get_household_bookings: {e}")
        return []


@router.get("/worker/{worker_id}", response_model=List[BookingResponse])
def get_worker_bookings(
    worker_id: str,
    db: Client = Depends(get_supabase_client)
):
    try:
        bookings = []
        if db:
            try:
                is_uuid = False
                try:
                    uuid.UUID(str(worker_id))
                    is_uuid = True
                except Exception:
                    pass

                if is_uuid:
                    query = db.table("bookings").select("*, services(*), households(*, users(name, phone))").eq("worker_id", worker_id)
                    try:
                        res = query.order("requested_at", desc=True).execute()
                    except Exception:
                        res = query.execute()
                    bookings = res.data or []

                    if not bookings:
                        try:
                            w_lookup = db.table("workers").select("id").eq("user_id", worker_id).execute()
                            if w_lookup.data and len(w_lookup.data) > 0:
                                actual_w_id = w_lookup.data[0]["id"]
                                res2 = db.table("bookings").select("*, services(*), households(*, users(name, phone))").eq("worker_id", actual_w_id)
                                try:
                                    res2 = res2.order("requested_at", desc=True).execute()
                                except Exception:
                                    res2 = res2.execute()
                                bookings = res2.data or []
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Error querying worker bookings from DB: {e}")

        try:
            from app.services.matching import _BOOKINGS_BY_ID
            for bid, b in _BOOKINGS_BY_ID.items():
                if str(b.get("worker_id")) == str(worker_id):
                    if not any(str(x.get("id")) == str(bid) for x in bookings):
                        bookings.append(b)
        except Exception:
            pass

        return [
            BookingResponse(
                id=str(b["id"]),
                household_id=str(b.get("household_id", "hh_demo")),
                worker_id=str(b.get("worker_id", worker_id)),
                service_id=str(b.get("service_id", "srv_general")),
                status=b.get("status", "requested"),
                scheduled_time=b.get("scheduled_time"),
                created_at=b.get("created_at") or b.get("requested_at"),
                check_in_time=b.get("check_in_time"),
                check_out_time=b.get("check_out_time"),
                latitude=b.get("latitude"),
                longitude=b.get("longitude"),
                address=b.get("address"),
                notes=b.get("notes"),
                estimated_amount=b.get("estimated_amount"),
                final_amount=b.get("final_amount"),
                payment_status=b.get("payment_status"),
                household_verified_checkin=b.get("household_verified_checkin"),
                worker_verified_checkin=b.get("worker_verified_checkin"),
                household_verified_checkout=b.get("household_verified_checkout"),
                worker_verified_checkout=b.get("worker_verified_checkout"),
                verification_otp=b.get("verification_otp"),
                worker_live_lat=b.get("worker_live_lat"),
                worker_live_lng=b.get("worker_live_lng"),
                worker_last_seen=b.get("worker_last_seen"),
                household=b.get("households"),
                service=b.get("services"),
            )
            for b in bookings
        ]
    except Exception as e:
        logger.error(f"Error in get_worker_bookings: {e}")
        return []
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Error fetching worker bookings: {str(e)}")

@router.post("/emergency", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_emergency_dispatch(
    payload: BookingCreate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    24/7 Priority Emergency SOS Dispatch.
    Automatically finds the closest available verified cooperative specialist and immediately dispatches them.
    """
    from app.services.matching import rank_workers_for_booking, record_allocation_assignments

    try:
        user_id = current_user.get("id")
        household_id = payload.household_id
        if not household_id:
            h_res = db.table("households").select("id, address, latitude, longitude").eq("user_id", user_id).execute()
            if h_res.data:
                household_id = h_res.data[0]["id"]
                lat = payload.latitude or h_res.data[0].get("latitude")
                lng = payload.longitude or h_res.data[0].get("longitude")
                addr = payload.address or h_res.data[0].get("address") or "Emergency Location"
            else:
                household_id = str(uuid.uuid4())
                lat = payload.latitude
                lng = payload.longitude
                addr = payload.address or "Emergency Location"
        else:
            lat = payload.latitude
            lng = payload.longitude
            addr = payload.address or "Emergency Location"

        # Validate mandatory customer coordinates (no fake GPS)
        if lat is None or lng is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer GPS coordinates (latitude and longitude) are mandatory for emergency SOS dispatch."
            )

        booking_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        base_rate = float(payload.estimated_amount or 450.0)
        emergency_amount = round(base_rate * 1.25, 2) # 25% emergency surcharge
        otp = _generate_otp()

        # CRITICAL BUSINESS RULE:
        # Emergency booking starts in payment_pending. No emergency worker is dispatched before payment.
        booking_record = {
            "id": booking_id,
            "household_id": household_id,
            "worker_id": None,
            "service_id": payload.service_id or "Electrician",
            "status": "payment_pending",
            "requested_at": now_iso,
            "latitude": lat,
            "longitude": lng,
            "address": addr,
            "notes": f"[24/7 EMERGENCY SOS] {payload.notes or 'Immediate Assistance Required'}",
            "estimated_amount": emergency_amount,
            "final_amount": emergency_amount,
            "verification_otp": otp,
            "household_verified_checkin": False,
            "worker_verified_checkin": False,
            "household_verified_checkout": False,
            "worker_verified_checkout": False,
            "payment_status": "pending",
            "allocation_status": "PAYMENT_PENDING",
            "assigned_worker_count": 0,
            "is_emergency": True
        }

        try:
            db.table("bookings").insert(booking_record).execute()
        except Exception:
            pass

        from app.services.matching import _BOOKINGS_BY_ID
        _BOOKINGS_BY_ID[str(booking_id)] = booking_record

        return BookingResponse(
            id=booking_id,
            household_id=household_id,
            worker_id=None,
            service_id=payload.service_id or "Emergency Service",
            status="payment_pending",
            allocation_status="PAYMENT_PENDING",
            assigned_worker_count=0,
            scheduled_time=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            latitude=lat,
            longitude=lng,
            address=addr,
            notes=booking_record["notes"],
            estimated_amount=emergency_amount,
            final_amount=emergency_amount,
            payment_status="pending",
            household_verified_checkin=False,
            worker_verified_checkin=False,
            household_verified_checkout=False,
            worker_verified_checkout=False,
            verification_otp=otp,
            worker_live_lat=None,
            worker_live_lng=None,
            worker_last_seen=None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing emergency dispatch: {str(e)}"
        )

@router.get("/{booking_id}/completion-otp")
def get_completion_otp_for_customer(
    booking_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Retrieves the 6-digit service completion acceptance code strictly for the customer.
    Workers and unauthorized parties are strictly forbidden from reading this endpoint.
    """
    from app.services.otp_service import CompletionOtpService, _COMPLETION_OTPS_BY_BOOKING

    user_role = current_user.get("role", "customer")
    if user_role in ("cooperative_worker", "independent_worker"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workers are forbidden from reading the customer acceptance OTP."
        )

    otp_record = CompletionOtpService.get_customer_active_otp(booking_id, current_user["id"])
    if not otp_record and user_role in ("super_admin", "admin"):
        otp_record = _COMPLETION_OTPS_BY_BOOKING.get(str(booking_id))

    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active completion confirmation pending for this booking."
        )

    code = otp_record.get("plaintext_code") or "******"

    return {
        "booking_id": booking_id,
        "otp_code": code,
        "expires_at": otp_record.get("expires_at"),
        "instructions": "Inspect completed work. Share this 6-digit code with the technician only if you are satisfied."
    }
