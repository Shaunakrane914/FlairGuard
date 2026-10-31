"""Anomaly detection suite for FlairGuard AI.

Implements and compares:
1. Statistical Sensor Deviation (Z-score baseline)
2. PCA Reconstruction Error Detection
3. Isolation Forest

Methodology:
- Models fit strictly on nominal early-life reference cycles (cycle <= 20) of TRAINING engines.
- Thresholds calibrated on held-out VALIDATION early-life engines to target a documented False Alarm Rate (FAR).
- Configurable persistence filtering (K consecutive cycles) prevents false alarms from sensor noise.
- Diagnostic perturbation evaluation (synthetic noise/drift) without claiming unverified physical failure labels.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from flairguard.quality import ACTIVE_SENSORS

EARLY_CYCLE_CUTOFF = 20
DEFAULT_TARGET_FAR = 0.05  # Target 5% nominal false alarm rate


class BaseAnomalyDetector(ABC):
    """Abstract base class for all FlairGuard anomaly detectors."""

    def __init__(self, name: str):
        self.name = name
        self.threshold: float = 0.0
        self.target_far: float = DEFAULT_TARGET_FAR
        self.is_fitted: bool = False

    @abstractmethod
    def fit(self, X: np.ndarray):
        """Fit detector strictly on early-life nominal training samples."""
        pass

    @abstractmethod
    def compute_raw_score(self, X: np.ndarray) -> np.ndarray:
        """Compute continuous non-negative anomaly score where higher = more anomalous."""
        pass

    def calibrate_threshold(self, X_val_nominal: np.ndarray, target_far: float = DEFAULT_TARGET_FAR) -> float:
        """Calibrate detection threshold on held-out validation early-life data targeting FAR."""
        if not 0 < target_far < 1 or len(X_val_nominal) == 0:
            raise ValueError("Calibration needs nonempty independent reference data and FAR in (0,1)")
        scores = self.compute_raw_score(X_val_nominal)
        if not np.isfinite(scores).all():
            raise ValueError("Nonfinite calibration scores")
        self.target_far = target_far
        # (1 - target_far) percentile ensures approx target_far fraction exceed threshold on nominal data
        percentile = 100.0 * (1.0 - target_far)
        self.threshold = float(np.percentile(scores, percentile))
        return self.threshold

    def predict_anomalies(self, X: np.ndarray) -> np.ndarray:
        """Return boolean mask indicating whether raw score exceeds calibrated threshold."""
        scores = self.compute_raw_score(X)
        return scores >= self.threshold


class StatisticalDeviationDetector(BaseAnomalyDetector):
    """Baseline sensor deviation detector using mean/std deviation (not robust or a probability)."""

    def __init__(self):
        super().__init__("Statistical_Deviation_ZScore")
        self.mean_: Optional[np.ndarray] = None
        self.std_: Optional[np.ndarray] = None

    def fit(self, X: np.ndarray):
        X = np.asarray(X, dtype=float)
        self.mean_ = np.mean(X, axis=0)
        self.std_ = np.std(X, axis=0)
        self.std_ = np.where(self.std_ < 1e-4, 1.0, self.std_)
        self.is_fitted = True

    def compute_raw_score(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Detector must be fitted before scoring")
        X = np.asarray(X, dtype=float)
        z_scores = np.abs((X - self.mean_) / self.std_)
        # Aggregate score: mean of top 3 most deviating active sensors
        sorted_z = np.sort(z_scores, axis=1)
        return np.mean(sorted_z[:, -3:], axis=1)


class PCAReconstructionDetector(BaseAnomalyDetector):
    """Anomaly detection via PCA subspace reconstruction residual error."""

    def __init__(self, n_components: int = 5):
        super().__init__("PCA_Reconstruction_Error")
        self.n_components = n_components
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=n_components, random_state=42)

    def fit(self, X: np.ndarray):
        X_scaled = self.scaler.fit_transform(X)
        self.pca.fit(X_scaled)
        self.is_fitted = True

    def compute_raw_score(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Detector must be fitted before scoring")
        X_scaled = self.scaler.transform(X)
        X_proj = self.pca.transform(X_scaled)
        X_rec = self.pca.inverse_transform(X_proj)
        # Residual MSE per observation
        reconstruction_error = np.mean((X_scaled - X_rec) ** 2, axis=1)
        return reconstruction_error


class IsolationForestDetector(BaseAnomalyDetector):
    """Isolation Forest anomaly detection on nominal early-life sensor space."""

    def __init__(self, n_estimators: int = 100, random_state: int = 42):
        super().__init__("Isolation_Forest")
        self.scaler = StandardScaler()
        self.model = IsolationForest(
            n_estimators=n_estimators,
            contamination="auto",
            random_state=random_state,
            n_jobs=-1
        )

    def fit(self, X: np.ndarray):
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled)
        self.is_fitted = True

    def compute_raw_score(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Detector must be fitted before scoring")
        X_scaled = self.scaler.transform(X)
        # score_samples returns negative anomaly score (lower is more anomalous)
        # Invert so higher score represents higher anomaly level
        raw_scores = -self.model.score_samples(X_scaled)
        return raw_scores


class PersistenceFilter:
    """Cycle-aware run lengths. Same event cannot count twice; gaps reset runs."""
    def __init__(self, persistence_length=3):
        if persistence_length < 1:
            raise ValueError("Persistence must be positive")
        self.persistence_length = persistence_length
        self._consecutive_counts = {}
        self._last = {}
        self._flags = {}

    def update(self, engine_id, is_anomalous, cycle=None):
        previous = self._last.get(engine_id)
        cycle = cycle if cycle is not None else (previous or 0)+1
        if previous is not None and cycle == previous:
            if bool(is_anomalous) != self._flags[engine_id]:
                raise ValueError("Conflicting anomaly flag at repeated cycle")
            return self._consecutive_counts[engine_id]
        if previous is not None and cycle < previous:
            raise ValueError("Out-of-order persistence update")
        current = self._consecutive_counts.get(engine_id,0) if previous is None or cycle == previous+1 else 0
        self._consecutive_counts[engine_id] = current+1 if is_anomalous else 0
        self._last[engine_id] = cycle
        self._flags[engine_id] = bool(is_anomalous)
        return self._consecutive_counts[engine_id]

    def is_persistent(self, engine_id):
        return self._consecutive_counts.get(engine_id,0) >= self.persistence_length

    def reset_engine(self, engine_id):
        for state in (self._consecutive_counts,self._last,self._flags):
            state.pop(engine_id,None)
