"""
Data Preprocessing & Validation Utilities for Phase 8 ML.
"""
from typing import List, Any, Optional
import numpy as np
from sklearn.preprocessing import StandardScaler

class MLPreprocessor:
    def __init__(self):
        self.scaler = StandardScaler()
        self.is_fitted = False

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        X_clean = np.nan_to_num(X, nan=0.0, posinf=100.0, neginf=-100.0)
        transformed = self.scaler.fit_transform(X_clean)
        self.is_fitted = True
        return transformed

    def transform(self, X: np.ndarray) -> np.ndarray:
        X_clean = np.nan_to_num(X, nan=0.0, posinf=100.0, neginf=-100.0)
        if not self.is_fitted:
            return X_clean
        return self.scaler.transform(X_clean)
