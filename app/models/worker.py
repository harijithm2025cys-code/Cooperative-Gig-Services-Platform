from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class WorkerAvailabilityUpdate(BaseModel):
    availability: bool = Field(..., description="True if worker is open for new bookings, False otherwise")

class WorkerResponse(BaseModel):
    id: str
    user_id: str
    cooperative_id: Optional[str] = None
    skill: str
    service_area: Optional[str] = None
    rating: float = 0.0
    availability: bool = True
    verified_status: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    cooperative_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class WorkerDetailResponse(BaseModel):
    id: str
    user_id: str
    cooperative_id: Optional[str] = None
    skill: str
    service_area: Optional[str] = None
    rating: float = 0.0
    availability: bool = True
    verified_status: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    user: Optional[Dict[str, Any]] = None
    cooperative: Optional[Dict[str, Any]] = None
    recent_ratings: Optional[List[Dict[str, Any]]] = None

    model_config = ConfigDict(from_attributes=True)

class AvailableWorkersResponse(BaseModel):
    total: int
    workers: List[Dict[str, Any]]
