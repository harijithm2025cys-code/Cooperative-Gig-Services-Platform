from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from supabase import Client

from app.db.supabase_client import get_supabase_client
from app.core.dependencies import get_current_user
from app.services.matching import haversine_distance
from app.models.worker import (
    WorkerAvailabilityUpdate,
    WorkerResponse,
    WorkerDetailResponse,
    AvailableWorkersResponse,
)

router = APIRouter(prefix="/workers", tags=["Workers"])

@router.get("/available", response_model=AvailableWorkersResponse)
def get_available_workers(
    skill: Optional[str] = Query(None, description="Filter by worker skill (e.g. Electrician, Plumber)"),
    lat: Optional[float] = Query(None, description="Household latitude for distance sorting"),
    lng: Optional[float] = Query(None, description="Household longitude for distance sorting"),
    radius: Optional[float] = Query(None, description="Max radius in km"),
    db: Client = Depends(get_supabase_client)
):
    """
    Get all available workers with optional filtering by skill, location, and radius.
    Supports both is_available / availability and is_verified / verified_status column schemas.
    """
    try:
        try:
            query = db.table("workers").select(
                "*, users(name, email, phone), cooperatives(name, district, state)"
            ).eq("is_available", True)
            if skill:
                query = query.ilike("skill", f"%{skill.strip()}%")
            res = query.execute()
        except Exception:
            # Fallback for availability column
            query = db.table("workers").select(
                "*, users(name, email, phone), cooperatives(name, district, state)"
            )
            if skill:
                query = query.ilike("skill", f"%{skill.strip()}%")
            res = query.execute()

        workers = res.data or []

        processed_workers = []
        for w in workers:
            w_lat = w.get("latitude")
            w_lng = w.get("longitude")
            
            dist_km = None
            if lat is not None and lng is not None and w_lat is not None and w_lng is not None:
                dist_km = haversine_distance(lat, lng, float(w_lat), float(w_lng))
                if radius is not None and dist_km > radius:
                    continue  # Filter out workers outside radius

            user_obj = w.get("users") or {}
            coop_obj = w.get("cooperatives") or {}

            is_verified = bool(w.get("is_verified") or w.get("verified_status") or False)
            is_available = bool(w.get("is_available") if w.get("is_available") is not None else w.get("availability", True))

            processed_workers.append({
                "id": str(w["id"]),
                "user_id": str(w.get("user_id")),
                "cooperative_id": str(w.get("cooperative_id")) if w.get("cooperative_id") else None,
                "skill": w.get("skill", "Specialist"),
                "service_area": w.get("service_area") or (coop_obj.get("district") if isinstance(coop_obj, dict) else "City Area"),
                "rating": float(w.get("rating") or 4.8),
                "availability": is_available,
                "verified_status": is_verified,
                "latitude": float(w_lat) if w_lat is not None else None,
                "longitude": float(w_lng) if w_lng is not None else None,
                "distance_km": dist_km,
                "name": user_obj.get("name") or user_obj.get("email", "Worker"),
                "phone": user_obj.get("phone"),
                "email": user_obj.get("email"),
                "cooperative_name": coop_obj.get("name") if isinstance(coop_obj, dict) else None
            })

        # Sort by distance if location provided, else by rating
        if lat is not None and lng is not None:
            processed_workers.sort(key=lambda x: (x["distance_km"] if x["distance_km"] is not None else 999.0))
        else:
            processed_workers.sort(key=lambda x: x["rating"], reverse=True)

        return AvailableWorkersResponse(
            total=len(processed_workers),
            workers=processed_workers
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving available workers: {str(e)}"
        )

@router.get("/{worker_id}", response_model=WorkerDetailResponse)
def get_worker_by_id(
    worker_id: str,
    db: Client = Depends(get_supabase_client)
):
    """
    Retrieve comprehensive details for a specific worker including cooperative and ratings.
    """
    try:
        w_res = db.table("workers").select(
            "*, users(id, name, email, phone, created_at), cooperatives(id, name, district, state)"
        ).eq("id", worker_id).execute()

        if not w_res.data or len(w_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Worker with ID '{worker_id}' not found."
            )

        worker = w_res.data[0]

        # Fetch recent ratings for this worker via completed bookings
        try:
            ratings_res = db.table("ratings").select(
                "*, bookings!inner(worker_id)"
            ).eq("bookings.worker_id", worker_id).order("created_at", desc=True).limit(5).execute()
            recent_ratings = ratings_res.data or []
        except Exception:
            recent_ratings = []

        is_verified = bool(worker.get("is_verified") or worker.get("verified_status") or False)
        is_available = bool(worker.get("is_available") if worker.get("is_available") is not None else worker.get("availability", True))

        return WorkerDetailResponse(
            id=str(worker["id"]),
            user_id=str(worker["user_id"]),
            cooperative_id=str(worker.get("cooperative_id")) if worker.get("cooperative_id") else None,
            skill=worker.get("skill"),
            service_area=worker.get("service_area") or "Cooperative Zone",
            rating=float(worker.get("rating") or 0.0),
            availability=is_available,
            verified_status=is_verified,
            latitude=float(worker["latitude"]) if worker.get("latitude") is not None else None,
            longitude=float(worker["longitude"]) if worker.get("longitude") is not None else None,
            user=worker.get("users"),
            cooperative=worker.get("cooperatives"),
            recent_ratings=recent_ratings
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching worker: {str(e)}"
        )

@router.patch("/{worker_id}/availability", response_model=WorkerResponse)
def update_worker_availability(
    worker_id: str,
    payload: WorkerAvailabilityUpdate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Update a worker's availability toggle.
    Requires user to be the worker or an admin.
    """
    try:
        # Check if worker exists
        existing = db.table("workers").select("*").eq("id", worker_id).execute()
        if not existing.data or len(existing.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Worker with ID '{worker_id}' not found."
            )

        worker = existing.data[0]
        # Authorization check
        if current_user.get("role") != "admin" and str(worker.get("user_id")) != str(current_user.get("id")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to update this worker's availability status."
            )

        try:
            updated = db.table("workers").update({"is_available": payload.availability}).eq("id", worker_id).execute()
        except Exception:
            updated = db.table("workers").update({"availability": payload.availability}).eq("id", worker_id).execute()

        if not updated.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update worker availability."
            )

        updated_worker = updated.data[0]
        is_verified = bool(updated_worker.get("is_verified") or updated_worker.get("verified_status") or False)
        is_available = bool(updated_worker.get("is_available") if updated_worker.get("is_available") is not None else updated_worker.get("availability", True))

        return WorkerResponse(
            id=str(updated_worker["id"]),
            user_id=str(updated_worker["user_id"]),
            cooperative_id=str(updated_worker.get("cooperative_id")) if updated_worker.get("cooperative_id") else None,
            skill=updated_worker.get("skill"),
            service_area=updated_worker.get("service_area"),
            rating=float(updated_worker.get("rating") or 0.0),
            availability=is_available,
            verified_status=is_verified,
            latitude=float(updated_worker["latitude"]) if updated_worker.get("latitude") is not None else None,
            longitude=float(updated_worker["longitude"]) if updated_worker.get("longitude") is not None else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating worker availability: {str(e)}"
        )
