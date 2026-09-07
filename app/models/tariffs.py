from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

class CooperativeTariffCreate(BaseModel):
    cooperative_id: str
    service_id: Optional[str] = None
    service_name: str
    hourly_rate: float = Field(..., ge=50.0, description="Standardized hourly rate in INR")
    base_fee: float = Field(default=150.0, ge=0.0, description="Minimum base visiting fee")
    emergency_surcharge_rate: float = Field(default=1.25, ge=1.0, le=3.0, description="Emergency multiplier (e.g. 1.25 = 25% extra)")
    is_active: bool = True

class CooperativeTariffResponse(BaseModel):
    id: str
    cooperative_id: str
    service_id: Optional[str] = None
    service_name: str
    hourly_rate: float
    base_fee: float
    emergency_surcharge_rate: float
    is_active: bool
    created_at: Optional[datetime] = None

class TariffListResponse(BaseModel):
    success: bool = True
    total: int
    cooperative_id: Optional[str] = None
    cooperative_name: Optional[str] = None
    tariffs: List[CooperativeTariffResponse]
