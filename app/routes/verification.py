from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from supabase import Client
from app.db.supabase_client import get_supabase_client

router = APIRouter(prefix="/verification", tags=["Document Verification (Mock Government KYC)"])

class GovtIdVerificationRequest(BaseModel):
    id_type: str = Field(..., description="Document type: 'aadhaar', 'pan', or 'voter_id'")
    id_number: str = Field(..., description="The ID number to verify")
    full_name: Optional[str] = Field(None, description="Optional name to match against identity record")

class GovtIdVerificationResponse(BaseModel):
    is_valid: bool
    status: str
    message: str
    police_clearance_status: Optional[str] = "CLEARED"
    record: Optional[dict] = None

@router.post("/verify-govt-id", response_model=GovtIdVerificationResponse)
def verify_government_id(
    payload: GovtIdVerificationRequest,
    db: Client = Depends(get_supabase_client)
):
    """
    Mock Government Document Verification Gateway (DigiLocker & NCD Mock).
    Matches Aadhaar / PAN / Voter ID against the mock_govt_id_registry table.
    """
    try:
        clean_id = payload.id_number.replace("-", "").replace(" ", "").strip()
        id_type = payload.id_type.lower().strip()

        try:
            query = db.table("mock_govt_id_registry").select("*")
            if "aadhaar" in id_type:
                query = query.eq("aadhaar_number", clean_id)
            elif "pan" in id_type:
                query = query.eq("pan_number", clean_id.upper())
            elif "voter" in id_type:
                query = query.eq("voter_id", clean_id.upper())
            else:
                query = query.or_(f"aadhaar_number.eq.{clean_id},pan_number.eq.{clean_id.upper()},voter_id.eq.{clean_id.upper()}")

            res = query.execute()
            if res.data and len(res.data) > 0:
                matched_record = res.data[0]
                return GovtIdVerificationResponse(
                    is_valid=True,
                    status="VERIFIED_AUTHENTIC",
                    message=f"Government ID verified successfully for {matched_record.get('full_name')}.",
                    police_clearance_status=matched_record.get("police_clearance_status", "CLEARED"),
                    record={
                        "full_name": matched_record.get("full_name"),
                        "state": matched_record.get("state"),
                        "dob": str(matched_record.get("dob")),
                        "verification_status": matched_record.get("verification_status")
                    }
                )
        except Exception:
            pass

        # Fallback simulator for dynamic demo numbers
        if len(clean_id) >= 10:
            return GovtIdVerificationResponse(
                is_valid=True,
                status="VERIFIED_DEMO_MATCH",
                message="ID verified successfully via Government Mock Gateway.",
                police_clearance_status="CLEARED",
                record={
                    "full_name": payload.full_name or "Verified Citizen",
                    "verification_status": "VERIFIED_ACTIVE"
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Government ID format. Minimum 10 characters required."
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification gateway error: {str(e)}"
        )
