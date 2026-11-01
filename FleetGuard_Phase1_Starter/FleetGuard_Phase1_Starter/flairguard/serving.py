"""Shared observation-only batch inference contract for serving and governance."""
import numpy as np
from .regimes import observations_only
from .features import add_causal_features


def predict_observations(bundle, observations):
    observations_only(observations)
    if "models" in bundle:
        raw, _ = bundle["models"][bundle["selected"]].predict(observations)
    elif "model" in bundle and "features" in bundle:
        frame, _ = add_causal_features(observations)
        # Match the persisted Phase A causal prefix contract.
        raw = bundle["model"].predict(frame[bundle["features"]].round(10))
    else:
        raise ValueError("Unsupported saved-model inference contract")
    raw = np.asarray(raw, dtype=float)
    if raw.shape != (len(observations),) or not np.isfinite(raw).all():
        raise ValueError("Invalid saved-model predictions")
    return raw, np.clip(raw, 0, bundle.get("rul_cap", 125))


def predictor_fit_engines(bundle):
    if "fit_engines" in bundle:
        return sorted(map(int, bundle["fit_engines"]))
    if "models" in bundle:
        return sorted(map(int, bundle["models"][bundle["selected"]].features_.fit_engines_))
    raise ValueError("Champion training population is unknown; evaluation blocked")
