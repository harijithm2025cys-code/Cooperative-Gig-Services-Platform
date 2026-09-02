# main.py
# Cooperative Gig Services Platform - FastAPI Backend
# Updated with weighted matching algorithm

import os
import math
from typing import Optional, List, Dict
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from supabase import create_client, Client

# Load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials in .env")

# Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# FastAPI app
app = FastAPI(title="Cooperative Gig Services Platform API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For hackathon; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# Pydantic Models
# ----------------------------------------------------------------------
class UserRegister(BaseModel):
    name: str
    phone: str
    email: EmailStr
    role: str  # 'household' / 'worker' / 'admin'

class WorkerProfile(BaseModel):
    user_id: str
    skill: str
    cooperative_id: str
    latitude: float
    longitude: float
    experience_years: int = 1  # default 1 year

class BookingCreate(BaseModel):
    household_id: str
    service_id: str
    worker_id: Optional[str] = None  # if not provided, auto-match
    requested_at: Optional[datetime] = None

class BookingStatusUpdate(BaseModel):
    status: str  # 'requested'/'accepted'/'in_progress'/'completed'/'cancelled'

# ----------------------------------------------------------------------
# Helper: Haversine distance
# ----------------------------------------------------------------------
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in km between two coordinates."""
    R = 6371.0
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# ----------------------------------------------------------------------
# Helper: Weighted match score
# ----------------------------------------------------------------------
def calculate_match_score(worker: dict, request_lat: float, request_lng: float) -> Dict:
    """
    Calculate weighted match score.
    Returns dict with total and breakdown.
    """
    breakdown = {}
    
    # 1. Skill match (30 pts) - pre-filtered, so full
    breakdown['skill'] = 30.0
    
    # 2. Distance (20 pts) - linear: 0km->20, 15km->0
    worker_lat = float(worker.get('latitude', 0))
    worker_lng = float(worker.get('longitude', 0))
    distance_km = haversine_distance(request_lat, request_lng, worker_lat, worker_lng)
    distance_score = max(0.0, 20.0 * (1 - distance_km / 15.0))
    breakdown['distance'] = round(distance_score, 2)
    
    # 3. Verification (20 pts)
    breakdown['verification'] = 20.0 if worker.get('is_verified', False) else 0.0
    
    # 4. Rating (15 pts)
    rating = float(worker.get('rating', 0))
    breakdown['rating'] = round(min(15.0, (rating / 5.0) * 15.0), 2)
    
    # 5. Availability (10 pts)
    breakdown['availability'] = 10.0 if worker.get('is_available', False) else 0.0
    
    # 6. Experience (5 pts)
    exp = int(worker.get('experience_years', 1))
    breakdown['experience'] = round(min(exp / 10.0, 1.0) * 5.0, 2)
    
    total = sum(breakdown.values())
    breakdown['total'] = round(total, 2)
    return breakdown

# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@app.get("/")
def root():
    return {"message": "Cooperative Gig Services Platform API is running"}

# ----- User Registration -----
@app.post("/register")
def register_user(user: UserRegister):
    try:
        data = user.dict()
        # Optional: set created_at to now()
        data['created_at'] = datetime.utcnow().isoformat()
        result = supabase.table("users").insert(data).execute()
        if not result.data:
            raise HTTPException(status_code=400, detail="Registration failed")
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# ----- Worker Profile Creation -----
@app.post("/workers/profile")
def create_worker_profile(profile: WorkerProfile):
    try:
        # Check user exists and role is worker
        user_check = supabase.table("users").select("role").eq("id", profile.user_id).execute()
        if not user_check.data or user_check.data[0]["role"] != "worker":
            raise HTTPException(status_code=400, detail="User not found or not a worker")
        
        data = profile.dict()
        data['is_verified'] = False  # default not verified
        data['is_available'] = True
        data['rating'] = 0.0  # initial rating
        result = supabase.table("workers").insert(data).execute()
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# ----- Available Workers (updated) -----
@app.get("/workers/available")
def get_available_workers(
    skill: Optional[str] = None,
    lat: float = Query(..., description="User latitude"),
    lng: float = Query(..., description="User longitude")
):
    """
    Return available workers sorted by weighted match score.
    """
    try:
        query = supabase.table("workers").select(
            "*, users!inner(name, phone)"
        ).eq("is_available", True)
        
        if skill:
            query = query.eq("skill", skill)
        
        result = query.execute()
        workers = result.data
        
        if not workers:
            return {"workers": [], "message": "No workers found"}
        
        scored = []
        for w in workers:
            score = calculate_match_score(w, lat, lng)
            # Include distance for convenience
            w_lat = float(w['latitude'])
            w_lng = float(w['longitude'])
            dist = haversine_distance(lat, lng, w_lat, w_lng)
            scored.append({
                "worker": w,
                "match_score": score,
                "distance_km": round(dist, 2)
            })
        
        scored.sort(key=lambda x: x["match_score"]["total"], reverse=True)
        
        response = [{
            "id": s["worker"]["id"],
            "name": s["worker"]["users"]["name"] if s["worker"].get("users") else "Unknown",
            "phone": s["worker"]["users"]["phone"] if s["worker"].get("users") else "",
            "skill": s["worker"]["skill"],
            "rating": s["worker"]["rating"],
            "is_verified": s["worker"]["is_verified"],
            "is_available": s["worker"]["is_available"],
            "experience_years": s["worker"].get("experience_years", 1),
            "cooperative_id": s["worker"]["cooperative_id"],
            "latitude": s["worker"]["latitude"],
            "longitude": s["worker"]["longitude"],
            "distance_km": s["distance_km"],
            "match_score": s["match_score"]["total"],
            "score_breakdown": s["match_score"]
        } for s in scored]
        
        return {"workers": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching workers: {str(e)}")

# ----- Nearby Workers (new) -----
@app.get("/workers/nearby")
def get_nearby_workers(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    radius_km: float = Query(4.0, description="Radius in km"),
    skill: Optional[str] = None
):
    """
    Return available and verified workers within radius, sorted by weighted score.
    """
    try:
        query = supabase.table("workers").select(
            "*, users!inner(name, phone)"
        ).eq("is_available", True).eq("is_verified", True)
        
        if skill:
            query = query.eq("skill", skill)
        
        result = query.execute()
        workers = result.data
        
        if not workers:
            return {"workers": [], "message": "No workers found"}
        
        scored = []
        for w in workers:
            w_lat = float(w['latitude'])
            w_lng = float(w['longitude'])
            dist = haversine_distance(lat, lng, w_lat, w_lng)
            if dist <= radius_km:
                score = calculate_match_score(w, lat, lng)
                scored.append({
                    "worker": w,
                    "match_score": score,
                    "distance_km": round(dist, 2)
                })
        
        scored.sort(key=lambda x: x["match_score"]["total"], reverse=True)
        
        response = [{
            "id": s["worker"]["id"],
            "name": s["worker"]["users"]["name"] if s["worker"].get("users") else "Unknown",
            "phone": s["worker"]["users"]["phone"] if s["worker"].get("users") else "",
            "skill": s["worker"]["skill"],
            "rating": s["worker"]["rating"],
            "is_verified": s["worker"]["is_verified"],
            "is_available": s["worker"]["is_available"],
            "experience_years": s["worker"].get("experience_years", 1),
            "cooperative_id": s["worker"]["cooperative_id"],
            "latitude": s["worker"]["latitude"],
            "longitude": s["worker"]["longitude"],
            "distance_km": s["distance_km"],
            "match_score": s["match_score"]["total"],
            "score_breakdown": s["match_score"]
        } for s in scored]
        
        return {"workers": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching nearby workers: {str(e)}")

# ----- Create Booking (auto-match) -----
@app.post("/bookings")
def create_booking(booking: BookingCreate):
    try:
        household_id = booking.household_id
        service_id = booking.service_id
        
        # Get household location
        household = supabase.table("households").select("latitude, longitude").eq("id", household_id).execute()
        if not household.data:
            raise HTTPException(status_code=404, detail="Household not found")
        h_lat = float(household.data[0]["latitude"])
        h_lng = float(household.data[0]["longitude"])
        
        # Get service to know skill
        service = supabase.table("services").select("name").eq("id", service_id).execute()
        if not service.data:
            raise HTTPException(status_code=404, detail="Service not found")
        skill = service.data[0]["name"]
        
        # If worker_id not provided, auto-match
        worker_id = booking.worker_id
        if not worker_id:
            # Find best available worker for this skill
            workers_query = supabase.table("workers").select(
                "*, users!inner(name, phone)"
            ).eq("is_available", True).eq("skill", skill).execute()
            workers = workers_query.data
            if not workers:
                raise HTTPException(status_code=400, detail="No available workers for this skill")
            
            # Score all workers
            scored = []
            for w in workers:
                score = calculate_match_score(w, h_lat, h_lng)
                scored.append((w, score))
            # Sort by total score descending
            scored.sort(key=lambda x: x[1]["total"], reverse=True)
            best_worker = scored[0][0]
            worker_id = best_worker["id"]
        
        # Create booking
        booking_data = {
            "household_id": household_id,
            "worker_id": worker_id,
            "service_id": service_id,
            "status": "requested",
            "requested_at": booking.requested_at.isoformat() if booking.requested_at else datetime.utcnow().isoformat()
        }
        result = supabase.table("bookings").insert(booking_data).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Booking creation failed")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating booking: {str(e)}")

# ----- Update Booking Status -----
@app.put("/bookings/{booking_id}/status")
def update_booking_status(booking_id: str, status_update: BookingStatusUpdate):
    try:
        valid_statuses = ["requested", "accepted", "in_progress", "completed", "cancelled"]
        if status_update.status not in valid_statuses:
            raise HTTPException(status_code=400, detail="Invalid status")
        
        update_data = {"status": status_update.status}
        if status_update.status == "completed":
            update_data["completed_at"] = datetime.utcnow().isoformat()
        
        result = supabase.table("bookings").update(update_data).eq("id", booking_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Booking not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating booking: {str(e)}")

# ----- Get Booking Details -----
@app.get("/bookings/{booking_id}")
def get_booking(booking_id: str):
    try:
        result = supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Booking not found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching booking: {str(e)}")

# ----- List Household's Bookings -----
@app.get("/bookings/household/{household_id}")
def get_household_bookings(household_id: str):
    try:
        result = supabase.table("bookings").select("*").eq("household_id", household_id).order("requested_at", desc=True).execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching household bookings: {str(e)}")

# ----- List Worker's Bookings -----
@app.get("/bookings/worker/{worker_id}")
def get_worker_bookings(worker_id: str):
    try:
        result = supabase.table("bookings").select("*").eq("worker_id", worker_id).order("requested_at", desc=True).execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching worker bookings: {str(e)}")

# ----------------------------------------------------------------------
# Run: uvicorn main:app --reload
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)