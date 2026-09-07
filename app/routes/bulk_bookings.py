import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.db.supabase_client import get_supabase_client
from app.core.dependencies import get_current_user, require_role
from app.models.bulk_booking import (
    BulkBookingCreateRequest,
    BulkBookingResponse,
    BulkBookingItemResponse,
    BulkAssignResponse,
)
from app.services.matching import rank_workers_for_booking

router = APIRouter(prefix="/bulk-bookings", tags=["Institutional Multi-Trade Bulk Procurement"])

@router.post("", response_model=BulkBookingResponse)
def create_bulk_booking(
    payload: BulkBookingCreateRequest,
    db: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user)
):
    """
    Create an Institutional Multi-Trade Bulk Booking (e.g. 5 Cleaners + 2 Electricians).
    """
    customer_id = current_user.get("id") or str(uuid.uuid4())
    bulk_id = str(uuid.uuid4())

    total_workers_req = sum(item.quantity_requested for item in payload.trades)
    total_est_amount = sum(item.quantity_requested * (item.rate_per_worker or 350.0) * 4.0 for item in payload.trades) # 4 hrs standard

    if payload.is_emergency:
        total_est_amount *= 1.25

    bulk_record = {
        "id": bulk_id,
        "customer_id": customer_id,
        "institution_name": payload.institution_name,
        "contact_person": payload.contact_person,
        "contact_phone": payload.contact_phone,
        "service_address": payload.service_address,
        "latitude": payload.latitude or 12.9716,
        "longitude": payload.longitude or 77.5946,
        "scheduled_date": payload.scheduled_date,
        "scheduled_time": payload.scheduled_time,
        "total_workers_requested": total_workers_req,
        "total_workers_assigned": 0,
        "status": "requested",
        "total_estimated_amount": round(total_est_amount, 2),
        "payment_status": "pending",
        "is_emergency": payload.is_emergency,
        "notes": payload.notes,
        "created_at": datetime.utcnow().isoformat()
    }

    try:
        db.table("bulk_bookings").insert(bulk_record).execute()
    except Exception:
        pass

    items_response = []
    for trade in payload.trades:
        item_id = str(uuid.uuid4())
        item_row = {
            "id": item_id,
            "bulk_booking_id": bulk_id,
            "service_id": trade.service_id,
            "trade_name": trade.trade_name,
            "quantity_requested": trade.quantity_requested,
            "quantity_assigned": 0,
            "rate_per_worker": trade.rate_per_worker or 350.0,
            "created_at": datetime.utcnow().isoformat()
        }
        try:
            db.table("bulk_booking_items").insert(item_row).execute()
        except Exception:
            pass

        items_response.append(BulkBookingItemResponse(
            id=item_id,
            trade_name=trade.trade_name,
            quantity_requested=trade.quantity_requested,
            quantity_assigned=0,
            rate_per_worker=trade.rate_per_worker or 350.0
        ))

    return BulkBookingResponse(
        id=bulk_id,
        customer_id=customer_id,
        institution_name=payload.institution_name,
        contact_person=payload.contact_person,
        contact_phone=payload.contact_phone,
        service_address=payload.service_address,
        scheduled_date=payload.scheduled_date,
        scheduled_time=payload.scheduled_time,
        total_workers_requested=total_workers_req,
        total_workers_assigned=0,
        status="requested",
        total_estimated_amount=round(total_est_amount, 2),
        payment_status="pending",
        is_emergency=payload.is_emergency,
        notes=payload.notes,
        created_at=datetime.utcnow(),
        items=items_response
    )

@router.get("", response_model=List[BulkBookingResponse])
def list_bulk_bookings(
    db: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user)
):
    """
    List all bulk bookings. Customers view their own; Association Heads & Super Admin view platform bulk requests.
    """
    user_role = (current_user.get("role") or "").lower()
    user_id = current_user.get("id")

    try:
        query = db.table("bulk_bookings").select("*, bulk_booking_items(*)")
        if user_role not in ["super_admin", "cooperative_association_head", "admin"]:
            if user_id:
                query = query.eq("customer_id", user_id)
        
        res = query.order("created_at", desc=True).execute()
        rows = res.data or []

        results = []
        for r in rows:
            raw_items = r.get("bulk_booking_items") or []
            parsed_items = [
                BulkBookingItemResponse(
                    id=str(it.get("id")),
                    trade_name=it.get("trade_name", "Service Trade"),
                    quantity_requested=int(it.get("quantity_requested", 1)),
                    quantity_assigned=int(it.get("quantity_assigned", 0)),
                    rate_per_worker=float(it.get("rate_per_worker", 350.0))
                )
                for it in raw_items
            ]
            results.append(BulkBookingResponse(
                id=str(r["id"]),
                customer_id=str(r.get("customer_id")),
                institution_name=r.get("institution_name"),
                contact_person=r.get("contact_person", "Contact"),
                contact_phone=r.get("contact_phone", ""),
                service_address=r.get("service_address", "Service Location"),
                scheduled_date=str(r.get("scheduled_date", "Today")),
                scheduled_time=str(r.get("scheduled_time", "09:00 AM")),
                total_workers_requested=int(r.get("total_workers_requested", 1)),
                total_workers_assigned=int(r.get("total_workers_assigned", 0)),
                status=r.get("status", "requested"),
                total_estimated_amount=float(r.get("total_estimated_amount", 0.0)),
                payment_status=r.get("payment_status", "pending"),
                is_emergency=bool(r.get("is_emergency", False)),
                notes=r.get("notes"),
                created_at=None,
                items=parsed_items
            ))
        return results
    except Exception:
        # Return empty list on failure
        return []

@router.post("/{bulk_id}/assign", response_model=BulkAssignResponse)
def auto_assign_bulk_workers(
    bulk_id: str,
    db: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_role(["cooperative_association_head", "admin", "super_admin"]))
):
    """
    Execute Fair Multi-Worker Dispatch to assign cooperative workers across all trades in the bulk request.
    """
    try:
        # 1. Fetch bulk booking
        b_res = db.table("bulk_bookings").select("*, bulk_booking_items(*)").eq("id", bulk_id).execute()
        if not b_res.data:
            raise HTTPException(status_code=404, detail="Bulk booking not found.")
        
        bulk = b_res.data[0]
        items = bulk.get("bulk_booking_items") or []
        req_lat = float(bulk.get("latitude") or 12.9716)
        req_lng = float(bulk.get("longitude") or 77.5946)

        # 2. Fetch available workers
        w_res = db.table("workers").select("*, users(name, email, phone), cooperatives(name)").eq("is_available", True).execute()
        available_workers = w_res.data or []

        assigned_workers = []
        already_assigned_ids = set()

        for item in items:
            trade_name = item.get("trade_name", "")
            qty_req = int(item.get("quantity_requested", 1))

            # Filter candidates for trade
            candidates = [
                w for w in available_workers 
                if str(w.get("id")) not in already_assigned_ids and (
                    trade_name.lower() in (w.get("skill") or "").lower() or 
                    (w.get("skill") or "").lower() in trade_name.lower()
                )
            ]

            ranked = rank_workers_for_booking(
                requested_skill=trade_name,
                request_lat=req_lat,
                request_lng=req_lng,
                available_workers=candidates,
                is_emergency=bool(bulk.get("is_emergency", False))
            )

            to_assign = ranked[:qty_req]
            for c in to_assign:
                already_assigned_ids.add(c["worker_id"])
                assigned_workers.append({
                    "worker_id": c["worker_id"],
                    "name": c["name"],
                    "phone": c["phone"],
                    "skill": trade_name,
                    "cooperative_name": c["cooperative_name"] or "ABC Skilled Workers Co-op",
                    "hourly_rate": c["hourly_rate"],
                    "fairness_score": c["score"]
                })

            # Update item assigned count
            try:
                db.table("bulk_booking_items").update({
                    "quantity_assigned": len(to_assign)
                }).eq("id", item.get("id")).execute()
            except Exception:
                pass

        total_assigned = len(assigned_workers)
        new_status = "fully_assigned" if total_assigned >= int(bulk.get("total_workers_requested", 1)) else "partially_assigned"

        try:
            db.table("bulk_bookings").update({
                "total_workers_assigned": total_assigned,
                "status": new_status
            }).eq("id", bulk_id).execute()
        except Exception:
            pass

        return BulkAssignResponse(
            success=True,
            bulk_booking_id=bulk_id,
            total_requested=int(bulk.get("total_workers_requested", 1)),
            total_assigned=total_assigned,
            status=new_status,
            assigned_workers=assigned_workers
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error assigning bulk workers: {str(e)}"
        )
