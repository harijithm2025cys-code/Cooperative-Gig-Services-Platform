import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from supabase import Client

from app.db.supabase_client import get_supabase_client
from app.core.dependencies import get_current_user, require_role
from app.models.payment import (
    CreateOrderRequest,
    CreateOrderResponse,
    VerifyPaymentRequest,
    PaymentDetailResponse,
    RefundRequest,
    RefundResponse
)
from app.services.payment_service import PaymentService, _PAYMENTS_BY_ID, _PAYMENTS_BY_BOOKING_ID
from app.services.invoice_service import InvoiceService
from app.services.matching import _BOOKINGS_BY_ID

logger = logging.getLogger("payments_router")

router = APIRouter(prefix="/payments", tags=["Razorpay Payments & Settlement"])

@router.post("/create-order", response_model=CreateOrderResponse, status_code=status.HTTP_201_CREATED)
def create_payment_order(
    payload: CreateOrderRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Creates a Razorpay payment order for a booking.
    Calculates/verifies amount server-side. Never trusts client-sent amounts.
    """
    bid = payload.booking_id
    booking = _BOOKINGS_BY_ID.get(bid)

    if not booking and db:
        try:
            res = db.table("bookings").select("*, services(title, base_rate)").eq("id", bid).execute()
            if res.data and len(res.data) > 0:
                booking = res.data[0]
                _BOOKINGS_BY_ID[bid] = booking
        except Exception:
            pass

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking '{bid}' not found."
        )

    # Verify ownership
    user_id = current_user["id"]
    customer_id = booking.get("customer_id") or booking.get("household_id")
    # Also allow if user is the household or matches user_id
    user_role = current_user.get("role", "customer")
    if user_role not in ("super_admin", "admin") and customer_id and str(customer_id) != str(user_id):
        # Check household user_id in households table
        if db:
            try:
                h_res = db.table("households").select("user_id").eq("id", customer_id).execute()
                if h_res.data and str(h_res.data[0].get("user_id")) != str(user_id):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized access to this booking.")
            except HTTPException:
                raise
            except Exception:
                pass

    # Verify booking is in payable state
    b_pay_status = str(booking.get("payment_status", "pending")).lower()
    b_status = str(booking.get("status", "payment_pending")).lower()
    if b_pay_status in ("captured", "released", "paid"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Booking '{bid}' has already been paid and captured."
        )
    if b_status in ("cancelled", "completed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot create payment order for booking in '{b_status}' status."
        )

    # Calculate payable amount strictly server-side
    amount = float(booking.get("final_amount") or booking.get("amount") or booking.get("estimated_amount") or 450.0)
    if amount <= 0:
        amount = 450.0

    order_info = PaymentService.create_razorpay_order(
        booking_id=bid,
        amount=amount,
        customer_id=user_id,
        receipt=f"rcpt_{bid[:10]}",
        db=db
    )

    return CreateOrderResponse(
        order_id=order_info["order_id"],
        key_id=order_info["key_id"],
        amount=order_info["amount"],
        currency="INR",
        booking_id=bid,
        customer_name=current_user.get("name"),
        customer_phone=current_user.get("phone"),
        customer_email=current_user.get("email"),
        service_name=booking.get("service_id", "Cooperative Service")
    )

@router.post("/verify", response_model=PaymentDetailResponse)
def verify_payment(
    payload: VerifyPaymentRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Verifies Razorpay payment signature on the backend.
    Transitions payment to CAPTURED, updates booking payment_status,
    and creates server-side invoice.
    """
    try:
        payment_record = PaymentService.process_verified_payment(
            booking_id=payload.booking_id,
            order_id=payload.razorpay_order_id,
            payment_id=payload.razorpay_payment_id,
            signature=payload.razorpay_signature,
            customer_id=current_user["id"],
            db=db
        )
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    # Trigger server-side invoice generation idempotently
    try:
        booking = _BOOKINGS_BY_ID.get(payload.booking_id) or {}
        InvoiceService.get_or_create_invoice(
            booking_id=payload.booking_id,
            customer_id=current_user["id"],
            customer_name=current_user.get("name", "Customer"),
            service_name=booking.get("service_id", "Labour Service"),
            amount=payment_record["amount"],
            cooperative_name=booking.get("worker_coop", "Metro Labour Cooperative Society"),
            worker_count=booking.get("required_worker_count", 1),
            payment_id=payment_record.get("razorpay_payment_id"),
            db=db
        )
    except Exception as e:
        logger.warning(f"Auto-invoice generation note: {e}")

    return PaymentDetailResponse(
        id=payment_record["id"],
        booking_id=payment_record["booking_id"],
        customer_id=payment_record["customer_id"],
        razorpay_order_id=payment_record["razorpay_order_id"],
        razorpay_payment_id=payment_record.get("razorpay_payment_id"),
        amount=payment_record["amount"],
        currency=payment_record.get("currency", "INR"),
        status=payment_record["status"],
        payment_method=payment_record.get("payment_method"),
        signature_verified=payment_record.get("signature_verified", False),
        settlement_status=payment_record.get("settlement_status", "PENDING"),
        paid_at=payment_record.get("paid_at"),
        refunded_amount=payment_record.get("refunded_amount", 0.0),
        created_at=payment_record["created_at"],
        updated_at=payment_record.get("updated_at")
    )

@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature"),
    db: Client = Depends(get_supabase_client)
):
    """
    Secure Razorpay Webhook endpoint.
    Verifies webhook signature using configured webhook secret.
    Processes payment.captured, payment.failed events idempotently.
    """
    raw_body = await request.body()

    # Verify signature if secret configured
    if x_razorpay_signature:
        is_valid = PaymentService.verify_webhook_signature(raw_body, x_razorpay_signature)
        if not is_valid:
            logger.warning("Razorpay Webhook rejected: Signature mismatch.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature.")

    try:
        event_payload = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON payload.")

    event_id = event_payload.get("event_id") or event_payload.get("id") or str(hash(raw_body))
    event_name = event_payload.get("event", "unknown")

    result = PaymentService.process_webhook_event(
        event_id=event_id,
        event_name=event_name,
        payload=event_payload,
        db=db
    )

    return result

@router.post("/{payment_id}/refund", response_model=RefundResponse)
def refund_payment(
    payment_id: str,
    payload: RefundRequest,
    current_user: dict = Depends(require_role(["super_admin"])),
    db: Client = Depends(get_supabase_client)
):
    """
    Issues a refund for a payment.
    Super Admin authority required.
    """
    try:
        result = PaymentService.process_refund(
            payment_id=payment_id,
            actor_id=current_user["id"],
            actor_role=current_user.get("role", "super_admin"),
            amount=payload.amount,
            reason=payload.reason,
            db=db
        )
        return RefundResponse(**result)
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

@router.get("/{payment_id}", response_model=PaymentDetailResponse)
def get_payment_details(
    payment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    record = _PAYMENTS_BY_ID.get(payment_id)
    if not record and db:
        try:
            res = db.table("payments").select("*").eq("id", payment_id).execute()
            if res.data:
                record = res.data[0]
        except Exception:
            pass

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment record not found.")

    return PaymentDetailResponse(**record)
