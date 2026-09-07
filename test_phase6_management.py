import uuid
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import get_current_user
from app.db.in_memory_store import (
    _COOPERATIVES_BY_ID,
    _USERS_BY_ID,
    _WORKERS_BY_ID,
    _SERVICES_BY_ID,
    _ADMIN_AUDIT_LOGS
)
from app.services.matching import _BOOKINGS_BY_ID, _ASSIGNMENTS_BY_ID
from app.routes.complaints import _COMPLAINTS_BY_ID
from app.services.payment_service import _PAYMENTS_BY_ID

client = TestClient(app)

def run_tests():
    print("==================================================")
    print("RUNNING PHASE 6 MANAGEMENT DASHBOARDS TEST SUITE")
    print("==================================================")

    # Global user context override for testing
    user_context = {}

    def override_get_current_user():
        return user_context

    app.dependency_overrides[get_current_user] = override_get_current_user

    # Setup test data
    test_bid_north = f"bk_north_{uuid.uuid4().hex[:6]}"
    _BOOKINGS_BY_ID[test_bid_north] = {
        "id": test_bid_north,
        "cooperative_id": "coop_north_01",
        "customer_id": "usr_cust_01",
        "worker_id": "wrk_1",
        "service_id": "Plumbing & Pipe Repair",
        "status": "in_progress",
        "amount": 450.0,
        "final_amount": 450.0,
        "payment_status": "captured",
        "settlement_status": "PENDING",
        "is_emergency": False,
        "address": "12 Gandhi Road, Chennai",
        "created_at": "2026-09-01T10:00:00Z"
    }

    test_pid_north = f"pay_{uuid.uuid4().hex[:6]}"
    _PAYMENTS_BY_ID[test_pid_north] = {
        "id": test_pid_north,
        "booking_id": test_bid_north,
        "cooperative_id": "coop_north_01",
        "amount": 450.0,
        "currency": "INR",
        "status": "captured",
        "settlement_status": "PENDING",
        "order_id": f"order_{uuid.uuid4().hex[:8]}",
        "razorpay_payment_id": f"pay_{uuid.uuid4().hex[:8]}",
        "created_at": "2026-09-01T10:05:00Z"
    }

    test_cid_north = f"cmp_north_{uuid.uuid4().hex[:6]}"
    _COMPLAINTS_BY_ID[test_cid_north] = {
        "id": test_cid_north,
        "booking_id": test_bid_north,
        "cooperative_id": "coop_north_01",
        "customer_id": "usr_cust_01",
        "category": "Service Delay",
        "description": "Technician arrived 20 minutes behind schedule.",
        "status": "OPEN",
        "resolution_notes": None,
        "resolved_by": None,
        "resolved_at": None,
        "created_at": "2026-09-01T11:00:00Z"
    }

    test_asgn_north = f"asgn_{uuid.uuid4().hex[:6]}"
    _ASSIGNMENTS_BY_ID[test_asgn_north] = {
        "id": test_asgn_north,
        "booking_id": test_bid_north,
        "worker_id": "wrk_1",
        "status": "ACCEPTED",
        "fairness_score": 24.5,
        "distance_km": 1.8,
        "rejection_count": 0,
        "created_at": "2026-09-01T10:02:00Z"
    }

    # -------------------------------------------------------------
    # Test 1: Association Head Dashboard (Own Cooperative)
    # -------------------------------------------------------------
    print("\n--- 1. Testing Association Head Dashboard Access ---")
    user_context.clear()
    user_context.update({
        "id": "usr_head_north_01",
        "name": "Sundaramoorthy Head",
        "email": "head.north@tnlabourcoop.org",
        "role": "cooperative_association_head",
        "cooperative_id": "coop_north_01"
    })

    res = client.get("/association/dashboard")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert data["success"] is True
    assert data["cooperative_id"] == "coop_north_01"
    assert data["metrics"]["total_workers"] >= 2
    assert data["metrics"]["active_jobs"] >= 1
    print("[PASS] Association Head can retrieve dashboard metrics for own cooperative.")

    # -------------------------------------------------------------
    # Test 2: Strict Data Isolation (Cross-Cooperative Block)
    # -------------------------------------------------------------
    print("\n--- 2. Testing Strict Data Isolation ---")
    # Attempting to access coop_south_02 data
    res = client.get("/association/dashboard?cooperative_id=coop_south_02")
    assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"
    print("[PASS] Cross-cooperative dashboard query blocked with HTTP 403 Forbidden.")

    # Attempting to modify worker wrk_3 belonging to coop_south_02
    res = client.patch("/association/workers/wrk_3", json={"is_available": False})
    assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"
    print("[PASS] Cross-cooperative worker modification blocked with HTTP 403 Forbidden.")

    # -------------------------------------------------------------
    # Test 3: Worker Management (Own Society)
    # -------------------------------------------------------------
    print("\n--- 3. Testing Worker Management & Authority Bounds ---")
    # List workers
    res = client.get("/association/workers?skill=Plumbing")
    assert res.status_code == 200
    assert len(res.json()["workers"]) >= 1
    print("[PASS] Association Head filtered own workers by skill.")

    # Update worker availability and phone
    res = client.patch("/association/workers/wrk_1", json={
        "phone": "+91 98450 99999",
        "is_available": False
    })
    assert res.status_code == 200
    assert _WORKERS_BY_ID["wrk_1"]["is_available"] is False
    assert _WORKERS_BY_ID["wrk_1"]["phone"] == "+91 98450 99999"
    print("[PASS] Association Head successfully updated worker contact & availability.")

    # Association Head cannot modify verified_status
    res = client.patch("/association/workers/wrk_1", json={"verified_status": False})
    assert res.status_code == 403, f"Expected 403, got {res.status_code}"
    print("[PASS] Association Head cannot alter verification status (HTTP 403).")

    # Reset worker availability
    _WORKERS_BY_ID["wrk_1"]["is_available"] = True

    # -------------------------------------------------------------
    # Test 4: Service Management (Tariff Matrix)
    # -------------------------------------------------------------
    print("\n--- 4. Testing Service Catalog Management ---")
    # Create new service
    new_service_payload = {
        "name": "Cooperative Solar Panel Cleaning",
        "category": "Eco-Cleaning",
        "description": "Standardized eco-friendly solar array maintenance.",
        "base_price": 500.0,
        "unit": "job",
        "is_active": True
    }
    res = client.post("/association/services", json=new_service_payload)
    assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
    created_srv = res.json()["service"]
    srv_id = created_srv["id"]
    assert created_srv["cooperative_id"] == "coop_north_01"
    print("[PASS] Association Head created new cooperative-approved service.")

    # Update service price
    res = client.patch(f"/association/services/{srv_id}", json={"base_price": 550.0})
    assert res.status_code == 200
    assert res.json()["service"]["base_price"] == 550.0
    print("[PASS] Cooperative service tariff successfully updated.")

    # -------------------------------------------------------------
    # Test 5: Operations & Allocation Inspection
    # -------------------------------------------------------------
    print("\n--- 5. Testing Active Operations & Allocation Transparency ---")
    res = client.get("/association/operations")
    assert res.status_code == 200
    ops = res.json()["operations"]
    assert len(ops) >= 1
    assert any(op["booking_id"] == test_bid_north for op in ops)
    print(f"[PASS] Retrieved active operations feed with live status and ETAs ({len(ops)} active).")

    res = client.get("/association/assignments")
    assert res.status_code == 200
    asgns = res.json()["assignments"]
    assert len(asgns) >= 1
    print(f"[PASS] Allocation transparency log inspected ({len(asgns)} records).")

    # -------------------------------------------------------------
    # Test 6: Dispute Inquiry (Own Society)
    # -------------------------------------------------------------
    print("\n--- 6. Testing Dispute Inquiry & Authority Bounds ---")
    res = client.get("/association/disputes")
    assert res.status_code == 200
    disputes = res.json()["disputes"]
    assert any(d["id"] == test_cid_north for d in disputes)
    print("[PASS] Scoped disputes list retrieved for cooperative.")

    # Review dispute with notes
    res = client.patch(f"/association/disputes/{test_cid_north}", json={
        "status": "UNDER_REVIEW",
        "resolution_notes": "Contacted technician and customer to review arrival log."
    })
    assert res.status_code == 200
    assert _COMPLAINTS_BY_ID[test_cid_north]["status"] == "UNDER_REVIEW"
    print("[PASS] Association Head logged dispute inquiry notes and updated status.")

    # Association Head cannot issue REFUNDED
    res = client.patch(f"/association/disputes/{test_cid_north}", json={"status": "REFUNDED"})
    assert res.status_code == 403
    print("[PASS] Association Head cannot authorize financial refund (HTTP 403).")

    # -------------------------------------------------------------
    # Test 7: Payments Visibility
    # -------------------------------------------------------------
    print("\n--- 7. Testing Financial Visibility (Safe PII/PCI) ---")
    res = client.get("/association/payments")
    assert res.status_code == 200
    pay_data = res.json()
    assert pay_data["summary"]["total_captured_revenue"] >= 450.0
    for tx in pay_data["transactions"]:
        assert "card" not in tx
        assert "cvv" not in tx
        assert "upi_pin" not in tx
    print("[PASS] Cooperative financial totals and safe transactions retrieved.")

    # -------------------------------------------------------------
    # Test 8: Real Database Aggregations (Analytics)
    # -------------------------------------------------------------
    print("\n--- 8. Testing Operational Analytics Aggregations ---")
    res = client.get("/association/analytics")
    assert res.status_code == 200
    aggr = res.json()["aggregations"]
    assert "demand_by_service" in aggr
    assert "worker_utilization_percent" in aggr
    assert "completion_rate_percent" in aggr
    print(f"[PASS] Real database aggregations computed: {len(aggr['demand_by_service'])} service categories.")

    # -------------------------------------------------------------
    # Test 9: Super Admin Platform Oversight & Federation Tree
    # -------------------------------------------------------------
    print("\n--- 9. Testing Super Admin Platform Oversight ---")
    user_context.clear()
    user_context.update({
        "id": "usr_super_admin_01",
        "name": "Super Admin",
        "email": "superadmin@coopservices.gov.in",
        "role": "super_admin",
        "cooperative_id": None
    })

    # Platform dashboard
    res = client.get("/admin/dashboard")
    assert res.status_code == 200
    p_data = res.json()
    assert p_data["metrics"]["total_cooperatives"] >= 3
    assert p_data["metrics"]["total_workers"] >= 4
    print("[PASS] Super Admin platform-wide dashboard verified.")

    # Federation hierarchy tree
    res = client.get("/admin/federation-tree")
    assert res.status_code == 200
    tree = res.json()["federation"]
    assert tree["total_affiliated_societies"] >= 3
    print(f"[PASS] Full federation tree verified ({tree['total_affiliated_societies']} societies, {tree['independent_workers_count']} independent workers).")

    # User Directory & Role Management
    res = client.get("/admin/users")
    assert res.status_code == 200
    assert res.json()["total"] >= 5
    print(f"[PASS] 5-Role user directory retrieved ({res.json()['total']} users).")

    # Super Admin cannot demote self
    res = client.patch("/admin/users/usr_super_admin_01/role", json={"role": "customer"})
    assert res.status_code == 400
    print("[PASS] Self-demotion by Super Admin prohibited with HTTP 400.")

    # Super Admin updates another user's role
    res = client.patch("/admin/users/usr_cust_02/role", json={"role": "independent_worker"})
    assert res.status_code == 200
    assert _USERS_BY_ID["usr_cust_02"]["role"] == "independent_worker"
    print("[PASS] Super Admin updated user role to independent_worker.")

    # Cooperative Registration
    new_coop_payload = {
        "name": "Madurai Heritage Artisans Cooperative",
        "district": "Madurai",
        "state": "Tamil Nadu",
        "address": "10 Palace Road, Madurai",
        "registration_number": "TN-LCS-2024-9988",
        "contact_email": "madurai@tnlabourcoop.org",
        "contact_phone": "+91 452 233 4455",
        "verified": True
    }
    res = client.post("/admin/cooperatives", json=new_coop_payload)
    assert res.status_code == 201
    assert res.json()["cooperative"]["district"] == "Madurai"
    print("[PASS] Super Admin registered new cooperative society.")

    # Dispute Resolution with Refund Authorization
    res = client.post(f"/admin/disputes/{test_cid_north}/resolve", json={
        "status": "RESOLVED",
        "resolution_notes": "Super Admin authorized full refund due to certified service delay.",
        "refund_approved": True
    })
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["refund_processed"] is True
    assert _COMPLAINTS_BY_ID[test_cid_north]["status"] == "REFUNDED"
    assert _BOOKINGS_BY_ID[test_bid_north]["settlement_status"] == "REFUNDED"
    assert _PAYMENTS_BY_ID[test_pid_north]["status"] == "refunded"
    print("[PASS] Super Admin resolved dispute with full refund and settlement freeze unfreeze.")

    # Audit Logs
    res = client.get("/admin/audit-logs")
    assert res.status_code == 200
    assert len(res.json()["audit_logs"]) >= 1
    print(f"[PASS] System-wide administrative audit logs verified ({len(res.json()['audit_logs'])} entries).")

    # -------------------------------------------------------------
    # Test 10: Unauthorized Roles Blocked (Customer & Worker)
    # -------------------------------------------------------------
    print("\n--- 10. Testing Role Enforcement for Non-Admin Roles ---")
    # Customer
    user_context.clear()
    user_context.update({"id": "usr_cust_01", "role": "customer", "email": "customer@test.com"})
    res = client.get("/association/dashboard")
    assert res.status_code == 403, f"Expected 403 for Customer on /association/dashboard, got {res.status_code}"
    res = client.get("/admin/dashboard")
    assert res.status_code == 403, f"Expected 403 for Customer on /admin/dashboard, got {res.status_code}"
    print("[PASS] Customer blocked from /association and /admin endpoints (HTTP 403).")

    # Cooperative Worker
    user_context.clear()
    user_context.update({"id": "usr_wrk_1", "role": "cooperative_worker", "email": "worker@test.com"})
    res = client.get("/association/dashboard")
    assert res.status_code == 403, f"Expected 403 for Worker on /association/dashboard, got {res.status_code}"
    res = client.get("/admin/dashboard")
    assert res.status_code == 403, f"Expected 403 for Worker on /admin/dashboard, got {res.status_code}"
    print("[PASS] Cooperative Worker blocked from /association and /admin endpoints (HTTP 403).")

    print("\n==================================================")
    print("ALL 10 PHASE 6 BACKEND MANAGEMENT TESTS PASSED! [100% OK]")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
