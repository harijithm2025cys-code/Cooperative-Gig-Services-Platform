"""
Phase 8 Machine Learning Test Suite:
Validates ML Worker Ranking, Duration Prediction, Demand Forecasting,
Hybrid Matching, Fallback Engine, Multi-Tenant Scoping, and Price Protection.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.dependencies import get_current_user
from app.ml.model_registry import model_registry
from app.ml.train_pipeline import run_training_pipeline
from app.ml.inference import (
    predict_worker_suitability,
    predict_service_duration,
    forecast_service_demand
)
from app.ml.fallback import compute_hybrid_matching_score
from app.services.matching import (
    evaluate_worker_eligibility,
    calculate_worker_score,
    rank_workers_for_booking,
    allocate_workers_for_booking
)

client = TestClient(app)

current_test_user = {"role": "customer", "id": "u_test_1", "cooperative_id": "coop_north_01"}

def mock_get_current_user():
    return current_test_user

@pytest.fixture(autouse=True)
def setup_and_teardown_overrides():
    set_test_user("customer", "u_test_1", "coop_north_01")
    app.dependency_overrides[get_current_user] = mock_get_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)

def set_test_user(role="customer", user_id="u_test_1", coop_id="coop_north_01"):
    current_test_user["role"] = role
    current_test_user["token_role"] = role
    current_test_user["id"] = user_id
    current_test_user["cooperative_id"] = coop_id

# ===========================================================================
# 1. Model Registry & Pipeline Tests
# ===========================================================================
def test_ml_model_registry_loaded():
    """Ensure all three Phase 8 ML models are initialized in the registry."""
    status = model_registry.get_model_status()
    assert status["status"] in ["active", "ONLINE", "baseline_active"]
    assert status["worker_ranking_loaded"] is True
    assert status["duration_model_loaded"] is True
    assert status["demand_model_loaded"] is True
    assert "total_inferences" in status
    assert "fallback_rate_percent" in status

def test_ml_offline_evaluation_metrics():
    """Verify offline metrics are calculated and exposed."""
    metrics = model_registry.get_offline_metrics()
    assert "worker_ranking" in metrics
    assert "duration_prediction" in metrics
    assert "demand_forecasting" in metrics
    assert metrics["worker_ranking"]["top_1_accuracy"] > 0.60
    assert metrics["duration_prediction"]["mae_minutes"] < 40.0

def test_ml_retraining_pipeline_execution():
    """Verify retraining pipeline completes successfully."""
    result = run_training_pipeline()
    assert result["success"] is True
    assert "worker_ranking" in result["metrics"]
    assert "duration_prediction" in result["metrics"]
    assert "demand_forecasting" in result["metrics"]

# ===========================================================================
# 2. Worker Ranking & Hard Constraint Filtering Tests
# ===========================================================================
def test_hard_constraint_filtering_before_ml():
    """Hard constraints must reject ineligible candidates BEFORE ranking."""
    # Worker with wrong skill
    w_wrong_skill = {
        "id": "w_wrong",
        "skill": "Carpentry",
        "is_active": True,
        "availability": True,
        "rating": 5.0,
        "latitude": 12.9716,
        "longitude": 77.5946
    }
    is_elig, reason, _ = evaluate_worker_eligibility(
        worker=w_wrong_skill,
        requested_skill="Plumbing",
        customer_lat=12.9716,
        customer_lng=77.5946
    )
    assert is_elig is False
    assert reason == "skill_mismatch"

    # Inactive worker
    w_inactive = {
        "id": "w_inact",
        "skill": "Plumbing",
        "is_active": False,
        "availability": True
    }
    is_elig2, reason2, _ = evaluate_worker_eligibility(
        worker=w_inactive,
        requested_skill="Plumbing"
    )
    assert is_elig2 is False
    assert reason2 == "worker_inactive"

def test_ml_worker_suitability_inference():
    """Valid worker receives calibrated suitability score (0.0 to 1.0)."""
    worker = {
        "id": "w_valid_1",
        "skill": "Plumbing",
        "rating": 4.9,
        "experience_years": 5,
        "verified_status": True,
        "worker_type": "cooperative"
    }
    booking = {
        "service_name": "Plumbing",
        "is_emergency": False,
        "amount": 350.0
    }
    res = predict_worker_suitability(worker, booking, distance_km=2.5, active_workload=0)
    assert 0.0 <= res["suitability_score"] <= 1.0
    assert res["confidence"] >= 0.40
    assert "features_used" in res

# ===========================================================================
# 3. Transparent Hybrid Matching & Fallback Tests
# ===========================================================================
def test_hybrid_matching_formula():
    """Verify hybrid formula = 0.45 * Rule + 0.35 * (ML * 100) + 0.20 * Fairness."""
    rule_score = 80.0
    ml_suit = 0.90 # 90.0 points
    fairness = 20.0
    expected = (0.45 * 80.0) + (0.35 * 90.0) + (0.20 * 20.0) # 36 + 31.5 + 4 = 71.5
    res = compute_hybrid_matching_score(rule_score, ml_suit, fairness_points=fairness, confidence=0.88)
    assert res["hybrid_score"] == round(expected, 2)
    assert res["fallback_used"] is False

def test_hybrid_matching_fallback_on_low_confidence():
    """When ML confidence is < 0.40, fallback to rule_score directly."""
    rule_score = 75.0
    ml_suit = 0.95
    res = compute_hybrid_matching_score(rule_score, ml_suit, confidence=0.25)
    assert res["fallback_used"] is True
    assert res["hybrid_score"] == rule_score
    assert res["fallback_reason"] == "confidence_below_threshold"

def test_hybrid_matching_forced_fallback():
    """When ML fallback is forced, hybrid score equals rule score."""
    rule_score = 68.0
    res = compute_hybrid_matching_score(rule_score, 0.8, confidence=0.9, fallback_forced=True)
    assert res["fallback_used"] is True
    assert res["hybrid_score"] == 68.0

# ===========================================================================
# 4. Service Duration Prediction & Demand Forecasting Tests
# ===========================================================================
def test_service_duration_prediction():
    """Duration prediction returns estimated minutes within realistic range."""
    booking = {
        "service_name": "Plumbing Pipe Repair",
        "category": "plumbing",
        "is_emergency": False,
        "amount": 400.0
    }
    worker = {"rating": 4.8, "experience_years": 4}
    res = predict_service_duration(booking, worker, distance_km=4.0)
    assert res["predicted_duration_minutes"] > 15.0
    assert len(res["duration_range_minutes"]) == 2
    assert res["duration_range_minutes"][0] < res["duration_range_minutes"][1]

def test_demand_forecasting_7_day():
    """Demand forecast generates 7-day projections with categories and peak hours."""
    forecast = forecast_service_demand(cooperative_id="coop_north_01", district="Chennai North")
    assert forecast["success"] is True
    assert len(forecast["seven_day_projections"]) == 7
    assert "busy_peak_hours" in forecast
    assert len(forecast["workforce_recommendations"]) > 0

# ===========================================================================
# 5. Matching Allocation Engine Integration
# ===========================================================================
def test_allocate_workers_uses_hybrid_and_logs_audit():
    """Verify allocate_workers_for_booking attaches ML scores and records audit logs."""
    candidates = [
        {
            "id": "w_top",
            "name": "Arun Kumar",
            "skill": "Plumbing",
            "rating": 4.9,
            "is_active": True,
            "availability": True,
            "verified_status": True,
            "latitude": 12.9716,
            "longitude": 77.5946,
            "cooperative_id": "coop_north_01",
            "worker_type": "cooperative"
        },
        {
            "id": "w_ineligible",
            "name": "David",
            "skill": "Carpentry",
            "rating": 4.8,
            "is_active": True,
            "availability": True,
            "latitude": 12.9716,
            "longitude": 77.5946
        }
    ]
    res = allocate_workers_for_booking(
        booking_id="bk_ml_test_01",
        requested_skill="Plumbing",
        customer_lat=12.9716,
        customer_lng=77.5946,
        required_worker_count=1,
        candidate_workers=candidates
    )
    assert res["success"] is True
    assert res["assigned_worker_count"] == 1
    asgn = res["assigned_workers"][0]
    assert asgn["worker_id"] == "w_top"
    assert "hybrid_score" in asgn
    assert "rule_score" in asgn
    assert "ml_score" in asgn

    # Check audit logs
    logs = res["audit_logs"]
    assert len(logs) == 2
    top_log = next(l for l in logs if l["worker_id"] == "w_top")
    assert top_log["is_eligible"] is True
    assert "hybrid_score" in top_log
    rej_log = next(l for l in logs if l["worker_id"] == "w_ineligible")
    assert rej_log["is_eligible"] is False
    assert rej_log["rejection_reason"] == "skill_mismatch"

# ===========================================================================
# 6. API Endpoints & Role Authorization Tests
# ===========================================================================
def test_api_worker_ranking_endpoint():
    """POST /ml/worker-ranking returns candidate ranking and breakdown."""
    set_test_user("super_admin")
    payload = {
        "booking": {
            "service_name": "Plumbing",
            "customer_lat": 12.9716,
            "customer_lng": 77.5946,
            "amount": 350.0
        },
        "candidates": [
            {
                "id": "w1",
                "name": "Ravi",
                "skill": "Plumbing",
                "rating": 4.8,
                "latitude": 12.9720,
                "longitude": 77.5950,
                "is_active": True,
                "availability": True
            }
        ]
    }
    resp = client.post("/ml/worker-ranking", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["ranked_candidates"]) == 1
    assert data["ranked_candidates"][0]["hybrid_score"] > 0

def test_api_duration_prediction_endpoint():
    """POST /ml/duration-prediction returns minute estimation."""
    set_test_user("customer")
    payload = {
        "service_name": "Electrical Wiring",
        "category": "electrical",
        "worker_rating": 4.9,
        "experience_years": 4,
        "distance_km": 3.0
    }
    resp = client.post("/ml/duration-prediction", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["prediction"]["predicted_duration_minutes"] > 0

def test_api_demand_forecast_coop_isolation():
    """GET /ml/demand-forecast enforces multi-tenant scoping for Association Heads."""
    # Head of coop_north_01 can access coop_north_01
    set_test_user("cooperative_association_head", coop_id="coop_north_01")
    resp = client.get("/ml/demand-forecast?cooperative_id=coop_north_01")
    assert resp.status_code == 200

    # Head of coop_north_01 CANNOT access coop_south_99
    resp_forbidden = client.get("/ml/demand-forecast?cooperative_id=coop_south_99")
    assert resp_forbidden.status_code == 403

def test_api_retrain_super_admin_only():
    """POST /ml/train restricted to Super Admin only."""
    # Customer rejected
    set_test_user("customer")
    resp_cust = client.post("/ml/train")
    assert resp_cust.status_code == 403

    # Super admin accepted
    set_test_user("super_admin")
    resp_admin = client.post("/ml/train")
    assert resp_admin.status_code == 200
    assert resp_admin.json()["success"] is True

# ===========================================================================
# 7. Price Protection Invariant Check
# ===========================================================================
def test_ml_cannot_alter_tariffs_or_prices():
    """Verify ML operations do NOT modify base prices or billing amounts."""
    booking = {"service_name": "Plumbing", "amount": 450.0}
    w = {"rating": 5.0, "skill": "Plumbing"}
    dur = predict_service_duration(booking, w)
    suit = predict_worker_suitability(w, booking)
    # Ensure booking amount is unchanged and no price field was altered
    assert booking["amount"] == 450.0
    assert "tariff_override" not in dur
    assert "new_fare" not in suit

if __name__ == "__main__":
    pytest.main(["-v", "test_phase8_ml.py"])
