from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

BookingStatusType = Literal[
    "requested",
    "accepted",
    "worker_enroute",
    "arrived",
    "verified_checkin",
    "payment_pending",
    "payment_released",
    "in_progress",
    "verified_checkout",
    "completed",
    "cancelled",
    "rejected"
]

VerificationMethodType = Literal["gps_proximity", "otp_match", "qr_scan", "manual"]
PaymentStatusType = Literal["pending", "held_in_escrow", "released", "refunded", "failed"]

class BookingCreate(BaseModel):
    household_id: Optional[str] = Field(None, description="Household ID. Inferred from current user if omitted.")
    service_id: str = Field(..., description="Service ID requested")
    worker_id: Optional[str] = Field(None, description="Optional preferred worker ID. If omitted, matching engine will assign.")
    required_worker_count: int = Field(default=1, ge=1, le=20, description="Number of workers required for this service")
    scheduled_time: Optional[datetime] = Field(None, description="Scheduled time for service")
    latitude: Optional[float] = Field(None, description="Service location latitude")
    longitude: Optional[float] = Field(None, description="Service location longitude")
    address: Optional[str] = Field(None, description="Service address text")
    notes: Optional[str] = Field(None, description="Additional service notes")
    estimated_amount: Optional[float] = Field(None, description="Estimated service cost")

    model_config = ConfigDict(from_attributes=True)

class BookingStatusUpdate(BaseModel):
    status: BookingStatusType = Field(
        ...,
        description="Updated booking status"
    )
    action: Optional[Literal[
        "request", "accept", "reject", "start_travel", "arrive",
        "verify_checkin", "init_payment", "release_payment",
        "check_in", "start_service", "complete_service",
        "verify_checkout", "check_out", "complete", "cancel"
    ]] = None

    model_config = ConfigDict(from_attributes=True)

class CheckInVerificationRequest(BaseModel):
    booking_id: str = Field(..., description="Booking ID to verify")
    verifier_role: Literal["household", "worker"] = Field(..., description="Who is verifying")
    method: VerificationMethodType = Field(..., description="Verification method used")
    worker_latitude: Optional[float] = Field(None, description="Worker's current latitude for GPS proximity check")
    worker_longitude: Optional[float] = Field(None, description="Worker's current longitude for GPS proximity check")
    household_latitude: Optional[float] = Field(None, description="Household's reported latitude")
    household_longitude: Optional[float] = Field(None, description="Household's reported longitude")
    otp_code: Optional[str] = Field(None, description="6-digit OTP for OTP match verification")
    max_distance_meters: Optional[float] = Field(100.0, description="Max allowed GPS distance in meters")

class CheckOutVerificationRequest(BaseModel):
    booking_id: str = Field(..., description="Booking ID to verify checkout")
    verifier_role: Literal["household", "worker"] = Field(..., description="Who is verifying")
    method: VerificationMethodType = Field(..., description="Verification method")
    otp_code: Optional[str] = Field(None, description="OTP code for mutual verification")

class PaymentProcessRequest(BaseModel):
    booking_id: str = Field(..., description="Booking ID")
    amount: float = Field(..., gt=0, description="Amount to process")
    payment_method: Literal["upi", "card", "wallet", "escrow"] = Field(..., description="Payment method")
    release_after_verification: bool = Field(True, description="Release only after both verify")

class WorkerLocationUpdate(BaseModel):
    worker_id: str = Field(..., description="Worker ID")
    latitude: float = Field(..., description="Current GPS latitude")
    longitude: float = Field(..., description="Current GPS longitude")
    heading: Optional[float] = Field(None, description="Direction of travel in degrees (0-360)")
    speed_kmh: Optional[float] = Field(None, description="Current speed in km/h")
    booking_id: Optional[str] = Field(None, description="Associated active booking ID if any")

class BookingResponse(BaseModel):
    id: str
    household_id: str
    worker_id: Optional[str] = None
    service_id: str
    status: str
    required_worker_count: int = 1
    assigned_worker_count: int = 0
    allocation_status: str = "PENDING"
    scheduled_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    estimated_amount: Optional[float] = None
    final_amount: Optional[float] = None
    payment_status: Optional[str] = None
    household_verified_checkin: Optional[bool] = False
    worker_verified_checkin: Optional[bool] = False
    household_verified_checkout: Optional[bool] = False
    worker_verified_checkout: Optional[bool] = False
    verification_otp: Optional[str] = None
    worker_live_lat: Optional[float] = None
    worker_live_lng: Optional[float] = None
    worker_last_seen: Optional[datetime] = None
    
    assignments: Optional[List[Dict[str, Any]]] = None
    household: Optional[Dict[str, Any]] = None
    worker: Optional[Dict[str, Any]] = None
    service: Optional[Dict[str, Any]] = None
    payment: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)

class BookingListResponse(BaseModel):
    total: int
    bookings: List[BookingResponse]

class VerificationResponse(BaseModel):
    success: bool
    booking_id: str
    verified_role: str
    method: str
    both_verified: bool
    distance_meters: Optional[float] = None
    message: str

class PaymentResponse(BaseModel):
    success: bool
    booking_id: str
    transaction_id: Optional[str] = None
    amount: float
    status: str
    message: str

class WorkerLocationResponse(BaseModel):
    success: bool
    worker_id: str
    latitude: float
    longitude: float
    timestamp: datetime
    message: str
    distance_to_customer_km: Optional[float] = None
    eta_minutes: Optional[int] = None
    eta_formatted: Optional[str] = None
    booking_id: Optional[str] = None
    assignment_id: Optional[str] = None
