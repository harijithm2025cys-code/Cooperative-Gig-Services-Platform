import hmac
import hashlib
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.services.payment_service import (
    PaymentService,
    _PAYMENTS_BY_ID,
    _PAYMENTS_BY_ORDER_ID,
    _PAYMENTS_BY_BOOKING_ID,
    _FINANCIAL_AUDIT_LOGS,
    _PROCESSED_WEBHOOK_EVENTS
)
from app.services.invoice_service import (
    InvoiceService,
    _INVOICES_BY_ID,
    _INVOICES_BY_BOOKING_ID
)
from app.services.otp_service import (
    CompletionOtpService,
    _COMPLETION_OTPS_BY_BOOKING
)
from app.services.matching import _BOOKINGS_BY_ID, _ASSIGNMENTS_BY_ID
from app.routes.complaints import _COMPLAINTS_BY_ID

client = TestClient(app)

def run_tests():
    print("==================================================")
    print("RUNNING PHASE 5 PAYMENT, INVOICE, OTP & DISPUTE TESTS")
    print("==================================================")

    from app.core.dependencies import get_current_user

    current_user_context = {"id": "usr_cust_p5", "role": "customer", "name": "Customer Ramesh", "email": "customer@example.com"}

    def override_current_user():
        return current_user_context

    app.dependency_overrides[get_current_user] = override_current_user

    headers_cust = {}
    headers_worker = {}
    headers_assoc_1 = {}
    headers_assoc_2 = {}
    headers_admin = {}

    # Setup seed booking
    test_bid = "bk_phase5_test_01"
    _BOOKINGS_BY_ID[test_bid] = {
        "id": test_bid,
        "customer_id": "usr_cust_p5",
        "household_id": "usr_cust_p5",
        "worker_id": "usr_worker_p5",
        "service_id": "Plumbing",
        "status": "in_progress",
        "amount": 750.0,
        "final_amount": 750.0,
        "payment_status": "pending",
        "settlement_status": "PENDING",
        "cooperative_id": "coop_north_01",
        "required_worker_count": 1,
        "worker_coop": "North City Labour Cooperative",
    }

    test_asgn_id = "asgn_phase5_test_01"
    _ASSIGNMENTS_BY_ID[test_asgn_id] = {
        "id": test_asgn_id,
        "booking_id": test_bid,
        "worker_id": "usr_worker_p5",
        "status": "IN_PROGRESS",
    }

    # -------------------------------------------------------------
    # 1. Razorpay Order Creation & Server-Side Amount Validation
    # -------------------------------------------------------------
    print("\n--- 1. Testing Razorpay Order Creation & Ownership ---")
    resp_order = client.post("/payments/create-order", json={"booking_id": test_bid}, headers=headers_cust)
    assert resp_order.status_code == 201, f"Expected 201, got {resp_order.status_code}: {resp_order.text}"
    order_data = resp_order.json()
    assert "order_id" in order_data
    assert order_data["amount"] == 750.0, f"Expected 750.0, got {order_data['amount']}"
    assert order_data["booking_id"] == test_bid
    order_id = order_data["order_id"]
    print(f"[PASS] Order created with order_id={order_id}, amount=INR {order_data['amount']} strictly from server.")

    # -------------------------------------------------------------
    # 2. Razorpay Signature Verification & Tamper Resistance
    # -------------------------------------------------------------
    print("\n--- 2. Testing Signature Verification & Tamper Resistance ---")
    test_payment_id = "pay_test_phase5_999"
    secret = PaymentService.get_key_secret()
    valid_msg = f"{order_id}|{test_payment_id}".encode("utf-8")
    valid_sig = hmac.new(secret.encode("utf-8"), valid_msg, hashlib.sha256).hexdigest()

    # Forged signature must fail
    resp_tamper = client.post("/payments/verify", json={
        "booking_id": test_bid,
        "razorpay_order_id": order_id,
        "razorpay_payment_id": test_payment_id,
        "razorpay_signature": "forged_signature_xyz_123"
    }, headers=headers_cust)
    assert resp_tamper.status_code == 400, f"Expected 400 for forged signature, got {resp_tamper.status_code}"
    print("[PASS] Forged signature rejected with HTTP 400.")

    # Valid signature passes
    resp_verify = client.post("/payments/verify", json={
        "booking_id": test_bid,
        "razorpay_order_id": order_id,
        "razorpay_payment_id": test_payment_id,
        "razorpay_signature": valid_sig
    }, headers=headers_cust)
    assert resp_verify.status_code == 200, f"Expected 200, got {resp_verify.status_code}: {resp_verify.text}"
    pay_data = resp_verify.json()
    assert pay_data["status"] == "CAPTURED"
    assert pay_data["settlement_status"] == "PENDING"
    assert pay_data["signature_verified"] is True
    print(f"[PASS] Valid signature verified. Payment captured. Settlement set to PENDING (no fake escrow).")

    # -------------------------------------------------------------
    # 3. Idempotent Payment Verification & Webhook Safety
    # -------------------------------------------------------------
    print("\n--- 3. Testing Idempotent Verification & Webhooks ---")
    resp_reverify = client.post("/payments/verify", json={
        "booking_id": test_bid,
        "razorpay_order_id": order_id,
        "razorpay_payment_id": test_payment_id,
        "razorpay_signature": valid_sig
    }, headers=headers_cust)
    assert resp_reverify.status_code == 200
    assert resp_reverify.json()["id"] == pay_data["id"]
    print("[PASS] Duplicate verify request handled idempotently without duplicate records.")

    # Webhook handling
    webhook_body = {
        "event": "payment.captured",
        "event_id": "evt_webhook_123",
        "payload": {
            "payment": {
                "entity": {
                    "id": test_payment_id,
                    "order_id": order_id,
                    "amount": 75000
                }
            }
        }
    }
    resp_wh1 = client.post("/payments/webhook", json=webhook_body)
    assert resp_wh1.status_code == 200
    resp_wh2 = client.post("/payments/webhook", json=webhook_body)
    assert resp_wh2.status_code == 200
    assert resp_wh2.json().get("status") == "skipped"
    print("[PASS] Duplicate webhook event handled safely and idempotently.")

    # -------------------------------------------------------------
    # 4. Server-Side Invoice Generation & Download
    # -------------------------------------------------------------
    print("\n--- 4. Testing Server-Side Invoice Generation & Download ---")
    resp_inv = client.get(f"/invoices/booking/{test_bid}", headers=headers_cust)
    assert resp_inv.status_code == 200, f"Expected 200, got {resp_inv.status_code}: {resp_inv.text}"
    inv_data = resp_inv.json()
    assert "INV-" in inv_data["invoice_number"]
    assert inv_data["total_amount"] == 750.0
    print(f"[PASS] Unique invoice generated: {inv_data['invoice_number']} for INR {inv_data['total_amount']}.")

    # Download HTML
    resp_dl = client.get(f"/invoices/{inv_data['id']}/download", headers=headers_cust)
    assert resp_dl.status_code == 200
    assert "<html" in resp_dl.text.lower()
    assert inv_data["invoice_number"] in resp_dl.text
    print("[PASS] Clean server-side HTML receipt rendered successfully.")

    # -------------------------------------------------------------
    # 5. Service Completion & Cryptographic 6-Digit OTP Acceptance
    # -------------------------------------------------------------
    print("\n--- 5. Testing Service Completion & Cryptographic 6-Digit OTP ---")
    # Worker completes service
    current_user_context.clear()
    current_user_context.update({"id": "usr_worker_p5", "role": "cooperative_worker", "worker_id": "usr_worker_p5", "name": "Worker Suresh"})
    resp_comp = client.post(f"/workers/usr_worker_p5/assignments/{test_asgn_id}/complete-service")
    assert resp_comp.status_code == 200, f"Expected 200, got {resp_comp.status_code}: {resp_comp.text}"
    assert resp_comp.json()["status"] == "CUSTOMER_CONFIRMATION_PENDING"
    assert "otp_code" not in resp_comp.json(), "Worker MUST NOT see plaintext OTP in API response!"
    print("[PASS] Worker marked service complete. State transitioned to CUSTOMER_CONFIRMATION_PENDING. Plaintext OTP withheld from worker.")

    # Customer retrieves OTP
    current_user_context.clear()
    current_user_context.update({"id": "usr_cust_p5", "role": "customer", "name": "Customer Ramesh"})
    resp_cust_otp = client.get(f"/bookings/{test_bid}/completion-otp")
    assert resp_cust_otp.status_code == 200, f"Expected 200, got {resp_cust_otp.status_code}"
    otp_code = resp_cust_otp.json()["otp_code"]
    assert len(otp_code) == 6 and otp_code.isdigit(), f"Expected 6-digit numeric OTP, got {otp_code}"
    print(f"[PASS] Customer received 6-digit inspection OTP: {otp_code}")

    # Worker forbidden from customer endpoint
    current_user_context.clear()
    current_user_context.update({"id": "usr_worker_p5", "role": "cooperative_worker", "worker_id": "usr_worker_p5"})
    resp_worker_forbidden = client.get(f"/bookings/{test_bid}/completion-otp")
    assert resp_worker_forbidden.status_code == 403
    print("[PASS] Worker prohibited from calling customer OTP retrieval endpoint.")

    # Worker submits wrong OTP
    resp_wrong = client.post("/workers/usr_worker_p5/verify-completion-otp", json={
        "booking_id": test_bid,
        "otp_code": "000000"
    })
    err_msg = resp_wrong.json().get("error") or resp_wrong.json().get("detail", "")
    assert "attempt(s) remaining" in err_msg
    print(f"[PASS] Incorrect OTP rejected with remaining attempt count notice.")

    # Worker submits valid OTP
    resp_correct = client.post("/workers/usr_worker_p5/verify-completion-otp", json={
        "booking_id": test_bid,
        "otp_code": otp_code
    })
    assert resp_correct.status_code == 200, f"Expected 200, got {resp_correct.status_code}: {resp_correct.text}"
    assert resp_correct.json()["status"] == "completed"
    assert resp_correct.json()["settlement_status"] == "ELIGIBLE"
    print("[PASS] Valid OTP verified. Booking marked COMPLETED and settlement marked ELIGIBLE.")

    # Reusing used OTP must fail
    resp_reused = client.post("/workers/usr_worker_p5/verify-completion-otp", json={
        "booking_id": test_bid,
        "otp_code": otp_code
    })
    assert resp_reused.status_code == 400
    print("[PASS] Reused completion OTP strictly rejected.")

    # -------------------------------------------------------------
    # 6. Complaint / Dispute Workflow & Settlement Freezing
    # -------------------------------------------------------------
    print("\n--- 6. Testing Complaint, Dispute Freezing & Cooperative Isolation ---")
    current_user_context.clear()
    current_user_context.update({"id": "usr_cust_p5", "role": "customer"})
    resp_complaint = client.post("/complaints/", json={
        "booking_id": test_bid,
        "category": "Service incomplete",
        "description": "Pipe leaking slightly under sink after technician left."
    })
    assert resp_complaint.status_code == 201, f"Expected 201, got {resp_complaint.status_code}: {resp_complaint.text}"
    complaint_id = resp_complaint.json()["id"]
    assert resp_complaint.json()["status"] == "OPEN"
    assert _BOOKINGS_BY_ID[test_bid]["settlement_status"] == "DISPUTED"
    print(f"[PASS] Complaint created. Settlement status immediately frozen to DISPUTED.")

    # Association Head Isolation:
    # Coop 1 (own society) can view
    current_user_context.clear()
    current_user_context.update({"id": "usr_assoc_01", "role": "cooperative_association_head", "cooperative_id": "coop_north_01"})
    resp_coop1 = client.get("/complaints/cooperative/coop_north_01")
    assert resp_coop1.status_code == 200
    assert resp_coop1.json()["total"] >= 1
    print("[PASS] Association Head 1 accessed disputes for their own cooperative.")

    # Coop 2 cannot access Coop 1's disputes
    current_user_context.clear()
    current_user_context.update({"id": "usr_assoc_02", "role": "cooperative_association_head", "cooperative_id": "coop_south_02"})
    resp_coop2_blocked = client.get("/complaints/cooperative/coop_north_01")
    assert resp_coop2_blocked.status_code == 403
    print("[PASS] Cross-cooperative dispute data access blocked with HTTP 403.")

    # Super Admin resolves dispute
    current_user_context.clear()
    current_user_context.update({"id": "usr_admin_p5", "role": "super_admin"})
    resp_resolve = client.patch(f"/complaints/{complaint_id}/resolve", json={
        "status": "RESOLVED",
        "resolution_notes": "Plumber returned and fixed minor seal leak. Customer satisfied."
    })
    assert resp_resolve.status_code == 200
    assert resp_resolve.json()["status"] == "RESOLVED"
    assert _BOOKINGS_BY_ID[test_bid]["settlement_status"] == "ELIGIBLE"
    print("[PASS] Super Admin resolved dispute. Settlement status restored to ELIGIBLE.")

    # -------------------------------------------------------------
    # 7. Financial Audit Logs Verification
    # -------------------------------------------------------------
    print("\n--- 7. Testing Financial Audit Logs ---")
    actions = [log["action"] for log in _FINANCIAL_AUDIT_LOGS if log["booking_id"] == test_bid]
    assert "PAYMENT_CREATED" in actions
    assert "PAYMENT_VERIFIED" in actions
    assert "OTP_VERIFIED" in actions
    assert "SETTLEMENT_MARKED_ELIGIBLE" in actions
    assert "COMPLAINT_CREATED" in actions
    assert "DISPUTE_RESOLVED" in actions
    print(f"[PASS] All required financial and dispute events recorded in audit log: {set(actions)}")

    print("\n========================================================")
    print("ALL PHASE 5 BACKEND TESTS PASSED SUCCESSFULLY! [100% OK]")
    print("========================================================")

if __name__ == "__main__":
    run_tests()
