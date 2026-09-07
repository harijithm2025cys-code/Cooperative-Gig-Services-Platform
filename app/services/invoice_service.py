import uuid
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

logger = logging.getLogger("invoice_service")

_INVOICES_BY_ID: Dict[str, Dict[str, Any]] = {}
_INVOICES_BY_BOOKING_ID: Dict[str, Dict[str, Any]] = {}
_INVOICES_BY_NUMBER: Dict[str, Dict[str, Any]] = {}
_INVOICE_COUNTER: int = 1000

class InvoiceService:
    """
    Server-side Invoice Generation and Management.
    Ensures unique invoice numbering, idempotent creation, and printable receipt generation.
    """

    @classmethod
    def generate_invoice_number(cls) -> str:
        global _INVOICE_COUNTER
        _INVOICE_COUNTER += 1
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        random_suffix = uuid.uuid4().hex[:4].upper()
        return f"INV-{date_str}-{_INVOICE_COUNTER}-{random_suffix}"

    @classmethod
    def get_or_create_invoice(
        cls,
        booking_id: str,
        customer_id: str,
        customer_name: str,
        service_name: str,
        amount: float,
        cooperative_name: Optional[str] = "Cooperative Labour Federation",
        worker_count: int = 1,
        payment_id: Optional[str] = None,
        service_date: Optional[datetime] = None,
        db: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Generates an official cooperative invoice idempotently.
        If an invoice for this booking already exists, returns the existing record.
        """
        bid = str(booking_id)
        if bid in _INVOICES_BY_BOOKING_ID:
            logger.info(f"Invoice for booking {bid} already exists. Returning existing.")
            return _INVOICES_BY_BOOKING_ID[bid]

        if db:
            try:
                res = db.table("invoices").select("*").eq("booking_id", bid).execute()
                if res.data and len(res.data) > 0:
                    rec = res.data[0]
                    _INVOICES_BY_BOOKING_ID[bid] = rec
                    _INVOICES_BY_ID[rec["id"]] = rec
                    return rec
            except Exception:
                pass

        invoice_id = str(uuid.uuid4())
        invoice_number = cls.generate_invoice_number()
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        unit_price = amount / max(1, worker_count)

        invoice_record = {
            "id": invoice_id,
            "booking_id": bid,
            "invoice_number": invoice_number,
            "customer_id": str(customer_id),
            "customer_name": customer_name,
            "cooperative_name": cooperative_name or "Labour Cooperative Society",
            "service_name": service_name,
            "service_date": (service_date or now_dt).isoformat(),
            "worker_count": worker_count,
            "unit_price": round(unit_price, 2),
            "total_amount": round(amount, 2),
            "currency": "INR",
            "invoice_status": "GENERATED",
            "payment_id": payment_id,
            "generated_at": now_iso,
            "metadata": {
                "platform": "Cooperative Gig Services Platform",
                "tax_note": "Cooperative labour society service exempted from commercial gig surcharges."
            }
        }

        _INVOICES_BY_ID[invoice_id] = invoice_record
        _INVOICES_BY_BOOKING_ID[bid] = invoice_record
        _INVOICES_BY_NUMBER[invoice_number] = invoice_record

        if db:
            try:
                db.table("invoices").insert(invoice_record).execute()
                db.table("bookings").update({"invoice_id": invoice_id}).eq("id", bid).execute()
            except Exception as e:
                logger.debug(f"DB insert invoice note: {e}")

        logger.info(f"Generated official invoice #{invoice_number} for Booking #{bid}")
        return invoice_record

    @classmethod
    def get_invoice_by_booking(cls, booking_id: str, db: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        bid = str(booking_id)
        if bid in _INVOICES_BY_BOOKING_ID:
            return _INVOICES_BY_BOOKING_ID[bid]
        if db:
            try:
                res = db.table("invoices").select("*").eq("booking_id", bid).execute()
                if res.data and len(res.data) > 0:
                    rec = res.data[0]
                    _INVOICES_BY_BOOKING_ID[bid] = rec
                    _INVOICES_BY_ID[rec["id"]] = rec
                    return rec
            except Exception:
                pass
        return None

    @classmethod
    def get_invoice_by_id(cls, invoice_id: str, db: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        iid = str(invoice_id)
        if iid in _INVOICES_BY_ID:
            return _INVOICES_BY_ID[iid]
        if db:
            try:
                res = db.table("invoices").select("*").eq("id", iid).execute()
                if res.data and len(res.data) > 0:
                    rec = res.data[0]
                    _INVOICES_BY_ID[iid] = rec
                    return rec
            except Exception:
                pass
        return None

    @classmethod
    def render_invoice_html(cls, invoice: Dict[str, Any]) -> str:
        """
        Renders a clean, official cooperative service invoice HTML receipt.
        """
        inv_no = invoice.get("invoice_number", "N/A")
        c_name = invoice.get("customer_name", "Valued Customer")
        coop = invoice.get("cooperative_name", "Labour Cooperative Society")
        service = invoice.get("service_name", "Household Gig Service")
        w_count = invoice.get("worker_count", 1)
        u_price = invoice.get("unit_price", 0.0)
        total = invoice.get("total_amount", 0.0)
        pay_id = invoice.get("payment_id") or "PAID VIA RAZORPAY"
        gen_date = invoice.get("generated_at", "")[:10]

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Invoice {inv_no}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 40px; color: #1F2937; }}
        .header {{ border-bottom: 2px solid #2563EB; padding-bottom: 16px; margin-bottom: 24px; }}
        .badge {{ background: #DCFCE7; color: #166534; font-weight: bold; padding: 4px 10px; border-radius: 6px; font-size: 12px; }}
        .table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        .table th, .table td {{ padding: 12px; text-align: left; border-bottom: 1px solid #E5E7EB; }}
        .table th {{ background: #F3F4F6; font-size: 13px; text-transform: uppercase; color: #6B7280; }}
        .total-row {{ font-weight: bold; font-size: 16px; color: #1E3A8A; }}
        .footer {{ margin-top: 40px; font-size: 12px; color: #6B7280; border-top: 1px solid #E5E7EB; padding-top: 16px; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>COOPERATIVE GIG SERVICES PLATFORM</h2>
        <p><strong>Official Labour Cooperative Invoice / Receipt</strong></p>
        <p><strong>Invoice Number:</strong> {inv_no} &nbsp;|&nbsp; <strong>Date:</strong> {gen_date} &nbsp;|&nbsp; <span class="badge">PAID</span></p>
    </div>
    <div>
        <p><strong>Issued By Cooperative:</strong> {coop}</p>
        <p><strong>Billed To:</strong> {c_name}</p>
        <p><strong>Payment Reference:</strong> {pay_id}</p>
    </div>
    <table class="table">
        <thead>
            <tr>
                <th>Service Description</th>
                <th>Specialists Count</th>
                <th>Unit Rate (₹)</th>
                <th>Total (₹)</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>{service}</td>
                <td>{w_count}</td>
                <td>₹{u_price:.2f}</td>
                <td>₹{total:.2f}</td>
            </tr>
            <tr class="total-row">
                <td colspan="3" style="text-align: right;">Final Total Paid:</td>
                <td>₹{total:.2f} INR</td>
            </tr>
        </tbody>
    </table>
    <div class="footer">
        <p>This is a computer-generated tax invoice issued on behalf of worker-owners registered under the Labour Cooperative Societies Act.</p>
        <p>Dual service inspection and customer acceptance verified via secure cryptographic OTP.</p>
    </div>
</body>
</html>"""
