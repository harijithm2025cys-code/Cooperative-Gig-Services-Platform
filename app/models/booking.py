from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

BookingStatusType = Literal["pending", "accepted", "in_progress", "completed", "cancelled"]

class BookingCreate(BaseModel):
    household_id: Optional[str] = Field(None, description="Household ID. Inferred from current user if omitted.")
    service_id: str = Field(..., description="Service ID requested")
    worker_id: Optional[str] = Field(None, description="Optional preferred worker ID. If omitted, matching engine will assign.")
    scheduled_time: Optional[datetime] = Field(None, description="Scheduled time for service")

    model_config = ConfigDict(from_attributes=True)

class BookingStatusUpdate(BaseModel):
    status: BookingStatusType = Field(
        ...,
        description="Updated status: pending, accepted, in_progress, completed, or cancelled"
    )
    action: Optional[Literal["accept", "reject", "check_in", "check_out", "complete", "cancel"]] = None

    model_config = ConfigDict(from_attributes=True)

class BookingResponse(BaseModel):
    id: str
    household_id: str
    worker_id: Optional[str] = None
    service_id: str
    status: str
    scheduled_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    
    # Nested detail fields if joined
    household: Optional[Dict[str, Any]] = None
    worker: Optional[Dict[str, Any]] = None
    service: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)

class BookingListResponse(BaseModel):
    total: int
    bookings: List[BookingResponse]
