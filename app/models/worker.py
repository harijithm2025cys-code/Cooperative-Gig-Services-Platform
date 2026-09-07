from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class WorkerAvailabilityUpdate(BaseModel):
    availability: bool = Field(..., description="True if worker is open for new bookings, False otherwise")

class WorkerAvailabilityStatusUpdate(BaseModel):
    availability_status: Literal["available", "unavailable", "working", "leave"] = Field(
        ...,
        description="Worker current operational status"
    )

class WorkerResponse(BaseModel):
    id: str
    user_id: str
    cooperative_id: Optional[str] = None
    worker_type: Optional[str] = "cooperative"  # "cooperative" or "independent"
    member_reg_id: Optional[str] = None
    skill: str
    service_area: Optional[str] = None
    service_radius_km: Optional[float] = 25.0
    certifications: Optional[List[str]] = []
    rating: float = 0.0
    availability: bool = True
    availability_status: Optional[str] = "available"  # "available", "unavailable", "working", "leave"
    verified_status: bool = False
    is_pre_verified_by_association: bool = True
    hourly_rate: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_updated_at: Optional[datetime] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    cooperative_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class WorkerDetailResponse(BaseModel):
    id: str
    user_id: str
    cooperative_id: Optional[str] = None
    worker_type: Optional[str] = "cooperative"
    member_reg_id: Optional[str] = None
    skill: str
    service_area: Optional[str] = None
    service_radius_km: Optional[float] = 25.0
    certifications: Optional[List[str]] = []
    rating: float = 0.0
    availability: bool = True
    availability_status: Optional[str] = "available"
    verified_status: bool = False
    is_pre_verified_by_association: bool = True
    hourly_rate: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_updated_at: Optional[datetime] = None
    user: Optional[Dict[str, Any]] = None
    cooperative: Optional[Dict[str, Any]] = None
    recent_ratings: Optional[List[Dict[str, Any]]] = None

    model_config = ConfigDict(from_attributes=True)

class AvailableWorkersResponse(BaseModel):
    total: int
    workers: List[Dict[str, Any]]
