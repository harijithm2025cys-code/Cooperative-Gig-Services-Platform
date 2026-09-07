"""
Service Duration Prediction Model.
Predicts estimated service duration in minutes for workforce planning, scheduling, and customer ETAs.
"""
from typing import Dict, Any, Optional
import numpy as np
from sklearn.linear_model import Ridge

from app.ml.features import build_duration_prediction_features
from app.ml.preprocessing import MLPreprocessor

class DurationPredictionModel:
    def __init__(self, version: str = "duration-prediction-v1"):
        self.version = version
        self.model = Ridge(alpha=1.0, random_state=42)
        self.preprocessor = MLPreprocessor()
        self.is_trained = False
        self.metrics: Dict[str, Any] = {}

    def fit(self, X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
        X_scaled = self.preprocessor.fit_transform(X)
        self.model.fit(X_scaled, y)
        self.is_trained = True

        preds = self.model.predict(X_scaled)
        mae = float(np.mean(np.abs(preds - y))) if len(y) > 0 else 0.0
        self.metrics = {
            "mae_minutes": round(mae, 2),
            "sample_count": int(len(y)),
            "model_type": "Ridge_Regressor"
        }
        return self.metrics

    def predict_duration(
        self,
        booking: Dict[str, Any],
        worker: Optional[Dict[str, Any]] = None,
        distance_km: float = 3.5
    ) -> Dict[str, Any]:
        """
        Predicts expected duration in minutes.
        """
        features = build_duration_prediction_features(booking, worker, distance_km)
        X_raw = np.array([features])

        if not self.is_trained:
            # Baseline heuristic (e.g. 75 mins normal, 45 mins emergency)
            base_mins = 45.0 if booking.get("is_emergency") else 75.0
            return {
                "predicted_duration_minutes": base_mins,
                "duration_range_minutes": [max(20.0, base_mins - 15), base_mins + 30],
                "confidence": 0.60,
                "model_version": self.version,
                "is_fallback": True
            }

        X_scaled = self.preprocessor.transform(X_raw)
        pred_mins = float(self.model.predict(X_scaled)[0])
        pred_mins = max(20.0, min(300.0, pred_mins))  # Clip between 20 mins and 5 hours

        return {
            "predicted_duration_minutes": round(pred_mins, 1),
            "duration_range_minutes": [round(max(15.0, pred_mins * 0.85), 1), round(pred_mins * 1.25, 1)],
            "confidence": 0.85,
            "model_version": self.version,
            "is_fallback": False
        }
