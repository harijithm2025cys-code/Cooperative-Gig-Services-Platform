from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class BookingStatusCounts(BaseModel):
    total: int = 0
    pending: int = 0
    accepted: int = 0
    in_progress: int = 0
    completed: int = 0
    cancelled: int = 0

class AdminStatsResponse(BaseModel):
    bookings: BookingStatusCounts
    total_workers: int = 0
    active_available_workers: int = 0
    verified_workers: int = 0
    total_households: int = 0
    total_cooperatives: int = 0
    total_services: int = 0
    disputes_count: int = 0

    model_config = ConfigDict(from_attributes=True)

class CooperativeWorkersResponse(BaseModel):
    cooperative_id: str
    cooperative_name: str
    district: Optional[str] = None
    verified: bool = False
    total_workers: int = 0
    workers: List[Dict[str, Any]]
