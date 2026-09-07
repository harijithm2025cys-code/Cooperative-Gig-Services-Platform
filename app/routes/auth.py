from datetime import datetime, timezone
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.config import settings
from app.db.supabase_client import get_supabase_client
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.dependencies import get_current_user
from app.models.auth import UserRegister, UserLogin, Token, UserResponse, UserMeResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserRegister,
    db: Client = Depends(get_supabase_client)
):
    """
    Register a new user (household, worker, or admin).
    Automatically initializes the corresponding profile table (households / workers).
    """
    try:
        # Check if user with this email or phone already exists
        existing = db.table("users").select("id, email, phone").or_(
            f"email.eq.{payload.email},phone.eq.{payload.phone}"
        ).execute()

        if existing.data and len(existing.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email or phone number is already registered."
            )

        user_id = str(uuid.uuid4())
        hashed_pwd = get_password_hash(payload.password)
        now_iso = datetime.now(timezone.utc).isoformat()
        user_name = payload.name or payload.email.split("@")[0]

        # Insert into users table
        user_row = {
            "id": user_id,
            "name": user_name,
            "email": payload.email,
            "phone": payload.phone,
            "role": payload.role,
            "password": payload.password,
            "created_at": now_iso
        }
        
        try:
            user_res = db.table("users").insert(user_row).execute()
        except Exception:
            # Fallback if password column is omitted
            user_row.pop("password", None)
            user_res = db.table("users").insert(user_row).execute()

        profile_id = None

        profile_id = None
        coop_id = payload.cooperative_id
        worker_type = None

        norm_role = payload.role.lower()

        # 1. Customer / Household
        if norm_role in ["customer", "household"]:
            household_row = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "address": payload.address or "Default City Address",
                "latitude": payload.latitude or 12.9716,
                "longitude": payload.longitude or 77.5946
            }
            try:
                hh_res = db.table("households").insert(household_row).execute()
                if hh_res.data:
                    profile_id = hh_res.data[0].get("id")
            except Exception:
                pass

        # 2. Cooperative Worker (Belongs to Association, Pre-Verified by Association)
        elif norm_role in ["cooperative_worker", "worker"] or (payload.worker_type == "cooperative"):
            worker_type = "cooperative"
            worker_row = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "cooperative_id": coop_id,
                "skill": payload.skill or "Specialist",
                "worker_type": "cooperative",
                "member_reg_id": payload.member_reg_id or f"COOP-{random_digits()}",
                "latitude": payload.latitude or 12.9716,
                "longitude": payload.longitude or 77.5946,
                "rating": 5.0,
                # Pre-verified by Association: True
                "is_verified": True,
                "verified_status": True,
                "is_available": True,
                "availability": True,
                "experience_years": 3
            }
            try:
                w_res = db.table("workers").insert(worker_row).execute()
                if w_res.data:
                    profile_id = w_res.data[0].get("id")
            except Exception:
                # Omit optional columns if schema varies
                worker_row.pop("worker_type", None)
                worker_row.pop("member_reg_id", None)
                w_res = db.table("workers").insert(worker_row).execute()
                if w_res.data:
                    profile_id = w_res.data[0].get("id")

        # 3. Independent Worker (Outside Cooperative Hierarchy, Self-Set Rate)
        elif norm_role == "independent_worker" or (payload.worker_type == "independent"):
            worker_type = "independent"
            worker_row = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "cooperative_id": None,  # Outside co-op hierarchy
                "skill": payload.skill or "Independent Technician",
                "worker_type": "independent",
                "hourly_rate": payload.hourly_rate or 400.0,
                "latitude": payload.latitude or 12.9716,
                "longitude": payload.longitude or 77.5946,
                "rating": 4.5,
                "is_verified": False,  # Needs independent KYC
                "verified_status": False,
                "is_available": True,
                "availability": True,
                "experience_years": 2
            }
            try:
                w_res = db.table("workers").insert(worker_row).execute()
                if w_res.data:
                    profile_id = w_res.data[0].get("id")
            except Exception:
                worker_row.pop("worker_type", None)
                worker_row.pop("hourly_rate", None)
                w_res = db.table("workers").insert(worker_row).execute()
                if w_res.data:
                    profile_id = w_res.data[0].get("id")

        # 4. Cooperative Association Head
        elif norm_role in ["cooperative_association_head", "admin"]:
            if payload.society_name:
                # Optionally link or create cooperative association entry
                coop_row = {
                    "id": str(uuid.uuid4()),
                    "name": payload.society_name,
                    "district": payload.district or "Central District",
                    "state": "Tamil Nadu",
                    "verified": True
                }
                try:
                    c_res = db.table("cooperatives").insert(coop_row).execute()
                    if c_res.data:
                        coop_id = c_res.data[0].get("id")
                except Exception:
                    pass

        # 5. Super Admin (Federation Level)
        elif norm_role == "super_admin":
            # Federation wide access
            pass

        # Generate JWT Token with full role claims
        access_token = create_access_token(
            subject=user_id,
            role=payload.role,
            email=payload.email
        )

        return Token(
            access_token=access_token,
            token_type="bearer",
            role=payload.role,
            user_id=user_id,
            email=payload.email,
            profile_id=profile_id,
            cooperative_id=coop_id,
            worker_type=worker_type
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )

@router.post("/login", response_model=Token)
def login(
    payload: UserLogin,
    db: Client = Depends(get_supabase_client)
):
    """
    Authenticate a user using email or phone and password, returning a JWT token.
    """
    if not payload.email and not payload.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either email or phone for login."
        )

    try:
        query = db.table("users").select("*")
        if payload.email:
            query = query.eq("email", payload.email)
        else:
            query = query.eq("phone", payload.phone)

        res = query.execute()
        if not res.data or len(res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials. User not found."
            )

        user = res.data[0]
        user_id = str(user.get("id"))
        role = user.get("role", "household")

        # Check password if stored in table
        stored_pwd = user.get("password") or user.get("password_hash")
        if stored_pwd:
            if stored_pwd != payload.password and not verify_password(payload.password, stored_pwd):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email/phone or password."
                )

        # Retrieve profile_id based on role
        profile_id = None
        if role == "household":
            h_res = db.table("households").select("id").eq("user_id", user_id).execute()
            if h_res.data:
                profile_id = h_res.data[0]["id"]
        elif role == "worker":
            w_res = db.table("workers").select("id").eq("user_id", user_id).execute()
            if w_res.data:
                profile_id = w_res.data[0]["id"]

        access_token = create_access_token(
            subject=user_id,
            role=role,
            email=user.get("email")
        )

        return Token(
            access_token=access_token,
            token_type="bearer",
            role=role,
            user_id=user_id,
            email=user.get("email"),
            profile_id=profile_id
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login error: {str(e)}"
        )

@router.get("/me", response_model=UserMeResponse)
def get_current_user_profile(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Get profile information of currently authenticated user along with role-specific details.
    """
    try:
        user_id = current_user.get("id")
        role = current_user.get("role")
        profile_data = None
        coop_data = None

        if role == "household":
            h_res = db.table("households").select("*").eq("user_id", user_id).execute()
            if h_res.data:
                profile_data = h_res.data[0]

        elif role == "worker":
            w_res = db.table("workers").select("*").eq("user_id", user_id).execute()
            if w_res.data:
                profile_data = w_res.data[0]
                coop_id = profile_data.get("cooperative_id")
                if coop_id:
                    c_res = db.table("cooperatives").select("*").eq("id", coop_id).execute()
                    if c_res.data:
                        coop_data = c_res.data[0]

        user_info = UserResponse(
            id=str(user_id),
            email=current_user.get("email"),
            phone=current_user.get("phone"),
            role=role,
            name=current_user.get("name"),
            created_at=current_user.get("created_at")
        )

        return UserMeResponse(
            user=user_info,
            profile=profile_data,
            cooperative=coop_data
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching user profile: {str(e)}"
        )
