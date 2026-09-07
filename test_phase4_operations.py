import sys
import os

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.event_service import event_service
from app.services.matching import (
    haversine_distance,
    reallocate_rejected_assignment,
    match_emergency_booking,
    record_allocation_assignments,
    get_assignments_for_booking,
)
from app.routes.bookings import VALID_TRANSITIONS

def test_notification_and_event_service():
    print("\n--- 1. Testing In-App Notifications & Event Bus ---")
    user_id = "test_user_hh_01"
    
    # Clean previous test entries
    event_service._in_memory_notifications[user_id] = []
    
    # 1. Create notifications
    n1 = event_service.create_notification(
        user_id=user_id,
        title="Worker Assigned",
        message="Specialist assigned to your booking #B101.",
        type="BOOKING_ASSIGNED",
        reference_id="B101"
    )
    n2 = event_service.create_notification(
        user_id=user_id,
        title="Worker En Route",
        message="Specialist is en route to your home (~12 mins).",
        type="WORKER_EN_ROUTE",
        reference_id="B101"
    )
    assert n1["is_read"] is False
    assert n2["is_read"] is False
    
    # 2. Check unread count
    unread_count = event_service.get_unread_count(user_id)
    assert unread_count == 2, f"Expected 2 unread, got {unread_count}"
    print("[PASS] Unread count correctly tracked (2).")
    
    # 3. Mark one notification as read
    marked = event_service.mark_as_read(n1["id"], user_id)
    assert marked is True
    assert event_service.get_unread_count(user_id) == 1
    print("[PASS] Individual notification marked as read, unread count decremented.")
    
    # 4. Mark all as read
    count_marked = event_service.mark_all_as_read(user_id)
    assert count_marked >= 1
    assert event_service.get_unread_count(user_id) == 0
    print("[PASS] Mark-all-read clears unread count to 0.")
    
    # 5. Real-time event logging
    evt = event_service.publish_event(
        event_type="WORKER_ACCEPTED",
        booking_id="B101",
        actor_id="worker_01",
        actor_role="worker",
        title="Specialist Confirmed",
        description="Electrician confirmed appointment."
    )
    logs = event_service.get_booking_events("B101")
    assert len(logs) >= 1
    assert logs[0]["event_type"] == "WORKER_ACCEPTED"
    print("[PASS] Realtime event published and queryable.")

def test_state_machine_transitions():
    print("\n--- 2. Testing Strict Booking State Machine ---")
    
    # Check legal transitions
    assert "accepted" in VALID_TRANSITIONS["requested"]
    assert "worker_enroute" in VALID_TRANSITIONS["accepted"]
    assert "arrived" in VALID_TRANSITIONS["worker_enroute"]
    assert "in_progress" in VALID_TRANSITIONS["arrived"]
    assert "completed" in VALID_TRANSITIONS["in_progress"]
    print("[PASS] Standard linear transition sequence verified.")
    
    # Check illegal transitions
    illegal_transitions = [
        ("requested", "completed"),
        ("accepted", "completed"),
        ("worker_enroute", "completed"),
        ("completed", "in_progress"),
        ("cancelled", "accepted"),
    ]
    for from_state, to_state in illegal_transitions:
        allowed = VALID_TRANSITIONS.get(from_state, [])
        assert to_state not in allowed, f"Illegal jump from {from_state} to {to_state} must NOT be allowed!"
    print("[PASS] Invalid lifecycle jumps correctly rejected by VALID_TRANSITIONS.")

def test_customer_cancellation_rules():
    print("\n--- 3. Testing Cancellation Rules ---")
    cancellable_states = ["requested", "matching", "assigned", "accepted", "worker_enroute", "arrived"]
    non_cancellable_states = ["in_progress", "verified_checkin", "verified_checkout", "completed"]
    
    for s in cancellable_states:
        allowed = "cancelled" in VALID_TRANSITIONS.get(s, [])
        assert allowed, f"Status '{s}' should allow customer cancellation"
    print(f"[PASS] Pre-service states {cancellable_states} permit cancellation.")
    
    for s in non_cancellable_states:
        allowed = "cancelled" in VALID_TRANSITIONS.get(s, [])
        assert not allowed, f"Status '{s}' must NOT allow cancellation once work is active or completed"
    print(f"[PASS] In-progress & completed states {non_cancellable_states} strictly prohibit cancellation.")

def test_worker_reallocation_on_rejection():
    print("\n--- 4. Testing Auto-Reallocation on Worker Rejection ---")
    booking_id = "test_booking_realloc_01"
    
    # Candidate pool of 3 electricians at varying distances
    candidates = [
        {
            "id": "w_elec_close",
            "name": "Ramesh Electrician",
            "skill": "Electrician",
            "is_active": True,
            "is_available": True,
            "availability_status": "available",
            "rating": 4.8,
            "latitude": 12.9720,
            "longitude": 77.5950,
            "service_radius_km": 15.0,
            "experience_years": 4,
            "worker_type": "cooperative",
            "cooperative_id": "coop_01"
        },
        {
            "id": "w_elec_second",
            "name": "Suresh Electrician",
            "skill": "Electrician",
            "is_active": True,
            "is_available": True,
            "availability_status": "available",
            "rating": 4.5,
            "latitude": 12.9760,
            "longitude": 77.6000,
            "service_radius_km": 15.0,
            "experience_years": 3,
            "worker_type": "cooperative",
            "cooperative_id": "coop_01"
        },
        {
            "id": "w_elec_third",
            "name": "Mahesh Electrician",
            "skill": "Electrician",
            "is_active": True,
            "is_available": True,
            "availability_status": "available",
            "rating": 4.2,
            "latitude": 12.9800,
            "longitude": 77.6100,
            "service_radius_km": 15.0,
            "experience_years": 2,
            "worker_type": "cooperative",
            "cooperative_id": "coop_01"
        }
    ]
    
    # Initially assign w_elec_close
    initial_assignment = {
        "id": "asgn_init_01",
        "booking_id": booking_id,
        "worker_id": "w_elec_close",
        "status": "ASSIGNED",
        "assignment_sequence": 1
    }
    record_allocation_assignments(booking_id, [initial_assignment], [])
    
    # Worker declines -> trigger reallocation
    realloc_res = reallocate_rejected_assignment(
        booking_id=booking_id,
        rejected_worker_id="w_elec_close",
        candidate_workers=candidates,
        requested_skill="Electrician",
        customer_lat=12.9716,
        customer_lng=77.5946
    )
    
    assert realloc_res["reallocated"] is True, "Reallocation should succeed"
    new_asgn = realloc_res["new_assignment"]
    assert new_asgn["worker_id"] == "w_elec_second", f"Expected w_elec_second, got {new_asgn['worker_id']}"
    assert new_asgn["status"] == "ASSIGNED"
    print(f"[PASS] Reallocation successful: replaced rejected worker 'w_elec_close' with next-best candidate '{new_asgn['worker_name']}'.")
    
    # Now second worker also declines -> should allocate third candidate
    realloc_res_2 = reallocate_rejected_assignment(
        booking_id=booking_id,
        rejected_worker_id="w_elec_second",
        candidate_workers=candidates,
        requested_skill="Electrician",
        customer_lat=12.9716,
        customer_lng=77.5946
    )
    assert realloc_res_2["reallocated"] is True
    assert realloc_res_2["new_assignment"]["worker_id"] == "w_elec_third"
    print(f"[PASS] Chained reallocation successful: allocated '{realloc_res_2['new_assignment']['worker_name']}'.")

def test_location_and_eta_calculation():
    print("\n--- 5. Testing GPS Distance & Approximate ETA Calculation ---")
    # Worker at (12.9784, 77.6408), Customer at (12.9716, 77.5946) -> ~5.0 km
    w_lat, w_lng = 12.9784, 77.6408
    c_lat, c_lng = 12.9716, 77.5946
    dist_km = haversine_distance(w_lat, w_lng, c_lat, c_lng)
    
    # Speed = 25 km/h
    hours = dist_km / 25.0
    eta_mins = max(1, round(hours * 60))
    eta_str = f"~{eta_mins} mins (approx. {dist_km:.1f} km @ 25 km/h)"
    
    print(f"Distance: {dist_km} km, Calculated ETA: {eta_mins} minutes -> {eta_str}")
    assert 10 <= eta_mins <= 14, f"Expected ETA between 10-14 minutes, got {eta_mins}"
    assert "25 km/h" in eta_str
    print("[PASS] Realistic approximate ETA computed without artificial fake simulation.")

def test_emergency_booking_dispatch():
    print("\n--- 6. Testing Emergency On-Demand Priority Dispatch ---")
    candidates = [
        {
            "id": "w_far_high_rated",
            "name": "Far Worker",
            "skill": "Electrician",
            "is_active": True,
            "is_available": True,
            "availability_status": "available",
            "rating": 5.0,
            "latitude": 13.0500, # ~9 km away
            "longitude": 77.5946,
            "service_radius_km": 20.0,
            "worker_type": "cooperative"
        },
        {
            "id": "w_near_regular",
            "name": "Near Worker",
            "skill": "Electrician",
            "is_active": True,
            "is_available": True,
            "availability_status": "available",
            "rating": 4.4,
            "latitude": 12.9730, # ~0.2 km away
            "longitude": 77.5950,
            "service_radius_km": 15.0,
            "worker_type": "cooperative"
        }
    ]
    
    # In emergency mode, proximity is heavily prioritized (50% weight)
    res = match_emergency_booking(
        booking_id="emg_b_01",
        requested_skill="Electrician",
        customer_lat=12.9716,
        customer_lng=77.5946,
        candidate_workers=candidates,
        required_worker_count=1
    )
    
    assert res["success"] is True
    assigned = res["assigned_workers"]
    assert len(assigned) == 1
    # Closest worker should win due to emergency proximity weighting
    assert assigned[0]["worker_id"] == "w_near_regular", f"Expected w_near_regular, got {assigned[0]['worker_id']}"
    print(f"[PASS] Emergency booking prioritized closest worker '{assigned[0]['worker_name']}' over distant higher-rated worker.")

if __name__ == "__main__":
    test_notification_and_event_service()
    test_state_machine_transitions()
    test_customer_cancellation_rules()
    test_worker_reallocation_on_rejection()
    test_location_and_eta_calculation()
    test_emergency_booking_dispatch()
    print("\n========================================================")
    print("ALL PHASE 4 BACKEND OPERATIONS TESTS PASSED SUCCESSFULLY!")
    print("========================================================\n")
