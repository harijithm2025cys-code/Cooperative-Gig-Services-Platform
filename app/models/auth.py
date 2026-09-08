from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict

# Standard 5-Role Taxonomy with legacy backward-compatibility aliases
UserRoleType = Literal[
    "customer",
    "independent_worker",
    "cooperative_association_head",
    "cooperative_worker",
    "super_admin",
    # Legacy aliases
    "household",
    "worker",
    "admin"
]

class UserRegister(BaseModel):
    email: str = Field(..., description="Email address of user")
    phone: str = Field(..., min_length=7, max_length=15, description="Phone number with country code or 10 digits")
    password: str = Field(..., min_length=6, description="User password")
    role: UserRoleType = Field(..., description="Role: customer, independent_worker, cooperative_association_head, cooperative_worker, or super_admin")
    name: Optional[str] = Field(None, description="Full name of user")
    
    # Customer / Household fields
    address: Optional[str] = Field(None, description="Required if role is customer/household")
    latitude: Optional[float] = Field(None, description="Latitude for location")
    longitude: Optional[float] = Field(None, description="Longitude for location")
    
    # Worker fields (Cooperative or Independent)
    worker_type: Optional[Literal["cooperative", "independent"]] = Field(None, description="Cooperative member or independent contractor")
    skill: Optional[str] = Field(None, description="Worker primary skill (e.g. Electrician, Plumber)")
    cooperative_id: Optional[str] = Field(None, description="Associated Labour Cooperative Society ID")
    member_reg_id: Optional[str] = Field(None, description="Official Cooperative Member Registration ID")
    service_area: Optional[str] = Field(None, description="Service area or district coverage")
    hourly_rate: Optional[float] = Field(None, description="Self-set hourly rate for independent workers")

    # Association Head / Super Admin fields
    society_name: Optional[str] = Field(None, description="Name of Cooperative Society")
    district: Optional[str] = Field(None, description="District location of Cooperative Society")
    federation_name: Optional[str] = Field(None, description="State/National Federation Name")

    model_config = ConfigDict(from_attributes=True)

class UserLogin(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    username: Optional[str] = None
    password: str
    role: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra="allow")

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    profile_id: Optional[str] = None  # household_id or worker_id if applicable
    cooperative_id: Optional[str] = None
    worker_type: Optional[str] = None
    user: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True, extra="allow")

class UserResponse(BaseModel):
    id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str
    name: Optional[str] = None
    cooperative_id: Optional[str] = None
    worker_type: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class UserMeResponse(BaseModel):
    user: UserResponse
    profile: Optional[dict] = None
    cooperative: Optional[dict] = None
    role_permissions: Optional[dict] = None

