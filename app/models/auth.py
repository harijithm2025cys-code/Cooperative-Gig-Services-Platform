from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict

class UserRegister(BaseModel):
    email: EmailStr
    phone: str = Field(..., min_length=7, max_length=15, description="Phone number with country code or 10 digits")
    password: str = Field(..., min_length=6, description="User password")
    role: Literal["household", "worker", "admin"] = Field(..., description="Role must be household, worker, or admin")
    name: Optional[str] = Field(None, description="Full name of user")
    
    # Household-specific fields
    address: Optional[str] = Field(None, description="Required if role is household")
    latitude: Optional[float] = Field(None, description="Latitude for location")
    longitude: Optional[float] = Field(None, description="Longitude for location")
    
    # Worker-specific fields
    skill: Optional[str] = Field(None, description="Worker primary skill (e.g. Electrician, Plumber)")
    cooperative_id: Optional[str] = Field(None, description="Associated Labour Cooperative Society ID")
    service_area: Optional[str] = Field(None, description="Service area or district coverage")

    model_config = ConfigDict(from_attributes=True)

class UserLogin(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: str

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    email: Optional[str] = None
    profile_id: Optional[str] = None  # household_id or worker_id if applicable

class UserResponse(BaseModel):
    id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str
    name: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class UserMeResponse(BaseModel):
    user: UserResponse
    profile: Optional[dict] = None
    cooperative: Optional[dict] = None
