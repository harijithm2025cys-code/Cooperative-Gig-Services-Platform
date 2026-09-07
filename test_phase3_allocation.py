import sys
import os

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.matching import (
    haversine_distance,
    evaluate_worker_eligibility,
    rank_workers_for_booking,
    allocate_workers_for_booking,
    get_assignments_for_booking,
    get_assignments_for_worker,
    update_assignment_status_in_memory,
    get_audit_logs_for_booking
)

def test_haversine_distance():
    print("\n--- 1. Testing Haversine Distance Calculation ---")
    # Bangalore MG Road (12.9716, 77.5946) to Indiranagar (12.9784, 77.6408) is approx ~5.0 km
    d = haversine_distance(12.9716, 77.5946, 12.9784, 77.6408)
    print(f"Calculated distance: {d} km")
    assert 4.5 <= d <= 5.5, f"Expected distance ~5km, got {d}km"
    print("[PASS] Haversine distance correctly computed.")

def test_hard_eligibility_filters():
    print("\n--- 2. Testing Hard Eligibility Filters (Stage 1) ---")
    
    # 2.1 Correct-skill worker is eligible
    w_correct = {
        "id": "w_elec_1",
        "skill": "Electrician",
        "is_active": True,
        "is_available": True,
        "availability_status": "available",
        "cooperative_id": "coop_blr_01",
        "service_radius_km": 20.0,
        "latitude": 12.9716,
        "longitude": 77.5946,
        "certifications": ["Wireman Grade 1"]
    }
    is_el, reason, dist = evaluate_worker_eligibility(
        worker=w_correct,
        requested_skill="Electrician",
        customer_lat=12.9750,
        customer_lng=77.5980
    )
    assert is_el is True, "Worker with correct skill should be eligible"
    assert reason is None
    print("[PASS] Correct-skill worker is eligible.")

    # 2.2 Wrong-skill worker is rejected (even with 5-star rating)
    w_wrong_skill = dict(w_correct, id="w_plumb_1", skill="Plumber", rating=5.0)
    is_el, reason, _ = evaluate_worker_eligibility(
        worker=w_wrong_skill,
        requested_skill="Electrician"
    )
    assert is_el is False, "Wrong skill worker must be rejected"
    assert reason == "skill_mismatch"
    print("[PASS] Wrong-skill worker is rejected.")

    # 2.3 Unavailable worker is rejected (status != available)
    w_unavailable = dict(w_correct, id="w_unavail", availability_status="working")
    is_el, reason, _ = evaluate_worker_eligibility(
        worker=w_unavailable,
        requested_skill="Electrician"
    )
    assert is_el is False, "Unavailable/working worker must be rejected"
    assert "worker_unavailable" in reason
    print("[PASS] Unavailable worker is rejected.")

    # 2.4 Worker from another cooperative is rejected
    is_el, reason, _ = evaluate_worker_eligibility(
        worker=w_correct,
        requested_skill="Electrician",
        target_cooperative_id="coop_mysore_02"
    )
    assert is_el is False, "Worker from different cooperative must be rejected"
    assert reason == "cooperative_mismatch"
    print("[PASS] Worker from another cooperative is rejected.")

    # 2.5 Certification requirement is enforced
    is_el, reason, _ = evaluate_worker_eligibility(
        worker=w_correct,
        requested_skill="Electrician",
        required_certification="Master High Voltage Specialist"
    )
    assert is_el is False, "Worker lacking required certification must be rejected"
    assert reason == "missing_required_certification"
    print("[PASS] Certification requirement enforced.")

    # 2.6 Worker outside service area is rejected
    is_el, reason, dist = evaluate_worker_eligibility(
        worker=w_correct,
        requested_skill="Electrician",
        customer_lat=13.5000, # ~60 km away
        customer_lng=78.0000
    )
    assert is_el is False, "Worker outside service radius must be rejected"
    assert reason == "outside_service_area"
    print("[PASS] Worker outside service radius rejected.")

    # 2.7 Conflicting bookings cannot double-assign a worker
    is_el, reason, _ = evaluate_worker_eligibility(
        worker=w_correct,
        requested_skill="Electrician",
        active_conflicted_worker_ids={"w_elec_1"}
    )
    assert is_el is False, "Worker with schedule conflict must be rejected"
    assert reason == "booking_schedule_conflict"
    print("[PASS] Overlapping/conflicting worker assignment prevented.")

def test_workload_and_ranking():
    print("\n--- 3. Testing Workload Balancing & Deterministic Ranking ---")
    workers = [
        {
            "id": "w_busy",
            "name": "Busy Worker",
            "skill": "Electrician",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "rating": 4.8,
            "worker_type": "cooperative",
            "jobs_completed_this_month": 15
        },
        {
            "id": "w_fresh",
            "name": "Fresh Worker",
            "skill": "Electrician",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "rating": 4.8,
            "worker_type": "cooperative",
            "jobs_completed_this_month": 1
        }
    ]

    active_counts = {"w_busy": 3, "w_fresh": 0}
    ranked = rank_workers_for_booking(
        requested_skill="Electrician",
        request_lat=12.9716,
        request_lng=77.5946,
        available_workers=workers,
        worker_active_counts=active_counts
    )

    print("Ranked result:", [(r["worker_id"], r["score"]) for r in ranked])
    assert ranked[0]["worker_id"] == "w_fresh", "Worker with lower workload and fewer monthly jobs must rank higher"
    assert ranked[0]["score"] > ranked[1]["score"], "Fresh worker must have higher score"
    print("[PASS] Fair workload distribution and active workload penalty validated.")

def test_multi_worker_allocation_and_records():
    print("\n--- 4. Testing Multi-Worker Automatic Allocation Pipeline ---")
    candidate_workers = [
        {
            "id": "cand_1",
            "name": "Specialist 1",
            "skill": "Carpentry",
            "is_active": True,
            "is_available": True,
            "availability_status": "available",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "rating": 4.9,
            "users": {"name": "Specialist 1", "phone": "9876543210"}
        },
        {
            "id": "cand_2",
            "name": "Specialist 2",
            "skill": "Carpentry",
            "is_active": True,
            "is_available": True,
            "availability_status": "available",
            "latitude": 12.9720,
            "longitude": 77.5950,
            "rating": 4.7,
            "users": {"name": "Specialist 2", "phone": "9876543211"}
        },
        {
            "id": "cand_3",
            "name": "Specialist 3",
            "skill": "Carpentry",
            "is_active": True,
            "is_available": True,
            "availability_status": "available",
            "latitude": 12.9750,
            "longitude": 77.5960,
            "rating": 4.5,
            "users": {"name": "Specialist 3", "phone": "9876543212"}
        }
    ]

    booking_id = "test_b_multi_1001"
    # Customer requests 2 carpenters
    res = allocate_workers_for_booking(
        booking_id=booking_id,
        requested_skill="Carpentry",
        customer_lat=12.9716,
        customer_lng=77.5946,
        required_worker_count=2,
        candidate_workers=candidate_workers
    )

    print("Allocation Status:", res["allocation_status"])
    print("Assigned count:", res["assigned_worker_count"])
    assert res["success"] is True
    assert res["allocation_status"] == "ASSIGNED"
    assert res["required_worker_count"] == 2
    assert res["assigned_worker_count"] == 2
    assert len(res["assigned_workers"]) == 2

    # Verify assignment sequence
    asgns = res["assigned_workers"]
    assert asgns[0]["assignment_sequence"] == 1
    assert asgns[1]["assignment_sequence"] == 2
    assert asgns[0]["status"] == "ASSIGNED"
    print("[PASS] Top 2 workers automatically selected with assignment records.")

    # Verify records stored in memory
    saved_asgns = get_assignments_for_booking(booking_id)
    assert len(saved_asgns) == 2, "Saved assignments should match allocated count"
    
    saved_w1_asgns = get_assignments_for_worker(asgns[0]["worker_id"])
    assert len(saved_w1_asgns) >= 1
    print("[PASS] Assignment records successfully created and queryable.")

    # Verify worker assignment status transition (ASSIGNED -> ACCEPTED)
    asgn_id = asgns[0]["id"]
    updated = update_assignment_status_in_memory(asgn_id, "ACCEPTED")
    assert updated["status"] == "ACCEPTED"
    print("[PASS] Worker assignment acceptance verified.")

def test_no_eligible_worker_failure_state():
    print("\n--- 5. Testing No Eligible Worker Failure State ---")
    # No electricians available
    candidates = [
        {
            "id": "w_plumb_only",
            "name": "Plumber Only",
            "skill": "Plumbing",
            "is_active": True,
            "is_available": True,
            "availability_status": "available",
            "latitude": 12.9716,
            "longitude": 77.5946
        }
    ]

    res = allocate_workers_for_booking(
        booking_id="test_b_no_match",
        requested_skill="HVAC Electrician",
        customer_lat=12.9716,
        customer_lng=77.5946,
        required_worker_count=1,
        candidate_workers=candidates
    )

    print("Allocation Status for unmatched request:", res["allocation_status"])
    assert res["success"] is False
    assert res["allocation_status"] == "NO_ELIGIBLE_WORKER"
    assert res["assigned_worker_count"] == 0
    assert len(res["assigned_workers"]) == 0
    assert "No eligible cooperative workers available" in res["explanation"]
    print("[PASS] Real failure state returned without fabricated assignments.")

    # Verify audit log recorded rejection reason
    audit_logs = get_audit_logs_for_booking("test_b_no_match")
    assert len(audit_logs) == 1
    assert audit_logs[0]["is_eligible"] is False
    assert audit_logs[0]["rejection_reason"] == "skill_mismatch"
    print("[PASS] Matching audit log recorded correct rejection explanation.")

if __name__ == "__main__":
    print("==================================================")
    print("RUNNING PHASE 3 AUTOMATIC ALLOCATION TEST SUITE")
    print("==================================================")
    test_haversine_distance()
    test_hard_eligibility_filters()
    test_workload_and_ranking()
    test_multi_worker_allocation_and_records()
    test_no_eligible_worker_failure_state()
    print("\n==================================================")
    print("ALL PHASE 3 ALLOCATION & MATCHING TESTS PASSED! [OK]")
    print("==================================================")
