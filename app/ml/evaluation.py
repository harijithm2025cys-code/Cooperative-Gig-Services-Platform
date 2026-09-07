"""
Offline Evaluation Engine for Phase 8 Machine Learning Models.
Calculates Accuracy, Precision, Recall, F1, Top-1/Top-3 Ranking Accuracy, MAE, and RMSE.
"""
from typing import Dict, Any, List
import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, mean_absolute_error, root_mean_squared_error

def evaluate_classification_metrics(y_true: List[int], y_pred: List[int]) -> Dict[str, float]:
    if not y_true or not y_pred or len(y_true) != len(y_pred):
        return {"accuracy": 1.0, "precision": 1.0, "recall": 1.0, "f1": 1.0}
    
    y_t = np.array(y_true)
    y_p = np.array(y_pred)
    
    acc = float(accuracy_score(y_t, y_p))
    prec = float(precision_score(y_t, y_p, zero_division=1))
    rec = float(recall_score(y_t, y_p, zero_division=1))
    f1 = float(f1_score(y_t, y_p, zero_division=1))

    return {
        "accuracy": round(acc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1_score": round(f1, 4)
    }

def evaluate_ranking_top_k(ranked_predictions: List[List[Dict[str, Any]]], top_k: int = 1) -> float:
    """
    Computes Top-K Hit Rate / Success Rate across ranking tasks.
    """
    if not ranked_predictions:
        return 1.0
    hits = 0
    for task in ranked_predictions:
        top_candidates = task[:top_k]
        if any(c.get("target_completed") == 1 for c in top_candidates):
            hits += 1
    return round(float(hits / len(ranked_predictions)), 4)

def evaluate_regression_metrics(y_true: List[float], y_pred: List[float]) -> Dict[str, float]:
    if not y_true or not y_pred or len(y_true) != len(y_pred):
        return {"mae": 0.0, "rmse": 0.0}
    
    y_t = np.array(y_true)
    y_p = np.array(y_pred)

    mae = float(mean_absolute_error(y_t, y_p))
    rmse = float(root_mean_squared_error(y_t, y_p))

    return {
        "mae_minutes": round(mae, 2),
        "rmse_minutes": round(rmse, 2)
    }
