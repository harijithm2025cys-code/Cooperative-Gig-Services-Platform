"""
Transparent Fallback & Safety Net Engine for Phase 8 ML.
Ensures zero dispatch disruption when ML models are offline or under-confident.
"""
from typing import Dict, Any, List

MIN_CONFIDENCE_THRESHOLD = 0.40

def should_trigger_fallback(ml_result: Dict[str, Any]) -> bool:
    """
    Returns True if fallback to rule-based matching must be executed.
    """
    if ml_result.get("is_fallback") is True:
        return True
    conf = float(ml_result.get("confidence", 0.0))
    if conf < MIN_CONFIDENCE_THRESHOLD:
        return True
    return False

def compute_hybrid_matching_score(
    rule_score: float,
    ml_suitability: float,
    fairness_points: float = 15.0,
    confidence: float = 0.85,
    fallback_forced: bool = False
) -> Dict[str, Any]:
    """
    Transparent Hybrid Scoring Algorithm:
    - Rule-based Multi-Factor Score (45%)
    - ML Predicted Suitability Probability * 100 (35%)
    - Cooperative Fair Workload Balance (20%)
    
    If fallback is active:
    - Hybrid score = RuleScore directly
    - Fallback is recorded in audit logs
    """
    if fallback_forced or confidence < MIN_CONFIDENCE_THRESHOLD:
        return {
            "hybrid_score": round(rule_score, 2),
            "rule_score": round(rule_score, 2),
            "ml_score": round(ml_suitability * 100.0, 2),
            "fairness_contribution": round(fairness_points, 2),
            "confidence": round(confidence, 3),
            "fallback_used": True,
            "fallback_reason": "confidence_below_threshold" if confidence < MIN_CONFIDENCE_THRESHOLD else "ml_fallback_forced"
        }

    # Standard Hybrid Formula
    hybrid = (
        (0.45 * rule_score) +
        (0.35 * (ml_suitability * 100.0)) +
        (0.20 * fairness_points)
    )

    return {
        "hybrid_score": round(hybrid, 2),
        "rule_score": round(rule_score, 2),
        "ml_score": round(ml_suitability * 100.0, 2),
        "fairness_contribution": round(fairness_points, 2),
        "confidence": round(confidence, 3),
        "fallback_used": False,
        "fallback_reason": None
    }
