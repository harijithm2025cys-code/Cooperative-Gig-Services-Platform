from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from supabase import Client

from app.db.supabase_client import get_supabase_client
from app.core.dependencies import get_current_user
from app.models.invoice import InvoiceResponse, InvoiceDownloadResponse
from app.services.invoice_service import InvoiceService
from app.services.matching import _BOOKINGS_BY_ID
from app.services.payment_service import _PAYMENTS_BY_BOOKING_ID

router = APIRouter(prefix="/invoices", tags=["Invoices & Receipts"])

@router.get("/booking/{booking_id}", response_model=InvoiceResponse)
def get_invoice_for_booking(
    booking_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    """
    Retrieves or generates the official cooperative invoice for a booking.
    """
    invoice = InvoiceService.get_invoice_by_booking(booking_id, db=db)
    if not invoice:
        # Check if booking exists and generate
        booking = _BOOKINGS_BY_ID.get(booking_id)
        if not booking and db:
            try:
                res = db.table("bookings").select("*").eq("id", booking_id).execute()
                if res.data:
                    booking = res.data[0]
            except Exception:
                pass

        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Booking '{booking_id}' not found.")

        pay_rec = _PAYMENTS_BY_BOOKING_ID.get(booking_id)
        amount = float(booking.get("final_amount") or booking.get("amount") or (pay_rec.get("amount") if pay_rec else 450.0))

        invoice = InvoiceService.get_or_create_invoice(
            booking_id=booking_id,
            customer_id=booking.get("customer_id") or booking.get("household_id") or current_user["id"],
            customer_name=current_user.get("name", "Customer"),
            service_name=booking.get("service_id", "Cooperative Labour Service"),
            amount=amount,
            cooperative_name=booking.get("worker_coop", "Metro Labour Cooperative Society"),
            worker_count=booking.get("required_worker_count", 1),
            payment_id=pay_rec.get("razorpay_payment_id") if pay_rec else None,
            db=db
        )

    return InvoiceResponse(
        id=invoice["id"],
        booking_id=invoice["booking_id"],
        invoice_number=invoice["invoice_number"],
        customer_id=invoice["customer_id"],
        customer_name=invoice.get("customer_name"),
        cooperative_name=invoice.get("cooperative_name"),
        service_name=invoice["service_name"],
        service_date=invoice["service_date"],
        worker_count=invoice.get("worker_count", 1),
        unit_price=invoice["unit_price"],
        total_amount=invoice["total_amount"],
        currency=invoice.get("currency", "INR"),
        invoice_status=invoice.get("invoice_status", "GENERATED"),
        payment_id=invoice.get("payment_id"),
        generated_at=invoice["generated_at"],
        metadata=invoice.get("metadata")
    )

@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice_by_id(
    invoice_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    invoice = InvoiceService.get_invoice_by_id(invoice_id, db=db)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    return InvoiceResponse(
        id=invoice["id"],
        booking_id=invoice["booking_id"],
        invoice_number=invoice["invoice_number"],
        customer_id=invoice["customer_id"],
        customer_name=invoice.get("customer_name"),
        cooperative_name=invoice.get("cooperative_name"),
        service_name=invoice["service_name"],
        service_date=invoice["service_date"],
        worker_count=invoice.get("worker_count", 1),
        unit_price=invoice["unit_price"],
        total_amount=invoice["total_amount"],
        currency=invoice.get("currency", "INR"),
        invoice_status=invoice.get("invoice_status", "GENERATED"),
        payment_id=invoice.get("payment_id"),
        generated_at=invoice["generated_at"],
        metadata=invoice.get("metadata")
    )

@router.get("/{invoice_id}/download", response_class=HTMLResponse)
def download_invoice_html(
    invoice_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_client)
):
    invoice = InvoiceService.get_invoice_by_id(invoice_id, db=db)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    html = InvoiceService.render_invoice_html(invoice)
    return HTMLResponse(content=html)
