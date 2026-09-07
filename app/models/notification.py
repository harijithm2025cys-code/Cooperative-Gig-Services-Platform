from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

NotificationType = Literal[
    "new_booking",
    "worker_assigned",
    "worker_accepted",
    "worker_rejected",
    "worker_on_the_way",
    "worker_arrived",
    "service_started",
    "service_completed",
    "booking_cancelled",
    "emergency_dispatch",
    "system"
]

class NotificationCreate(BaseModel):
    user_id: str = Field(..., description="Target user ID receiving notification")
    type: NotificationType = Field(..., description="Notification category")
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Detailed message content")
    booking_id: Optional[str] = Field(None, description="Associated booking ID if any")
    assignment_id: Optional[str] = Field(None, description="Associated assignment ID if any")
    data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata payload")

class NotificationResponse(BaseModel):
    id: str
    user_id: str
    type: str
    title: str
    message: str
    booking_id: Optional[str] = None
    assignment_id: Optional[str] = None
    read: bool = False
    created_at: Optional[datetime] = None
    data: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)

class NotificationListResponse(BaseModel):
    total: int
    unread_count: int
    notifications: List[NotificationResponse]

class NotificationMarkReadRequest(BaseModel):
    notification_ids: Optional[List[str]] = None
    mark_all: bool = False

class RealtimeEvent(BaseModel):
    event_type: str
    booking_id: str
    assignment_id: Optional[str] = None
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = Field(default_factory=dict)
