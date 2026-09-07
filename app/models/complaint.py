from typing import Optional, List, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

ComplaintCategoryType = Literal[
    "Service incomplete",
    "Poor quality",
    "Wrong service",
    "Damage",
    "Worker issue",
    "Other"
]

ComplaintStatusType = Literal[
    "OPEN",
    "UNDER_REVIEW",
    "RESOLVED",
    "REJECTED",
    "REFUNDED"
]

class ComplaintCreate(BaseModel):
    booking_id: str = Field(..., description="ID of booking with issue")
    category: ComplaintCategoryType = Field(..., description="Issue category")
    description: str = Field(..., min_length=5, description="Detailed problem description")
    assignment_id: Optional[str] = Field(None, description="Specific worker assignment if applicable")

    model_config = ConfigDict(from_attributes=True)

class ComplaintResponse(BaseModel):
    id: str
    booking_id: str
    customer_id: str
    cooperative_id: Optional[str] = None
    assignment_id: Optional[str] = None
    category: str
    description: str
    status: str
    resolution_notes: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ComplaintResolveRequest(BaseModel):
    status: Literal["UNDER_REVIEW", "RESOLVED", "REJECTED", "REFUNDED"] = Field(..., description="Resolution status")
    resolution_notes: str = Field(..., min_length=3, description="Notes documenting resolution")
    refund_amount: Optional[float] = Field(None, description="Optional refund amount if approved")

class ComplaintListResponse(BaseModel):
    total: int
    complaints: List[ComplaintResponse]
