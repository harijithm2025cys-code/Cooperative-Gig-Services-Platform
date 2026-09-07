"""
Unit tests for the Cooperative Gig Platform Matching Engine
"""
from app.services.matching import calculate_worker_score, haversine_distance, rank_workers_for_booking

def test_haversine_distance():
    # Distance between two known coordinates (e.g. Bangalore MG Road to Indiranagar ~ 4.2 km)
    lat1, lon1 = 12.9756, 77.6066
    lat2, lon2 = 12.9784, 77.6408
    dist = haversine_distance(lat1, lon1, lat2, lon2)
    print(f"Haversine distance test: {dist} km")
    assert 3.0 <= dist <= 5.0, f"Unexpected distance: {dist}"

def test_calculate_worker_score():
    # Worker 1: 3.72km distance, 4.8 rating, 1 active booking, cooperative worker
    res = calculate_worker_score(
        worker_skill="Electrician",
        requested_skill="Electrician",
        worker_lat=12.9756,
        worker_lng=77.6066,
        request_lat=12.9784,
        request_lng=77.6408,
        worker_rating=4.8,
        active_bookings_count=1,
        is_cooperative_worker=True
    )
    print(f"Worker 1 Score Breakdown: {res}")
    assert res["rating_points"] == 19.2
    assert res["coop_boost_points"] == 15.0
    assert res["workload_penalty"] == 6.0
    assert res["total_score"] > 50.0

def test_ranking():
    workers = [
        {
            "id": "w1",
            "skill": "Plumber",
            "latitude": 12.97,
            "longitude": 77.59,
            "rating": 4.5,
            "verified_status": True,
            "availability": True,
            "users": {"name": "Ramesh Kumar", "phone": "9876543210"},
            "cooperatives": {"name": "Bengaluru North Labour Society"}
        },
        {
            "id": "w2",
            "skill": "Electrician",
            "latitude": 12.98,
            "longitude": 77.60,
            "rating": 4.9,
            "verified_status": True,
            "availability": True,
            "users": {"name": "Suresh Patel", "phone": "9876543211"},
            "cooperatives": {"name": "Bengaluru Central Labour Society"}
        }
    ]

    # Booking requests Electrician
    ranked = rank_workers_for_booking(
        requested_skill="Electrician",
        request_lat=12.98,
        request_lng=77.60,
        available_workers=workers,
        worker_active_counts={"w2": 0, "w1": 0}
    )

    print("Ranked Workers:")
    for r in ranked:
        print(f" - {r['name']} ({r['skill']}): Total Score={r['score']}, Breakdown={r['breakdown']}")

    # w2 must be ranked first because of skill match
    assert ranked[0]["worker_id"] == "w2"
    assert ranked[0]["score"] > ranked[1]["score"]
    print("All matching tests passed successfully!")

if __name__ == "__main__":
    test_haversine_distance()
    test_calculate_worker_score()
    test_ranking()
