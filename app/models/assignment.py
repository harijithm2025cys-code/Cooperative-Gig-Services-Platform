from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

AssignmentStatusType = Literal[
    "ASSIGNED",
    "ACCEPTED",
    "REJECTED",
    "EXPIRED",
    "CANCELLED",
    "COMPLETED"
]

class BookingAssignmentCreate(BaseModel):
    booking_id: str
    worker_id: str
    status: AssignmentStatusType = "ASSIGNED"
    distance_km: Optional[float] = None
    matching_score: Optional[float] = None
    assignment_sequence: int = 1

class BookingAssignmentResponse(BaseModel):
    id: str
    booking_id: str
    worker_id: str
    status: str
    assigned_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    distance_km: Optional[float] = None
    matching_score: Optional[float] = None
    assignment_sequence: int = 1
    worker_name: Optional[str] = None
    worker_phone: Optional[str] = None
    worker_skill: Optional[str] = None
    cooperative_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class MatchingAuditLogResponse(BaseModel):
    id: str
    booking_id: str
    worker_id: Optional[str] = None
    worker_name: Optional[str] = None
    is_eligible: bool
    rejection_reason: Optional[str] = None
    distance_km: Optional[float] = None
    matching_score: Optional[float] = None
    created_at: Optional[datetime] = None

class AutoAllocationRequest(BaseModel):
    booking_id: str
    max_radius_km: Optional[float] = 25.0
    require_exact_cooperative: Optional[bool] = False

class AutoAllocationResponse(BaseModel):
    success: bool
    booking_id: str
    allocation_status: str  # "ASSIGNED", "PARTIALLY_MATCHED", "NO_ELIGIBLE_WORKER"
    required_worker_count: int
    assigned_worker_count: int
    assigned_workers: List[BookingAssignmentResponse] = []
    explanation: str
    audit_logs: List[MatchingAuditLogResponse] = []
