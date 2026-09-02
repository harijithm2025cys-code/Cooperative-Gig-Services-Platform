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

        # Insert into users table
        user_row = {
            "id": user_id,
            "email": payload.email,
            "phone": payload.phone,
            "role": payload.role,
            "created_at": now_iso
        }
        # Note: In production Supabase Auth or with a password column:
        # We store or hash inside user record if column exists
        try:
            user_res = db.table("users").insert(user_row).execute()
        except Exception:
            # Fallback if users table requires additional fields or password column
            user_row["password"] = hashed_pwd
            user_res = db.table("users").insert(user_row).execute()

        profile_id = None

        # If role is household, initialize households table entry
        if payload.role == "household":
            household_row = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "address": payload.address or "Default Address",
                "latitude": payload.latitude or 12.9716,
                "longitude": payload.longitude or 77.5946
            }
            hh_res = db.table("households").insert(household_row).execute()
            if hh_res.data:
                profile_id = hh_res.data[0].get("id")

        # If role is worker, initialize workers table entry
        elif payload.role == "worker":
            worker_row = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "cooperative_id": payload.cooperative_id,
                "skill": payload.skill or "General Maintenance",
                "service_area": payload.service_area or "Default District",
                "rating": 0.0,
                "availability": True,
                "verified_status": False,
                "latitude": payload.latitude or 12.9716,
                "longitude": payload.longitude or 77.5946
            }
            w_res = db.table("workers").insert(worker_row).execute()
            if w_res.data:
                profile_id = w_res.data[0].get("id")

        # Generate JWT Token
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
            profile_id=profile_id
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
        stored_hash = user.get("password") or user.get("password_hash")
        if stored_hash:
            if not verify_password(payload.password, stored_hash):
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
