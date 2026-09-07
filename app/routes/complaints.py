import uuid
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.db.supabase_client import get_supabase_client
from app.core.dependencies import get_current_user, require_role
from app.models.complaint import (
    ComplaintCreate,
    ComplaintResponse,
    ComplaintResolveRequest,
    ComplaintListResponse
)
from app.services.payment_service import PaymentService, _PAYMENTS_BY_BOOKING_ID
from app.services.matching import _BOOKINGS_BY_ID
from app.services.event_service import EventService

logger = logging.getLogger("complaints_router")

_COMPLAINTS_BY_ID: Dict[str, Dict[str, Any]] = {}
_COMPLAINTS_BY_BOOKING: Dict[str, List[Dict[str, Any]]] = {}

router = APIRouter(prefix="/complaints", tags=["Complaints & Disputes"])

@router.post("/", response_model=ComplaintResponse, status_code=status.HTTP_201_CREATED)
def raise_complaint(
    payload: ComplaintCreate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Customer files a problem report / dispute for a booking.
    Immediately freezes settlement by marking settlement_status = 'DISPUTED'.
    """
    bid = payload.booking_id
    booking = _BOOKINGS_BY_ID.get(bid)

    if not booking and db:
        try:
            res = db.table("bookings").select("*").eq("id", bid).execute()
            if res.data and len(res.data) > 0:
                booking = res.data[0]
                _BOOKINGS_BY_ID[bid] = booking
        except Exception:
            pass

    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Booking '{bid}' not found.")

    cid = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    coop_id = booking.get("cooperative_id")

    complaint_record = {
        "id": cid,
        "booking_id": bid,
        "customer_id": current_user["id"],
        "cooperative_id": coop_id,
        "assignment_id": payload.assignment_id,
        "category": payload.category,
        "description": payload.description,
        "status": "OPEN",
        "resolution_notes": None,
        "resolved_by": None,
        "resolved_at": None,
        "created_at": now_iso
    }

    _COMPLAINTS_BY_ID[cid] = complaint_record
    if bid not in _COMPLAINTS_BY_BOOKING:
        _COMPLAINTS_BY_BOOKING[bid] = []
    _COMPLAINTS_BY_BOOKING[bid].append(complaint_record)

    # Freeze settlement to DISPUTED
    booking["settlement_status"] = "DISPUTED"
    _BOOKINGS_BY_ID[bid] = booking

    pay_rec = _PAYMENTS_BY_BOOKING_ID.get(bid)
    if pay_rec and pay_rec.get("status") == "CAPTURED":
        pay_rec["settlement_status"] = "DISPUTED"

    if db:
        try:
            db.table("complaints").insert(complaint_record).execute()
            db.table("bookings").update({"settlement_status": "DISPUTED"}).eq("id", bid).execute()
        except Exception as e:
            logger.debug(f"DB insert complaint note: {e}")

    # Financial audit log
    PaymentService.record_audit(
        action="COMPLAINT_CREATED",
        booking_id=bid,
        actor_id=current_user["id"],
        actor_role=current_user.get("role", "customer"),
        metadata={"complaint_id": cid, "category": payload.category, "settlement_status": "DISPUTED"},
        db=db
    )

    # Notify customer and association head
    EventService.dispatch_event(
        event_type="COMPLAINT_CREATED",
        booking_id=bid,
        actor_id=current_user["id"],
        actor_role="customer",
        data={"complaint_id": cid, "category": payload.category},
        target_user_ids=[current_user["id"]],
        notification_title="Dispute Opened",
        notification_message=f"Dispute raised for category '{payload.category}'. Payout settlement has been put on hold.",
        db=db
    )

    return ComplaintResponse(**complaint_record)

@router.get("/cooperative/{cooperative_id}", response_model=ComplaintListResponse)
def get_cooperative_complaints(
    cooperative_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Retrieves disputes for an association.
    Association Heads can ONLY view complaints belonging to their own cooperative.
    """
    user_role = current_user.get("role")
    user_coop = current_user.get("cooperative_id")

    if user_role == "cooperative_association_head":
        if str(user_coop) != str(cooperative_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Association Head can only view complaints for their own society."
            )
    elif user_role not in ("super_admin", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized access.")

    # Filter complaints
    results = [c for c in _COMPLAINTS_BY_ID.values() if str(c.get("cooperative_id")) == str(cooperative_id)]

    if db and len(results) == 0:
        try:
            res = db.table("complaints").select("*").eq("cooperative_id", cooperative_id).execute()
            if res.data:
                results = res.data
        except Exception:
            pass

    return ComplaintListResponse(
        total=len(results),
        complaints=[ComplaintResponse(**c) for c in results]
    )

@router.get("/", response_model=ComplaintListResponse)
def get_all_complaints(
    current_user: dict = Depends(require_role(["super_admin"])),
    db: Client = Depends(get_supabase_client)
):
    """
    Platform-wide complaints list. Super Admin only.
    """
    results = list(_COMPLAINTS_BY_ID.values())
    if db and len(results) == 0:
        try:
            res = db.table("complaints").select("*").order("created_at", desc=True).execute()
            if res.data:
                results = res.data
        except Exception:
            pass

    return ComplaintListResponse(
        total=len(results),
        complaints=[ComplaintResponse(**c) for c in results]
    )

@router.patch("/{complaint_id}/resolve", response_model=ComplaintResponse)
def resolve_complaint(
    complaint_id: str,
    payload: ComplaintResolveRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Resolves or updates status of a complaint.
    If status is REFUNDED, Super Admin authority is strictly required.
    """
    user_role = current_user.get("role")
    if payload.status == "REFUNDED" and user_role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Super Admin has platform authority to issue financial refunds."
        )

    if user_role not in ("super_admin", "cooperative_association_head"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized.")

    rec = _COMPLAINTS_BY_ID.get(complaint_id)
    if not rec and db:
        try:
            res = db.table("complaints").select("*").eq("id", complaint_id).execute()
            if res.data:
                rec = res.data[0]
        except Exception:
            pass

    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complaint not found.")

    if user_role == "cooperative_association_head":
        if str(rec.get("cooperative_id")) != str(current_user.get("cooperative_id")):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for other cooperative disputes.")

    now_iso = datetime.now(timezone.utc).isoformat()
    rec["status"] = payload.status
    rec["resolution_notes"] = payload.resolution_notes
    rec["resolved_by"] = current_user["id"]
    rec["resolved_at"] = now_iso

    _COMPLAINTS_BY_ID[complaint_id] = rec

    bid = rec.get("booking_id")
    booking = _BOOKINGS_BY_ID.get(bid)

    # Process refund if REFUNDED
    if payload.status == "REFUNDED" and bid:
        pay_rec = _PAYMENTS_BY_BOOKING_ID.get(bid)
        if pay_rec:
            try:
                PaymentService.process_refund(
                    payment_id=pay_rec["id"],
                    actor_id=current_user["id"],
                    actor_role=user_role,
                    amount=payload.refund_amount,
                    reason=payload.resolution_notes,
                    db=db
                )
            except Exception as e:
                logger.warning(f"Complaint refund note: {e}")
        if booking:
            booking["settlement_status"] = "SETTLED"
    elif payload.status == "RESOLVED":
        if booking:
            booking["settlement_status"] = "ELIGIBLE"

    if db:
        try:
            db.table("complaints").update(rec).eq("id", complaint_id).execute()
            if booking:
                db.table("bookings").update({"settlement_status": booking.get("settlement_status")}).eq("id", bid).execute()
        except Exception as e:
            logger.debug(f"DB update complaint note: {e}")

    PaymentService.record_audit(
        action="DISPUTE_RESOLVED",
        booking_id=bid or "N/A",
        actor_id=current_user["id"],
        actor_role=user_role,
        metadata={"complaint_id": complaint_id, "resolution": payload.status, "notes": payload.resolution_notes},
        db=db
    )

    return ComplaintResponse(**rec)
