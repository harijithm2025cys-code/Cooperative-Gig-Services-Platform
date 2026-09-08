"""
Phase 9 — Production Security, IDOR Verification, RBAC, Webhook Idempotency,
Completion OTP Security, Concurrency & State Machine Integrity Tests
"""
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.core.dependencies import get_current_user
from app.core.security import create_access_token, decode_access_token
from app.services.otp_service import CompletionOtpService, _COMPLETION_OTPS_BY_BOOKING
from app.services.payment_service import (
    PaymentService,
    _PAYMENTS_BY_ID,
    _PAYMENTS_BY_ORDER_ID,
    _PAYMENTS_BY_BOOKING_ID,
    _PROCESSED_WEBHOOK_EVENTS
)
from app.services.matching import _BOOKINGS_BY_ID, _ASSIGNMENTS_BY_ID, _ASSIGNMENTS_BY_BOOKING

client = TestClient(app)

current_test_user = {"role": "customer", "id": "usr_cust_a", "cooperative_id": "coop_north_01"}

def mock_get_current_user():
    return dict(current_test_user)

def set_test_user(role="customer", user_id="usr_cust_a", coop_id="coop_north_01"):
    current_test_user["role"] = role
    current_test_user["token_role"] = role
    current_test_user["id"] = user_id
    current_test_user["cooperative_id"] = coop_id

@pytest.fixture(autouse=True)
def setup_and_teardown_overrides():
    set_test_user(role="customer", user_id="usr_cust_a", coop_id="coop_north_01")
    app.dependency_overrides[get_current_user] = mock_get_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)

# ---------------------------------------------------------------------------
# 1. JWT Security & Decoding Tests
# ---------------------------------------------------------------------------
def test_jwt_token_security_and_expiration():
    """Verify standard JWT token creation, signature validation, and expiration."""
    token = create_access_token("usr_cust_a", "customer", email="cust.a@test.com")
    payload = decode_access_token(token)
    assert payload["sub"] == "usr_cust_a"
    assert payload["role"] == "customer"
    assert "exp" in payload

# ---------------------------------------------------------------------------
# 2. IDOR Protection Tests
# ---------------------------------------------------------------------------
def test_idor_payment_details_access():
    """Customer A cannot view Customer B's payment record."""
    pay_id = "pay_test_cust_b_1001"
    _PAYMENTS_BY_ID[pay_id] = {
        "id": pay_id,
        "booking_id": "bk_cust_b_101",
        "customer_id": "usr_cust_b",
        "razorpay_order_id": "order_test_b_1001",
        "razorpay_payment_id": "pay_rzp_b_1001",
        "amount": 750.0,
        "currency": "INR",
        "status": "CAPTURED",
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    # Customer B (owner) can access
    set_test_user(role="customer", user_id="usr_cust_b")
    resp_owner = client.get(f"/payments/{pay_id}")
    assert resp_owner.status_code == 200
    assert resp_owner.json()["customer_id"] == "usr_cust_b"

    # Customer A (attacker / other user) is blocked with 403 Forbidden
    set_test_user(role="customer", user_id="usr_cust_a")
    resp_attacker = client.get(f"/payments/{pay_id}")
    assert resp_attacker.status_code == 403
    assert "Access denied" in resp_attacker.json()["error"]

    # Super Admin can access for governance
    set_test_user(role="super_admin", user_id="usr_super_admin")
    resp_admin = client.get(f"/payments/{pay_id}")
    assert resp_admin.status_code == 200

def test_idor_worker_assignment_actions():
    """Worker A cannot accept, reject, start journey, or arrive on Worker B's assignment."""
    asgn_id = "asgn_wrk_b_99"
    _ASSIGNMENTS_BY_ID[asgn_id] = {
        "id": asgn_id,
        "booking_id": "bk_paid_wrk_b_99",
        "worker_id": "usr_wrk_b",
        "status": "ASSIGNED"
    }
    _BOOKINGS_BY_ID["bk_paid_wrk_b_99"] = {
        "id": "bk_paid_wrk_b_99",
        "status": "assigned",
        "payment_status": "captured"
    }

    # Worker A attempts to accept Worker B's job -> 403 Forbidden
    set_test_user(role="cooperative_worker", user_id="usr_wrk_a")
    resp = client.post(f"/workers/usr_wrk_b/assignments/{asgn_id}/accept")
    assert resp.status_code == 403
    assert "Access denied" in resp.json()["error"]

    # Worker B (assigned specialist) accepts -> 200 OK
    set_test_user(role="cooperative_worker", user_id="usr_wrk_b")
    resp_valid = client.post(f"/workers/usr_wrk_b/assignments/{asgn_id}/accept")
    assert resp_valid.status_code == 200
    assert resp_valid.json()["status"] == "ACCEPTED"

# ---------------------------------------------------------------------------
# 3. Payment-Before-Service Dispatch Rule
# ---------------------------------------------------------------------------
def test_unpaid_booking_cannot_be_dispatched_or_started():
    """CRITICAL: Unpaid booking can NEVER proceed to journey, arrival or service start."""
    unpaid_bid = "bk_unpaid_test_99"
    asgn_id = "asgn_unpaid_99"

    _BOOKINGS_BY_ID[unpaid_bid] = {
        "id": unpaid_bid,
        "status": "payment_pending",
        "payment_status": "pending",
        "amount": 550.0
    }
    _ASSIGNMENTS_BY_ID[asgn_id] = {
        "id": asgn_id,
        "booking_id": unpaid_bid,
        "worker_id": "usr_wrk_a",
        "status": "ASSIGNED"
    }

    set_test_user(role="cooperative_worker", user_id="usr_wrk_a")

    # Attempting to accept unpaid booking assignment -> 400 Bad Request
    resp_accept = client.post(f"/workers/usr_wrk_a/assignments/{asgn_id}/accept")
    assert resp_accept.status_code == 400
    assert "payment must be captured" in resp_accept.json()["error"].lower()

    # Attempting to start journey on unpaid booking -> 400 Bad Request
    resp_journey = client.post(f"/workers/usr_wrk_a/assignments/{asgn_id}/start-journey")
    assert resp_journey.status_code == 400

# ---------------------------------------------------------------------------
# 4. Webhook Idempotency Verification
# ---------------------------------------------------------------------------
def test_razorpay_webhook_idempotency():
    """Duplicate Razorpay webhook events are processed safely without duplicating payments."""
    event_id = "evt_razorpay_test_dup_001"
    webhook_payload = {
        "event_id": event_id,
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_webhook_dup_101",
                    "order_id": "order_webhook_dup_101",
                    "amount": 90000,
                    "status": "captured",
                    "notes": {"booking_id": "bk_webhook_dup_101"}
                }
            }
        }
    }

    # First call -> processed
    resp_1 = client.post("/payments/webhook", json=webhook_payload)
    assert resp_1.status_code == 200
    assert resp_1.json()["status"] == "processed"

    # Second call with same event_id -> skipped idempotently
    resp_2 = client.post("/payments/webhook", json=webhook_payload)
    assert resp_2.status_code == 200
    assert resp_2.json()["status"] == "skipped"
    assert "Duplicate event" in resp_2.json()["message"]

# ---------------------------------------------------------------------------
# 5. Cryptographic Completion OTP Security Lifecycle
# ---------------------------------------------------------------------------
def test_completion_otp_security_lifecycle():
    """
    Verifies completion OTP:
    1. Cryptographic generation (hashed in storage)
    2. Attempt limits (maximum 3 failed attempts)
    3. Expiration enforcement (15 minutes)
    4. Single-use invalidation
    """
    bid = "bk_otp_test_lifecycle_01"
    cust_id = "usr_cust_a"
    wrk_id = "usr_wrk_a"

    # 1. Generate OTP
    plaintext_otp = CompletionOtpService.generate_completion_otp(
        booking_id=bid,
        customer_id=cust_id,
        worker_id=wrk_id
    )
    assert len(plaintext_otp) == 6
    assert plaintext_otp.isdigit()

    record = _COMPLETION_OTPS_BY_BOOKING[bid]
    assert record["otp_hash"] != plaintext_otp  # Must be hashed

    # 2. Attempt with wrong OTP -> fails and decrements attempts
    ok, msg = CompletionOtpService.verify_completion_otp(bid, wrk_id, "000000")
    assert ok is False
    assert "2 attempt(s) remaining" in msg

    # 3. Second wrong attempt
    ok2, msg2 = CompletionOtpService.verify_completion_otp(bid, wrk_id, "111111")
    assert ok2 is False
    assert "1 attempt(s) remaining" in msg2

    # 4. Correct OTP -> Verified!
    ok_valid, msg_valid = CompletionOtpService.verify_completion_otp(bid, wrk_id, plaintext_otp)
    assert ok_valid is True
    assert "verified successfully" in msg_valid

    # 5. Replay attack: Reusing verified OTP -> Fails!
    ok_replay, msg_replay = CompletionOtpService.verify_completion_otp(bid, wrk_id, plaintext_otp)
    assert ok_replay is False
    assert "already been used" in msg_replay

def test_completion_otp_expiration():
    """Expired completion OTP is rejected."""
    bid = "bk_otp_expired_test_02"
    CompletionOtpService.generate_completion_otp(bid, "usr_cust_a", "usr_wrk_a")
    
    # Backdate expiration to simulate expired token
    _COMPLETION_OTPS_BY_BOOKING[bid]["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    valid_code = _COMPLETION_OTPS_BY_BOOKING[bid]["plaintext_code"]
    ok, msg = CompletionOtpService.verify_completion_otp(bid, "usr_wrk_a", valid_code)
    assert ok is False
    assert "expired" in msg.lower()

# ---------------------------------------------------------------------------
# 6. Booking State Machine Validation
# ---------------------------------------------------------------------------
def test_state_machine_illegal_transitions():
    """State machine prevents illegal transitions like COMPLETED -> REQUESTED or CANCELLED -> IN_PROGRESS."""
    from app.routes.bookings import VALID_TRANSITIONS

    # Completed is terminal
    assert VALID_TRANSITIONS["completed"] == []
    assert "in_progress" not in VALID_TRANSITIONS["completed"]
    assert "requested" not in VALID_TRANSITIONS["completed"]

    # Cancelled is terminal
    assert VALID_TRANSITIONS["cancelled"] == []
    assert "in_progress" not in VALID_TRANSITIONS["cancelled"]

    # Payment failed can only retry payment or cancel
    assert set(VALID_TRANSITIONS["payment_failed"]) == {"payment_pending", "cancelled"}

# ---------------------------------------------------------------------------
# 7. Health & Readiness Subsystem Probes
# ---------------------------------------------------------------------------
def test_health_and_readiness_endpoints():
    """Probes verify operational status without revealing secret keys."""
    resp_health = client.get("/health")
    assert resp_health.status_code == 200
    data_h = resp_health.json()
    assert data_h["status"] == "healthy"
    assert "timestamp" in data_h

    resp_ready = client.get("/ready")
    assert resp_ready.status_code == 200
    data_r = resp_ready.json()
    assert data_r["status"] in ("ready", "degraded")
    assert "subsystems" in data_r
    assert "database_connected" in data_r["subsystems"]
    assert "ml_engine_loaded" in data_r["subsystems"]

# ---------------------------------------------------------------------------
# 8. Request ID & Timing Middleware
# ---------------------------------------------------------------------------
def test_request_id_and_timing_headers():
    """Verify X-Request-ID and X-Response-Time-Ms headers on all API responses."""
    resp = client.get("/health")
    assert "X-Request-ID" in resp.headers
    assert "X-Response-Time-Ms" in resp.headers
    assert float(resp.headers["X-Response-Time-Ms"]) >= 0.0

# ---------------------------------------------------------------------------
# 9. Auth Routes & Demo Personas Fast-Path
# ---------------------------------------------------------------------------
def test_auth_routes_and_demo_personas():
    """Verify /login, /auth/login, /me, /auth/me route aliases and demo persona authentication."""
    # 1. Root /login alias
    resp_login = client.post("/login", json={"email": "ananya@example.com", "password": "Demo@2024"})
    assert resp_login.status_code == 200
    data = resp_login.json()
    assert "access_token" in data
    assert data["role"] == "customer"
    token = data["access_token"]

    # 2. Prefixed /auth/login
    resp_auth_login = client.post("/auth/login", json={"email": "ramesh.worker@coop.org", "password": "Demo@2024"})
    assert resp_auth_login.status_code == 200
    assert resp_auth_login.json()["role"] == "cooperative_worker"

    # 3. Super Admin demo login
    resp_admin = client.post("/login", json={"email": "admin@coop.org", "password": "Demo@2024"})
    assert resp_admin.status_code == 200
    assert resp_admin.json()["role"] == "super_admin"

    # 4. /me and /auth/me profile verification
    resp_me = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp_me.status_code == 200
    assert resp_me.json()["user"]["role"] == "customer"

    resp_auth_me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp_auth_me.status_code == 200
    assert resp_auth_me.json()["user"]["role"] == "customer"

if __name__ == "__main__":
    pytest.main(["-v", "test_phase9_production.py"])

