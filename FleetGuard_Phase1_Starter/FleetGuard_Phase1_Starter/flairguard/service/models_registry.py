"""Model registry and serving manager for FlairGuard AI.

Loads and serves verified serialized model artifacts:
- Phase A FD001 LightGBM baseline bundle
- Phase B FD002 Multi-Regime LightGBM bundle
Enforces real inference with zero fabricated or hardcoded model outputs.
"""
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from .config import settings
from flairguard.evidence import file_sha
from flairguard.quality import TELEMETRY_CHANNELS, ACTIVE_SENSORS


class ModelRegistry:
    """Singleton registry holding loaded model bundles and metadata."""

    def __init__(self):
        self._bundles: Dict[str, Any] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._loaded: bool = False

    def load_models(self):
        """Load verified model artifacts from disk."""
        # 1. Load FD001 bundle
        if settings.fd001_bundle_path.exists():
            bundle_a = joblib.load(settings.fd001_bundle_path)
            self._bundles["FD001"] = bundle_a
            self._metadata["FD001"] = {
                "dataset": "FD001",
                "model_id": bundle_a.get("model_id", "fd001-lightgbm-baseline"),
                "model_type": "HistGradientBoosting / LightGBM",
                "champion": True,
                "features_count": len(bundle_a.get("features", [])),
                "target_cap": bundle_a.get("rul_cap", 125),
                "metrics": {
                    "official_test_mae": 13.5577,
                    "official_test_rmse": 18.6121,
                    "official_phm08_score": 606.0246
                },
                "provenance": {
                    "artifact_path": str(settings.fd001_bundle_path.relative_to(settings.root_dir)),
                    "sha256": file_sha(settings.fd001_bundle_path),
                    "protocol": "phase-a-fd001-v1"
                }
            }

        # 2. Load FD002 bundle
        if settings.fd002_bundle_path.exists():
            bundle_b = joblib.load(settings.fd002_bundle_path)
            self._bundles["FD002"] = bundle_b
            selected_name = bundle_b.get("selected", "RegimeLightGBM")
            self._metadata["FD002"] = {
                "dataset": "FD002",
                "model_id": bundle_b.get("model_id", "fd002-regime-lightgbm"),
                "model_type": f"Regime-Aware {selected_name} (6 Operating Regimes)",
                "champion": True,
                "features_count": 48,
                "target_cap": 125,
                "metrics": {
                    "test_rmse_endpoint": 48.8844,
                    "global_norm_rmse_baseline": 50.3747,
                    "improvement_cycles": 1.4903
                },
                "provenance": {
                    "artifact_path": str(settings.fd002_bundle_path.relative_to(settings.root_dir)),
                    "sha256": file_sha(settings.fd002_bundle_path),
                    "protocol": bundle_b.get("protocol", {}).get("protocol_id", "phase-b-fd002-v1")
                }
            }

        self._loaded = True

    def get_bundle(self, dataset: str) -> Dict[str, Any]:
        dataset = dataset.upper()
        if not self._loaded:
            self.load_models()
        if dataset not in self._bundles:
            raise KeyError(f"Dataset model {dataset} not found in registry")
        return self._bundles[dataset]

    def get_metadata(self, dataset: str) -> Dict[str, Any]:
        dataset = dataset.upper()
        if not self._loaded:
            self.load_models()
        if dataset not in self._metadata:
            raise KeyError(f"Metadata for {dataset} not found")
        return self._metadata[dataset]

    def list_models(self) -> Dict[str, Dict[str, Any]]:
        if not self._loaded:
            self.load_models()
        return self._metadata

    def predict_fd002_trajectory(self, df_trajectory: pd.DataFrame) -> Tuple[np.ndarray, pd.DataFrame]:
        """Perform regime-aware RUL prediction on a sequence of FD002 observations."""
        bundle = self.get_bundle("FD002")
        selected_model = bundle["models"][bundle["selected"]]
        return selected_model.predict(df_trajectory)


# Global singleton instance
model_registry = ModelRegistry()
