# main.py
import os
import math
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables (SUPABASE_URL, SUPABASE_KEY)
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Cooperative Gig Services Platform API")

# CORS – allow all origins (for Flutter development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # In production, restrict to your Flutter app URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase client setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials in environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================================
# Pydantic Models (Request Bodies)
# ============================================================

class UserRegister(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    role: str = Field(..., pattern="^(household|worker|admin)$")  # only these roles

class WorkerProfile(BaseModel):
    user_id: str               # UUID of the user (must exist and role='worker')
    skill: str                 # e.g., "electrician", "plumber", "caregiver", "driver", "cleaner"
    latitude: float
    longitude: float
    cooperative_id: Optional[str] = None   # UUID of cooperative (optional)

class BookingCreate(BaseModel):
    household_id: str          # UUID of household
    service_id: str            # UUID of service (determines skill)
    latitude: Optional[float] = None   # optional override of household location
    longitude: Optional[float] = None

class BookingStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(accepted|in_progress|completed|cancelled)$")

# ============================================================
# Helper Functions
# ============================================================

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth (in kilometers).
    """
    R = 6371.0  # Earth radius in km
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def calculate_match_score(worker: dict, request_lat: float, request_lng: float) -> float:
    """
    Compute match score for a worker based on:
      - Skill match: 50 pts (already filtered in query)
      - Distance: up to 30 pts (closer = more points, only if within 10 km)
      - Rating: rating * 4 pts (max 20 pts)
    Returns total score (max 100).
    """
    # Skill match is assumed 50 (pre-filtered)
    skill_score = 50.0

    # Distance score (only if worker has coordinates)
    distance_score = 0.0
    distance_km = None
    if worker.get("latitude") is not None and worker.get("longitude") is not None:
        distance_km = haversine(request_lat, request_lng, worker["latitude"], worker["longitude"])
        if distance_km <= 10:
            # Scale: 0 km -> 30 pts, 10 km -> 0 pts
            distance_score = 30 * (1 - distance_km / 10.0)
        else:
            distance_score = 0.0
    else:
        # No coordinates – give average distance score
        distance_score = 15.0

    # Rating score
    rating = worker.get("rating", 0.0)
    rating_score = rating * 4.0  # max 5 * 4 = 20

    total = skill_score + distance_score + rating_score
    return total, distance_km, distance_score, rating_score

# ============================================================
# API Endpoints
# ============================================================

@app.post("/register", response_model=dict)
async def register_user(user: UserRegister):
    """
    Create a new user (role: household, worker, or admin).
    Returns the created user record.
    """
    # Insert into users table
    data = {
        "name": user.name,
        "phone": user.phone,
        "email": user.email,
        "role": user.role,
    }
    result = supabase.table("users").insert(data).execute()

    # Check if insert was successful
    if not result.data:
        raise HTTPException(status_code=400, detail="Could not create user")
    return {"user": result.data[0]}

@app.post("/workers/profile", response_model=dict)
async def create_worker_profile(profile: WorkerProfile):
    """
    Create a worker profile for an existing user.
    user_id must exist in users table and have role='worker'.
    """
    # Check that the user exists and has role 'worker'
    user = supabase.table("users").select("*").eq("id", profile.user_id).execute()
    if not user.data:
        raise HTTPException(status_code=404, detail="User not found")
    if user.data[0]["role"] != "worker":
        raise HTTPException(status_code=400, detail="User role is not 'worker'")

    # Check if worker profile already exists for this user
    existing = supabase.table("workers").select("*").eq("user_id", profile.user_id).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Worker profile already exists")

    # Insert worker profile
    data = {
        "user_id": profile.user_id,
        "skill": profile.skill,
        "latitude": profile.latitude,
        "longitude": profile.longitude,
        "cooperative_id": profile.cooperative_id,
        "is_verified": False,      # default false
        "is_available": True,      # default true
        "rating": 0.0,             # start with 0 rating
    }
    result = supabase.table("workers").insert(data).execute()
    if not result.data:
        raise HTTPException(status_code=400, detail="Failed to create worker profile")
    return {"worker": result.data[0]}

@app.get("/workers/available", response_model=dict)
async def get_available_workers(
    skill: str = Query(..., description="Skill category, e.g., electrician"),
    lat: float = Query(..., description="Request latitude"),
    lng: float = Query(..., description="Request longitude"),
):
    """
    Get all available workers with the given skill, sorted by match score (descending).
    Returns a list of workers with their score, distance, etc.
    """
    # Query workers: skill match and is_available = true
    result = supabase.table("workers").select("*").eq("skill", skill).eq("is_available", True).execute()
    workers = result.data

    if not workers:
        return {"workers": [], "message": "No available workers found"}

    # Calculate match score for each worker
    scored_workers = []
    for worker in workers:
        total_score, distance_km, distance_score, rating_score = calculate_match_score(worker, lat, lng)
        worker["match_score"] = round(total_score, 2)
        worker["distance_km"] = round(distance_km, 2) if distance_km is not None else None
        worker["distance_score"] = round(distance_score, 2)
        worker["rating_score"] = round(rating_score, 2)
        scored_workers.append(worker)

    # Sort by match_score descending
    scored_workers.sort(key=lambda x: x["match_score"], reverse=True)

    return {"workers": scored_workers}

@app.post("/bookings", response_model=dict)
async def create_booking(booking: BookingCreate):
    """
    Create a service request (booking).
    - household_id must exist
    - service_id determines the required skill
    - Optionally override household location with lat/lng
    - Automatically picks the best available worker for that skill
    """
    # 1. Verify household exists
    household = supabase.table("households").select("*").eq("id", booking.household_id).execute()
    if not household.data:
        raise HTTPException(status_code=404, detail="Household not found")
    household_data = household.data[0]

    # 2. Get service details to determine skill
    service = supabase.table("services").select("*").eq("id", booking.service_id).execute()
    if not service.data:
        raise HTTPException(status_code=404, detail="Service not found")
    service_data = service.data[0]
    required_skill = service_data["name"].lower()  # e.g., "electrician", "plumber"

    # 3. Determine request location
    req_lat = booking.latitude if booking.latitude is not None else household_data["latitude"]
    req_lng = booking.longitude if booking.longitude is not None else household_data["longitude"]

    if req_lat is None or req_lng is None:
        raise HTTPException(status_code=400, detail="Household has no location and none provided")

    # 4. Find best available worker
    workers_result = supabase.table("workers").select("*").eq("skill", required_skill).eq("is_available", True).execute()
    workers = workers_result.data

    if not workers:
        raise HTTPException(status_code=404, detail="No available workers for this skill")

    best_worker = None
    best_score = -1
    for worker in workers:
        score, _, _, _ = calculate_match_score(worker, req_lat, req_lng)
        if score > best_score:
            best_score = score
            best_worker = worker

    if not best_worker:
        raise HTTPException(status_code=500, detail="Could not select a worker")

    # 5. Create booking with status 'requested'
    booking_data = {
        "household_id": booking.household_id,
        "worker_id": best_worker["id"],
        "service_id": booking.service_id,
        "status": "requested",
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    insert_result = supabase.table("bookings").insert(booking_data).execute()
    if not insert_result.data:
        raise HTTPException(status_code=400, detail="Failed to create booking")

    # 6. Return booking details (with worker and household info)
    created_booking = insert_result.data[0]
    # Fetch worker info
    worker_info = supabase.table("workers").select("*").eq("id", created_booking["worker_id"]).execute()
    household_info = supabase.table("households").select("*").eq("id", created_booking["household_id"]).execute()
    service_info = supabase.table("services").select("*").eq("id", created_booking["service_id"]).execute()

    return {
        "booking": created_booking,
        "worker": worker_info.data[0] if worker_info.data else None,
        "household": household_info.data[0] if household_info.data else None,
        "service": service_info.data[0] if service_info.data else None,
        "match_score": round(best_score, 2),
    }

@app.put("/bookings/{booking_id}/status", response_model=dict)
async def update_booking_status(booking_id: str, update: BookingStatusUpdate):
    """
    Update the status of a booking.
    Allowed statuses: accepted, in_progress, completed, cancelled.
    """
    # Check if booking exists
    existing = supabase.table("bookings").select("*").eq("id", booking_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Update status
    update_data = {"status": update.status}
    if update.status == "completed":
        update_data["completed_at"] = datetime.now(timezone.utc).isoformat()

    result = supabase.table("bookings").update(update_data).eq("id", booking_id).execute()
    if not result.data:
        raise HTTPException(status_code=400, detail="Failed to update booking status")
    return {"booking": result.data[0]}

@app.get("/bookings/{booking_id}", response_model=dict)
async def get_booking(booking_id: str):
    """
    Get full details of a single booking, including household, worker, and service info.
    """
    booking = supabase.table("bookings").select("*").eq("id", booking_id).execute()
    if not booking.data:
        raise HTTPException(status_code=404, detail="Booking not found")
    booking_data = booking.data[0]

    # Fetch related entities
    household = supabase.table("households").select("*").eq("id", booking_data["household_id"]).execute()
    worker = supabase.table("workers").select("*").eq("id", booking_data["worker_id"]).execute()
    service = supabase.table("services").select("*").eq("id", booking_data["service_id"]).execute()

    return {
        "booking": booking_data,
        "household": household.data[0] if household.data else None,
        "worker": worker.data[0] if worker.data else None,
        "service": service.data[0] if service.data else None,
    }

@app.get("/bookings/household/{household_id}", response_model=dict)
async def list_household_bookings(household_id: str):
    """
    List all bookings for a given household.
    """
    bookings = supabase.table("bookings").select("*").eq("household_id", household_id).execute()
    if not bookings.data:
        return {"bookings": []}
    return {"bookings": bookings.data}

@app.get("/bookings/worker/{worker_id}", response_model=dict)
async def list_worker_bookings(worker_id: str):
    """
    List all bookings for a given worker.
    """
    bookings = supabase.table("bookings").select("*").eq("worker_id", worker_id).execute()
    if not bookings.data:
        return {"bookings": []}
    return {"bookings": bookings.data}

# ============================================================
# Run the app (for local development)
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)