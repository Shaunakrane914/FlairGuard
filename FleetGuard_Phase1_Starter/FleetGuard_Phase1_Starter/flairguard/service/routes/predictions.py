"""Prediction serving endpoint executing verified models."""
from fastapi import APIRouter, HTTPException
from flairguard.service.schemas import PredictRequest, PredictResponse, QualityDetails
from flairguard.service.models_registry import model_registry
from flairguard.quality import TelemetryQualityAuditor, TELEMETRY_CHANNELS, ACTIVE_SENSORS
from flairguard.replay import prefix_features, policy_proposal
from flairguard.evidence import digest
import numpy as np
import pandas as pd

router = APIRouter(prefix="/api/v1", tags=["Prediction Serving"])


@router.post("/predict", response_model=PredictResponse)
def serve_prediction(req: PredictRequest):
    """Predict Remaining Useful Life and diagnostic evidence from raw telemetry."""
    ds = req.dataset.upper()
    bundle = model_registry.get_bundle(ds)
    
    # 1. Quality Audit
    qcfg = bundle.get("quality_config", {"bounds_sigma": 6.0, "stuck_window": 5})
    auditor = TelemetryQualityAuditor(**qcfg, required_channels=TELEMETRY_CHANNELS)
    auditor.nominal_ranges = bundle.get("quality_ranges", {})
    
    combined_telemetry = {}
    for i, s in enumerate(req.settings, start=1):
        combined_telemetry[f"setting_{i}"] = s
    combined_telemetry.update(req.sensors)
    
    quality = auditor.audit_row(req.engine_id, req.cycle, combined_telemetry)
    
    # 2. Build History for Causal Features
    history = list(req.history or [])
    history.append({"cycle": req.cycle, **combined_telemetry})
    history = history[-20:]  # Bound history window
    
    usable = quality.is_valid and len(history) >= bundle.get("min_history", 20)
    prediction = None
    raw_prediction = None
    regime_id = None
    
    if ds == "FD002":
        # Multi-regime model
        regime_model = bundle["models"][bundle["selected"]]
        df_obs = pd.DataFrame(history)
        df_obs["engine_id"] = req.engine_id
        
        preds, diag = regime_model.predict(df_obs)
        raw_prediction = float(preds[-1])
        prediction = float(np.clip(raw_prediction, 0, 125))
        regime_id = int(diag.regime.iloc[-1]) if hasattr(diag, "regime") else None
    else:
        # FD001 feature engineering
        features = prefix_features(history)
        X = pd.DataFrame([features], columns=bundle["features"])
        raw_prediction = float(bundle["model"].predict(X)[0])
        prediction = float(np.clip(raw_prediction, 0, bundle.get("rul_cap", 125)))
        
    # Anomaly scoring
    score = None
    thresh = None
    if "detector" in bundle and bundle["detector"] is not None:
        det = bundle["detector"]
        thresh = float(det.threshold)
        x = np.array([[combined_telemetry[s] for s in ACTIVE_SENSORS if s in combined_telemetry]], dtype=float)
        score = float(det.compute_raw_score(x)[0])
        
    # Synthesize evidence dictionary for policy proposal
    q = bundle.get("interval_q")
    evidence = {
        "engine_id": req.engine_id,
        "cycle": req.cycle,
        "prediction": prediction,
        "raw_prediction": raw_prediction,
        "usable": bool(usable),
        "history_length": len(history),
        "anomaly_score": score,
        "persistence": 0
    }
    
    policy_def = {
        "kind": "point",
        "threshold": 20.0,
        "stale_limit": 10,
        "fixed_age": 140,
        "min_history": 20,
        "lead_time": 5,
        "review_delay": 2,
        "critical_threshold": 15.0
    }
    proposal = policy_proposal(evidence, state={}, policy=policy_def)
    
    return PredictResponse(
        engine_id=req.engine_id,
        cycle=req.cycle,
        dataset=ds,
        model_id=bundle.get("model_id", "unknown"),
        predicted_rul=prediction,
        raw_prediction=raw_prediction,
        usable=usable,
        lower_bound=max(0, prediction - q) if usable and q and prediction else None,
        upper_bound=prediction + q if usable and q and prediction else None,
        regime_id=regime_id,
        anomaly_score=score,
        anomaly_threshold=thresh,
        persistence_count=0,
        quality=QualityDetails(
            is_valid=quality.is_valid,
            quality_code=quality.quality_code,
            details=quality.details
        ),
        recommended_action=proposal.action_type,
        recommended_severity=proposal.severity,
        decision_reason=proposal.reason,
    )
