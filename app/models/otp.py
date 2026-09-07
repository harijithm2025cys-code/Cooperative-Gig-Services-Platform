from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class CompletionOtpCustomerResponse(BaseModel):
    booking_id: str
    otp_code: str
    expires_at: datetime
    instructions: str = "Please inspect the completed work. Share this 6-digit confirmation code with the worker only if you are satisfied."

    model_config = ConfigDict(from_attributes=True)

class VerifyCompletionOtpRequest(BaseModel):
    booking_id: str = Field(..., description="Booking ID being confirmed")
    otp_code: str = Field(..., description="6-digit OTP code provided by the customer after inspecting work")
    assignment_id: Optional[str] = Field(None, description="Optional assignment ID for the worker")

    model_config = ConfigDict(from_attributes=True)

class VerifyCompletionOtpResponse(BaseModel):
    success: bool
    booking_id: str
    status: str
    settlement_status: str
    message: str
