import sys
import os

# Add backend root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.matching import calculate_worker_score, rank_workers_for_booking
from app.models.tariffs import CooperativeTariffCreate, CooperativeTariffResponse
from app.models.bulk_booking import BulkBookingCreateRequest, BulkBookingItemInput

def test_fairness_workload_balancing():
    print("--- 1. Testing Fair Workload Balancing Factor (Fi) ---")
    # Worker A has 0 jobs this month
    score_a = calculate_worker_score(
        worker_skill="Electrician",
        requested_skill="Electrician",
        worker_lat=12.9716,
        worker_lng=77.5946,
        request_lat=12.9716,
        request_lng=77.5946,
        worker_rating=4.8,
        active_bookings_count=0,
        is_cooperative_worker=True,
        monthly_jobs_completed=0
    )
    # Worker B has 10 jobs this month (over-allocated)
    score_b = calculate_worker_score(
        worker_skill="Electrician",
        requested_skill="Electrician",
        worker_lat=12.9716,
        worker_lng=77.5946,
        request_lat=12.9716,
        request_lng=77.5946,
        worker_rating=4.8,
        active_bookings_count=0,
        is_cooperative_worker=True,
        monthly_jobs_completed=10
    )

    print(f"Worker A (0 jobs this month) Fi points: {score_a['fairness_points']}")
    print(f"Worker B (10 jobs this month) Fi points: {score_b['fairness_points']}")
    assert score_a["fairness_points"] == 25.0, "Worker A should receive maximum fairness points (25.0)"
    assert score_b["fairness_points"] == 0.0, "Worker B should receive minimum fairness points (0.0)"
    assert score_a["total_score"] > score_b["total_score"], "Worker A should rank higher to balance workload"
    print("[OK] Fair Workload Balancing Factor (Fi) verified successfully!")

def test_cooperative_priority_boost():
    print("--- 2. Testing Cooperative Member Priority Boost ---")
    score_coop = calculate_worker_score(
        worker_skill="Plumber",
        requested_skill="Plumber",
        worker_lat=12.9716,
        worker_lng=77.5946,
        request_lat=12.9716,
        request_lng=77.5946,
        is_cooperative_worker=True
    )
    score_ind = calculate_worker_score(
        worker_skill="Plumber",
        requested_skill="Plumber",
        worker_lat=12.9716,
        worker_lng=77.5946,
        request_lat=12.9716,
        request_lng=77.5946,
        is_cooperative_worker=False
    )

    print(f"Cooperative worker boost points: {score_coop['coop_boost_points']}")
    print(f"Independent worker boost points: {score_ind['coop_boost_points']}")
    assert score_coop["coop_boost_points"] == 15.0
    assert score_ind["coop_boost_points"] == 0.0
    print("[OK] Cooperative Priority Boost verified successfully!")

def test_ranking_engine_with_roster():
    print("--- 3. Testing Worker Ranking with Multi-Worker Roster ---")
    workers = [
        {
            "id": "w1",
            "skill": "Electrician",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "rating": 4.9,
            "cooperative_id": "coop_1",
            "worker_type": "cooperative",
            "jobs_completed_this_month": 12
        },
        {
            "id": "w2",
            "skill": "Electrician",
            "latitude": 12.9720,
            "longitude": 77.5950,
            "rating": 4.6,
            "cooperative_id": "coop_1",
            "worker_type": "cooperative",
            "jobs_completed_this_month": 1
        }
    ]

    ranked = rank_workers_for_booking(
        requested_skill="Electrician",
        request_lat=12.9716,
        request_lng=77.5946,
        available_workers=workers
    )

    # Worker w2 has fewer jobs (1 vs 12), so Fi elevates w2
    print(f"Top ranked worker: {ranked[0]['worker_id']} with score {ranked[0]['score']}")
    assert ranked[0]["worker_id"] == "w2", "Worker w2 should be prioritized due to fair workload distribution"
    print("[OK] Ranking engine balances workload in favor of under-assigned members!")

def test_phase2_pydantic_schemas():
    print("--- 4. Testing Phase 2 Schemas ---")
    tariff = CooperativeTariffCreate(
        cooperative_id="coop_abc",
        service_name="AC Repair",
        hourly_rate=450.0,
        base_fee=150.0,
        emergency_surcharge_rate=1.30
    )
    assert tariff.hourly_rate == 450.0

    bulk = BulkBookingCreateRequest(
        contact_person="Ramesh Kumar",
        contact_phone="+91 98450 11223",
        service_address="Brigade Millennium, JP Nagar, Bengaluru",
        scheduled_date="2026-09-10",
        scheduled_time="09:00 AM",
        trades=[
            BulkBookingItemInput(trade_name="Cleaners", quantity_requested=5, rate_per_worker=300.0),
            BulkBookingItemInput(trade_name="Electricians", quantity_requested=2, rate_per_worker=400.0)
        ]
    )
    assert len(bulk.trades) == 2
    assert sum(t.quantity_requested for t in bulk.trades) == 7
    print("[OK] Phase 2 Schemas verified successfully!")

if __name__ == "__main__":
    print("\n==========================================")
    print("RUNNING PHASE 2 BACKEND TEST SUITE")
    print("==========================================\n")
    test_fairness_workload_balancing()
    test_cooperative_priority_boost()
    test_ranking_engine_with_roster()
    test_phase2_pydantic_schemas()
    print("\n>>> ALL PHASE 2 BACKEND TESTS PASSED SUCCESSFULLY! <<<\n")
