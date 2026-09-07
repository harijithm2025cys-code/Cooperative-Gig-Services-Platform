from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict

class BookingStatusCounts(BaseModel):
    total: int = 0
    pending: int = 0
    payment_pending: int = 0
    accepted: int = 0
    in_progress: int = 0
    customer_confirmation_pending: int = 0
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
    total_revenue: float = 0.0

    model_config = ConfigDict(from_attributes=True)

class CooperativeWorkersResponse(BaseModel):
    cooperative_id: str
    cooperative_name: str
    district: Optional[str] = None
    verified: bool = False
    total_workers: int = 0
    workers: List[Dict[str, Any]]

class WorkerManagementUpdate(BaseModel):
    phone: Optional[str] = None
    skill: Optional[str] = None
    is_available: Optional[bool] = None
    active: Optional[bool] = None
    verified_status: Optional[bool] = None  # Super Admin only

class ServiceCreatePayload(BaseModel):
    name: str
    category: str
    description: Optional[str] = None
    base_price: float = Field(..., gt=0)
    unit: Optional[str] = "job"
    cooperative_id: Optional[str] = None
    is_active: bool = True

class ServiceUpdatePayload(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    base_price: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = None
    is_active: Optional[bool] = None

class UserRoleUpdatePayload(BaseModel):
    role: str = Field(..., description="Target role: customer, independent_worker, cooperative_worker, cooperative_association_head, super_admin")
    cooperative_id: Optional[str] = None

class DisputeResolutionPayload(BaseModel):
    status: Literal["RESOLVED", "REJECTED", "UNDER_REVIEW"] = "RESOLVED"
    resolution_notes: str
    refund_approved: bool = False

class CooperativeCreatePayload(BaseModel):
    name: str
    district: str
    state: Optional[str] = "Tamil Nadu"
    address: Optional[str] = None
    registration_number: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    verified: bool = True

class CooperativeUpdatePayload(BaseModel):
    name: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None
    address: Optional[str] = None
    registration_number: Optional[str] = None
    verified: Optional[bool] = None
