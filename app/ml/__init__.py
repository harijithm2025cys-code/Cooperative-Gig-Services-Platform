"""
Machine Learning & Hybrid Intelligence Module.
Phase 8 Production Implementation for Cooperative Gig Services Platform.

Provides:
- ML-assisted worker-job suitability ranking with fair workload distribution
- Service duration prediction for ETA and capacity planning
- Time-series service demand forecasting with low-data statistical baseline fallbacks
- Model versioning registry and persistent model storage
- Explainable hybrid matching score engine with transparent fallback telemetry
"""

from app.ml.model_registry import model_registry
from app.ml.inference import (
    predict_worker_suitability,
    predict_service_duration,
    forecast_service_demand
)

__all__ = [
    "model_registry",
    "predict_worker_suitability",
    "predict_service_duration",
    "forecast_service_demand"
]
