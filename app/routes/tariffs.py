import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.db.supabase_client import get_supabase_client
from app.core.dependencies import get_current_user, require_role
from app.models.tariffs import (
    CooperativeTariffCreate,
    CooperativeTariffResponse,
    TariffListResponse,
)

router = APIRouter(prefix="/tariffs", tags=["Cooperative Tariff Matrix"])

# Pre-defined default standard tariffs if database table is newly initialized
DEFAULT_TARIFFS = [
    {"service_name": "AC Service & Repair", "hourly_rate": 450.0, "base_fee": 150.0, "emergency_surcharge_rate": 1.25},
    {"service_name": "Plumbing & Pipe Repair", "hourly_rate": 350.0, "base_fee": 120.0, "emergency_surcharge_rate": 1.30},
    {"service_name": "Electrical & Wiring", "hourly_rate": 380.0, "base_fee": 120.0, "emergency_surcharge_rate": 1.35},
    {"service_name": "Carpentry & Furniture", "hourly_rate": 400.0, "base_fee": 150.0, "emergency_surcharge_rate": 1.20},
    {"service_name": "Deep House Cleaning", "hourly_rate": 300.0, "base_fee": 100.0, "emergency_surcharge_rate": 1.25},
    {"service_name": "Gardening & Landscape", "hourly_rate": 280.0, "base_fee": 100.0, "emergency_surcharge_rate": 1.15},
    {"service_name": "Appliance & Washing Machine", "hourly_rate": 420.0, "base_fee": 150.0, "emergency_surcharge_rate": 1.25},
    {"service_name": "Caregiving & Nursing Assistance", "hourly_rate": 320.0, "base_fee": 100.0, "emergency_surcharge_rate": 1.20},
]

@router.get("", response_model=TariffListResponse)
def get_cooperative_tariffs(
    cooperative_id: Optional[str] = Query(None, description="Cooperative Society ID"),
    db: Client = Depends(get_supabase_client),
):
    """
    Retrieve the standard tariff rate card for a cooperative society or the general state standard.
    """
    try:
        query = db.table("cooperative_tariffs").select("*").eq("is_active", True)
        if cooperative_id:
            query = query.eq("cooperative_id", cooperative_id)
        
        res = query.execute()
        data = res.data or []

        # If no custom tariff rows yet in db, provide standardized default cooperative matrix
        if not data:
            data = [
                {
                    "id": f"trf_{i+1}",
                    "cooperative_id": cooperative_id or "coop_default",
                    "service_id": None,
                    "service_name": item["service_name"],
                    "hourly_rate": item["hourly_rate"],
                    "base_fee": item["base_fee"],
                    "emergency_surcharge_rate": item["emergency_surcharge_rate"],
                    "is_active": True,
                    "created_at": None
                }
                for i, item in enumerate(DEFAULT_TARIFFS)
            ]

        # Fetch coop name if requested
        coop_name = None
        if cooperative_id:
            c_res = db.table("cooperatives").select("name").eq("id", cooperative_id).execute()
            if c_res.data:
                coop_name = c_res.data[0].get("name")

        return TariffListResponse(
            success=True,
            total=len(data),
            cooperative_id=cooperative_id,
            cooperative_name=coop_name or "Labour Cooperative Federation Standard",
            tariffs=[CooperativeTariffResponse(**item) for item in data]
        )
    except Exception as e:
        # Graceful fallback to default tariffs on network/mock error
        fallback_data = [
            CooperativeTariffResponse(
                id=f"trf_{i+1}",
                cooperative_id=cooperative_id or "coop_default",
                service_id=None,
                service_name=item["service_name"],
                hourly_rate=item["hourly_rate"],
                base_fee=item["base_fee"],
                emergency_surcharge_rate=item["emergency_surcharge_rate"],
                is_active=True
            )
            for i, item in enumerate(DEFAULT_TARIFFS)
        ]
        return TariffListResponse(
            success=True,
            total=len(fallback_data),
            cooperative_id=cooperative_id,
            cooperative_name="State Standardized Cooperative Matrix",
            tariffs=fallback_data
        )

@router.post("", response_model=CooperativeTariffResponse)
def upsert_cooperative_tariff(
    payload: CooperativeTariffCreate,
    db: Client = Depends(get_supabase_client),
    current_user: dict = Depends(require_role(["cooperative_association_head", "admin", "super_admin"]))
):
    """
    Create or update a standardized tariff for a service under a Cooperative Society.
    Association Heads can only set tariffs for their own society.
    """
    user_role = (current_user.get("role") or "").lower()
    user_coop_id = current_user.get("cooperative_id")

    if user_role != "super_admin" and user_coop_id and str(user_coop_id) != str(payload.cooperative_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are only authorized to set tariffs for your own Cooperative Association."
        )

    try:
        tariff_id = str(uuid.uuid4())
        record = {
            "id": tariff_id,
            "cooperative_id": payload.cooperative_id,
            "service_id": payload.service_id,
            "service_name": payload.service_name,
            "hourly_rate": payload.hourly_rate,
            "base_fee": payload.base_fee,
            "emergency_surcharge_rate": payload.emergency_surcharge_rate,
            "is_active": payload.is_active
        }

        # Check existing
        existing = db.table("cooperative_tariffs").select("id").eq("cooperative_id", payload.cooperative_id).eq("service_name", payload.service_name).execute()
        if existing.data:
            tid = existing.data[0]["id"]
            upd = db.table("cooperative_tariffs").update(record).eq("id", tid).execute()
            if upd.data:
                return CooperativeTariffResponse(**upd.data[0])
            record["id"] = tid
        else:
            ins = db.table("cooperative_tariffs").insert(record).execute()
            if ins.data:
                return CooperativeTariffResponse(**ins.data[0])

        return CooperativeTariffResponse(**record)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upsert tariff: {str(e)}"
        )
