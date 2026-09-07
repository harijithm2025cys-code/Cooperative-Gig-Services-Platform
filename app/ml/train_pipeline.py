"""
End-to-End ML Training Pipeline.
Ingests real platform historical records (with labeled demo data fallback),
trains worker ranking, duration prediction, and demand forecasting models,
evaluates metrics, and updates ModelRegistry.
"""
import os
import csv
import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime, timezone
import numpy as np

from app.ml.model_registry import model_registry
from app.ml.features import (
    WORKER_RANKING_FEATURE_NAMES,
    DURATION_FEATURE_NAMES,
    build_worker_ranking_features,
    build_duration_prediction_features
)
from app.ml.evaluation import (
    evaluate_classification_metrics,
    evaluate_regression_metrics
)
from app.services.analytics_service import (
    get_ml_worker_ranking_dataset,
    get_ml_demand_forecast_dataset
)

logger = logging.getLogger("ml_training_pipeline")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SYNTHETIC_CSV_PATH = os.path.join(DATA_DIR, "synthetic_ml_training_data.csv")

def load_training_dataset() -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, bool]:
    """
    Loads training feature vectors and targets.
    Prioritizes real Phase 7 records; supplements with labeled demo data if samples < 10.
    Returns: (X_ranking, y_ranking, X_duration, y_duration, is_synthetic)
    """
    real_ranking_data = get_ml_worker_ranking_dataset()
    real_records = real_ranking_data.get("records", [])

    X_ranking_list = []
    y_ranking_list = []
    X_duration_list = []
    y_duration_list = []
    is_synthetic = False

    if len(real_records) >= 10:
        for r in real_records:
            feat = [
                1.0,  # skill match
                float(r.get("certification_valid", 1)),
                float(r.get("distance_km", 3.5)),
                float(r.get("worker_rating", 4.8)),
                float(r.get("worker_is_cooperative", 1)),
                float(r.get("worker_monthly_jobs", 0)),
                float(r.get("active_workload", 0)),
                float(r.get("time_of_day_hour", 10)),
                float(r.get("day_of_week", 0)),
                float(r.get("is_emergency", 0)),
                float(r.get("base_fare_inr", 350.0))
            ]
            X_ranking_list.append(feat)
            y_ranking_list.append(int(r.get("target_completed", 1)))

            dur_feat = [
                1.0,  # cat code
                float(r.get("worker_rating", 4.8)),
                3.0,  # exp
                float(r.get("distance_km", 3.5)),
                float(r.get("is_emergency", 0)),
                float(r.get("time_of_day_hour", 10)),
                float(r.get("day_of_week", 0)),
                float(r.get("base_fare_inr", 350.0))
            ]
            X_duration_list.append(dur_feat)
            y_duration_list.append(float(r.get("target_service_duration_mins", 75.0)))
    else:
        # Load labeled synthetic demo dataset for cold-start initialization
        is_synthetic = True
        if os.path.exists(SYNTHETIC_CSV_PATH):
            with open(SYNTHETIC_CSV_PATH, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(line for line in f if not line.startswith("#"))
                for row in reader:
                    feat = [
                        float(row["skill_match_score"]),
                        float(row["certification_valid"]),
                        float(row["distance_km"]),
                        float(row["worker_rating"]),
                        float(row["is_cooperative"]),
                        float(row["monthly_jobs"]),
                        float(row["active_workload"]),
                        float(row["time_of_day_hour"]),
                        float(row["day_of_week"]),
                        float(row["is_emergency"]),
                        float(row["base_fare_inr"])
                    ]
                    X_ranking_list.append(feat)
                    y_ranking_list.append(int(row["target_completed"]))

                    dur_feat = [
                        1.0,
                        float(row["worker_rating"]),
                        3.0,
                        float(row["distance_km"]),
                        float(row["is_emergency"]),
                        float(row["time_of_day_hour"]),
                        float(row["day_of_week"]),
                        float(row["base_fare_inr"])
                    ]
                    X_duration_list.append(dur_feat)
                    y_duration_list.append(float(row["target_duration_mins"]))

    return (
        np.array(X_ranking_list, dtype=float),
        np.array(y_ranking_list, dtype=int),
        np.array(X_duration_list, dtype=float),
        np.array(y_duration_list, dtype=float),
        is_synthetic
    )

def train_all_models() -> Dict[str, Any]:
    """
    Executes full training pipeline, evaluates offline metrics,
    registers models, and saves artifacts to disk.
    """
    X_rank, y_rank, X_dur, y_dur, is_synthetic = load_training_dataset()

    # 1. Train Worker Ranking Model
    model_registry.worker_ranking_model.fit(X_rank, y_rank)
    rank_preds = model_registry.worker_ranking_model.model.predict(
        model_registry.worker_ranking_model.preprocessor.transform(X_rank)
    )
    rank_metrics = evaluate_classification_metrics(y_rank.tolist(), rank_preds.tolist())

    # 2. Train Duration Prediction Model
    model_registry.duration_model.fit(X_dur, y_dur)
    dur_preds = model_registry.duration_model.model.predict(
        model_registry.duration_model.preprocessor.transform(X_dur)
    )
    dur_metrics = evaluate_regression_metrics(y_dur.tolist(), dur_preds.tolist())

    # 3. Train Demand Forecasting Model
    demand_data = get_ml_demand_forecast_dataset()
    demand_metrics = model_registry.demand_model.fit(demand_data.get("records", []))

    # Update Registry Telemetry
    model_registry.last_trained_at = datetime.now(timezone.utc).isoformat()
    model_registry.status = "TRAINED_ACTIVE"
    model_registry.worker_ranking_model.metrics.update(rank_metrics)
    model_registry.duration_model.metrics.update(dur_metrics)

    # Save to disk
    model_registry.save_artifacts()

    return {
        "success": True,
        "trained_at": model_registry.last_trained_at,
        "is_synthetic_dataset": is_synthetic,
        "dataset_source": "DEMO / SYNTHETIC DATASET (Cold-Start Initialized)" if is_synthetic else "REAL PRODUCTION DATABASE",
        "sample_counts": {
            "worker_ranking_samples": len(y_rank),
            "duration_prediction_samples": len(y_dur),
            "demand_timeseries_bins": len(demand_data.get("records", []))
        },
        "models": {
            "worker_ranking": {
                "version": model_registry.worker_ranking_model.version,
                "metrics": rank_metrics
            },
            "duration_prediction": {
                "version": model_registry.duration_model.version,
                "metrics": dur_metrics
            },
            "demand_forecasting": {
                "version": model_registry.demand_model.version,
                "metrics": demand_metrics
            }
        },
        "metrics": {
            "worker_ranking": rank_metrics,
            "duration_prediction": dur_metrics,
            "demand_forecasting": demand_metrics
        }
    }

run_training_pipeline = train_all_models

# Automatically initialize models on import
train_all_models()

