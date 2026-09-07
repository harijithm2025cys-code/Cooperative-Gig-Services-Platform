from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

PaymentStatusType = Literal[
    "CREATED",
    "AUTHORIZED",
    "CAPTURED",
    "FAILED",
    "REFUNDED",
    "PARTIALLY_REFUNDED",
    "DISPUTED"
]

SettlementStatusType = Literal[
    "PENDING",
    "ELIGIBLE",
    "DISPUTED",
    "SETTLED"
]

class CreateOrderRequest(BaseModel):
    booking_id: str = Field(..., description="ID of booking to create Razorpay payment order for")

    model_config = ConfigDict(from_attributes=True)

class CreateOrderResponse(BaseModel):
    order_id: str = Field(..., description="Razorpay Order ID")
    key_id: str = Field(..., description="Razorpay Public Key ID")
    amount: float = Field(..., description="Amount payable in INR")
    currency: str = Field(default="INR", description="Currency code")
    booking_id: str = Field(..., description="Associated booking ID")
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    service_name: Optional[str] = None

class VerifyPaymentRequest(BaseModel):
    booking_id: str = Field(..., description="Associated booking ID")
    razorpay_order_id: str = Field(..., description="Razorpay Order ID")
    razorpay_payment_id: str = Field(..., description="Razorpay Payment ID from gateway")
    razorpay_signature: str = Field(..., description="HMAC-SHA256 signature from checkout")

class PaymentDetailResponse(BaseModel):
    id: str
    booking_id: str
    customer_id: str
    razorpay_order_id: str
    razorpay_payment_id: Optional[str] = None
    amount: float
    currency: str = "INR"
    status: str
    payment_method: Optional[str] = None
    signature_verified: bool = False
    settlement_status: str = "PENDING"
    paid_at: Optional[datetime] = None
    refunded_amount: float = 0.0
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class RefundRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Reason for refund")
    amount: Optional[float] = Field(None, description="Partial refund amount (full if omitted)")

class RefundResponse(BaseModel):
    success: bool
    payment_id: str
    refund_id: str
    amount_refunded: float
    status: str
    message: str
