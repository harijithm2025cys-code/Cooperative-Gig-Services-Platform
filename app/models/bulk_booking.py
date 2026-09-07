from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class BulkBookingItemInput(BaseModel):
    trade_name: str = Field(..., description="E.g. Cleaners, Electricians, Plumbers")
    quantity_requested: int = Field(..., ge=1, le=50, description="Number of workers required for this trade")
    service_id: Optional[str] = None
    rate_per_worker: Optional[float] = Field(default=350.0, description="Tariff rate per worker")

class BulkBookingCreateRequest(BaseModel):
    institution_name: Optional[str] = Field(default=None, description="Name of company, school, apartment complex")
    contact_person: str = Field(..., description="Name of representative")
    contact_phone: str = Field(..., description="Phone number")
    service_address: str = Field(..., description="Delivery location")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    scheduled_date: str = Field(..., description="YYYY-MM-DD or readable date")
    scheduled_time: str = Field(..., description="e.g. 09:00 AM - 05:00 PM")
    trades: List[BulkBookingItemInput] = Field(..., min_length=1, description="List of trade requirements")
    is_emergency: bool = False
    notes: Optional[str] = None

class BulkBookingItemResponse(BaseModel):
    id: str
    trade_name: str
    quantity_requested: int
    quantity_assigned: int
    rate_per_worker: float

class BulkBookingResponse(BaseModel):
    id: str
    customer_id: str
    institution_name: Optional[str]
    contact_person: str
    contact_phone: str
    service_address: str
    scheduled_date: str
    scheduled_time: str
    total_workers_requested: int
    total_workers_assigned: int
    status: str
    total_estimated_amount: float
    payment_status: str
    is_emergency: bool
    notes: Optional[str]
    created_at: Optional[datetime]
    items: List[BulkBookingItemResponse] = []

class BulkAssignResponse(BaseModel):
    success: bool
    bulk_booking_id: str
    total_requested: int
    total_assigned: int
    status: str
    assigned_workers: List[Dict[str, Any]]
