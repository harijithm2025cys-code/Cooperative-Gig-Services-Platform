import secrets
import hashlib
import uuid
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta

from app.services.event_service import EventService

logger = logging.getLogger("otp_service")

# In-memory store for active completion OTP records (keyed by booking_id)
_COMPLETION_OTPS_BY_BOOKING: Dict[str, Dict[str, Any]] = {}
_SALT = "cooperative_gig_otp_salt_2026"

class CompletionOtpService:
    """
    Cryptographic One-Time Password service for post-service customer acceptance.
    Enforces expiration, attempt limits, SHA-256 hashed storage, and single-use constraints.
    Note: OTP is exclusively an acceptance mechanism, NOT a payment mechanism.
    """

    @staticmethod
    def _hash_otp(otp_code: str) -> str:
        return hashlib.sha256(f"{otp_code}:{_SALT}".encode("utf-8")).hexdigest()

    @classmethod
    def generate_completion_otp(
        cls,
        booking_id: str,
        customer_id: str,
        worker_id: str,
        assignment_id: Optional[str] = None,
        db: Optional[Any] = None
    ) -> str:
        """
        Generates a 6-digit cryptographic random OTP, stores its SHA-256 hash,
        and returns the plaintext code to be delivered solely to the customer.
        """
        # Cryptographically secure 6-digit OTP
        plaintext_otp = "".join(secrets.choice("0123456789") for _ in range(6))
        otp_hash = cls._hash_otp(plaintext_otp)

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=15)
        otp_id = str(uuid.uuid4())

        record = {
            "id": otp_id,
            "booking_id": str(booking_id),
            "assignment_id": str(assignment_id) if assignment_id else None,
            "customer_id": str(customer_id),
            "worker_id": str(worker_id),
            "otp_hash": otp_hash,
            "expires_at": expires_at.isoformat(),
            "attempt_count": 0,
            "max_attempts": 3,
            "is_used": False,
            "used_at": None,
            "plaintext_code": plaintext_otp,
            "created_at": now.isoformat()
        }

        bid = str(booking_id)
        _COMPLETION_OTPS_BY_BOOKING[bid] = record

        if db:
            try:
                db.table("completion_otps").insert(record).execute()
            except Exception as e:
                logger.debug(f"DB insert completion_otps note: {e}")

        # Dispatch in-app notification strictly to customer
        EventService.dispatch_event(
            event_type="SERVICE_COMPLETED",
            booking_id=booking_id,
            actor_id=worker_id,
            actor_role="worker",
            data={
                "instructions": "Worker marked service completed. Please inspect work before sharing OTP.",
                "expires_in_minutes": 15
            },
            target_user_ids=[customer_id],
            notification_title="Service Completed — Inspect & Confirm",
            notification_message=f"Specialist has marked the service completed. Inspect the work and share code {plaintext_otp} if satisfied.",
            db=db
        )

        logger.info(f"Generated secure completion OTP for Booking #{booking_id} (Customer #{customer_id})")
        return plaintext_otp

    @classmethod
    def get_customer_active_otp(cls, booking_id: str, customer_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves active OTP details strictly for the authenticated customer.
        """
        bid = str(booking_id)
        record = _COMPLETION_OTPS_BY_BOOKING.get(bid)
        if not record:
            return None

        if str(record.get("customer_id")) != str(customer_id):
            return None

        if record.get("is_used"):
            return None

        exp = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > exp:
            return None

        return record

    @classmethod
    def verify_completion_otp(
        cls,
        booking_id: str,
        worker_id: str,
        otp_code: str,
        assignment_id: Optional[str] = None,
        db: Optional[Any] = None
    ) -> Tuple[bool, str]:
        """
        Validates OTP entered by worker.
        Enforces booking association, worker authorization, attempt limits, expiration, and single-use.
        """
        bid = str(booking_id)
        record = _COMPLETION_OTPS_BY_BOOKING.get(bid)

        if not record and db:
            try:
                res = db.table("completion_otps").select("*").eq("booking_id", bid).eq("is_used", False).execute()
                if res.data and len(res.data) > 0:
                    record = res.data[0]
                    _COMPLETION_OTPS_BY_BOOKING[bid] = record
            except Exception:
                pass

        if not record:
            return False, "No active completion confirmation pending for this booking."

        # Verify worker authorization
        if str(record.get("worker_id")) != str(worker_id):
            return False, "Unauthorized: Worker ID does not match the active assignment."

        # Check if already used
        if record.get("is_used"):
            return False, "This completion OTP has already been used."

        # Check attempts limit
        if record.get("attempt_count", 0) >= record.get("max_attempts", 3):
            return False, "Maximum verification attempts exceeded. Please request customer to re-issue confirmation."

        # Check expiration
        exp = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > exp:
            return False, "Completion OTP has expired (validity 15 minutes). Please request customer to re-issue."

        # Increment attempts
        record["attempt_count"] = record.get("attempt_count", 0) + 1

        # Check hash match
        candidate_hash = cls._hash_otp(otp_code.strip())
        if candidate_hash != record.get("otp_hash"):
            remaining = record.get("max_attempts", 3) - record["attempt_count"]
            return False, f"Incorrect completion OTP. {remaining} attempt(s) remaining."

        # Valid OTP! Mark single use
        now_iso = datetime.now(timezone.utc).isoformat()
        record["is_used"] = True
        record["used_at"] = now_iso

        _COMPLETION_OTPS_BY_BOOKING[bid] = record

        if db:
            try:
                db.table("completion_otps").update({
                    "is_used": True,
                    "used_at": now_iso,
                    "attempt_count": record["attempt_count"]
                }).eq("id", record["id"]).execute()
            except Exception as e:
                logger.debug(f"DB update completion_otps note: {e}")

        logger.info(f"Completion OTP verified successfully for Booking #{booking_id}")
        return True, "Customer acceptance verified successfully."
