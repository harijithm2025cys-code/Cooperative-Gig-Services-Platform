from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.db.supabase_client import get_supabase_client
from app.core.dependencies import get_current_user, require_role
from app.models.admin import (
    AdminStatsResponse,
    BookingStatusCounts,
    CooperativeWorkersResponse,
)

router = APIRouter(prefix="/admin", tags=["Cooperative Admin & Analytics"])

@router.get("/cooperative/{coop_id}/workers", response_model=CooperativeWorkersResponse)
def get_cooperative_workers(
    coop_id: str,
    db: Client = Depends(get_supabase_client)
):
    """
    Retrieve all workers affiliated with a specific Labour Cooperative Society.
    """
    try:
        # Check cooperative society
        coop_res = db.table("cooperatives").select("*").eq("id", coop_id).execute()
        if not coop_res.data or len(coop_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cooperative Society with ID '{coop_id}' not found."
            )

        coop = coop_res.data[0]

        # Fetch workers under this cooperative
        workers_res = db.table("workers").select(
            "*, users(id, name, email, phone, created_at)"
        ).eq("cooperative_id", coop_id).execute()

        workers = workers_res.data or []

        return CooperativeWorkersResponse(
            cooperative_id=str(coop["id"]),
            cooperative_name=coop.get("name", "Labour Cooperative Society"),
            district=coop.get("district"),
            verified=bool(coop.get("verified", False)),
            total_workers=len(workers),
            workers=workers
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving cooperative workers: {str(e)}"
        )

@router.get("/stats", response_model=AdminStatsResponse)
def get_admin_statistics(
    db: Client = Depends(get_supabase_client)
):
    """
    Retrieve platform-wide operational statistics, booking distribution, and worker counts.
    """
    try:
        # 1. Fetch bookings distribution
        bookings_res = db.table("bookings").select("status").execute()
        bookings_data = bookings_res.data or []

        counts = {
            "total": len(bookings_data),
            "pending": 0,
            "accepted": 0,
            "in_progress": 0,
            "completed": 0,
            "cancelled": 0
        }
        for b in bookings_data:
            st = (b.get("status") or "").lower()
            if st in counts:
                counts[st] += 1

        # 2. Worker counts
        workers_res = db.table("workers").select("id, availability, verified_status").execute()
        workers_data = workers_res.data or []
        total_workers = len(workers_data)
        active_available = sum(1 for w in workers_data if w.get("availability"))
        verified = sum(1 for w in workers_data if w.get("verified_status"))

        # 3. Households count
        households_res = db.table("households").select("id", count="exact").execute()
        total_hh = len(households_res.data or [])

        # 4. Cooperatives count
        coops_res = db.table("cooperatives").select("id", count="exact").execute()
        total_coops = len(coops_res.data or [])

        # 5. Services count
        services_res = db.table("services").select("id", count="exact").execute()
        total_services = len(services_res.data or [])

        return AdminStatsResponse(
            bookings=BookingStatusCounts(
                total=counts["total"],
                pending=counts["pending"],
                accepted=counts["accepted"],
                in_progress=counts["in_progress"],
                completed=counts["completed"],
                cancelled=counts["cancelled"]
            ),
            total_workers=total_workers,
            active_available_workers=active_available,
            verified_workers=verified,
            total_households=total_hh,
            total_cooperatives=total_coops,
            total_services=total_services,
            disputes_count=0
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error compiling admin statistics: {str(e)}"
        )
