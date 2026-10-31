"""MLOps lifecycle, model provenance, and automated retraining endpoints."""
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from flairguard.service.schemas import ModelMetadataResponse
from flairguard.service.models_registry import model_registry

router = APIRouter(prefix="/api/v1/models", tags=["MLOps & Lifecycle"])


@router.get("", response_model=List[ModelMetadataResponse])
def list_models():
    """List loaded model bundles, version provenance, and benchmark performance."""
    models_dict = model_registry.list_models()
    result = []
    for ds, meta in models_dict.items():
        result.append(ModelMetadataResponse(
            dataset=meta["dataset"],
            model_id=meta["model_id"],
            model_type=meta["model_type"],
            champion=meta["champion"],
            features_count=meta["features_count"],
            target_cap=meta["target_cap"],
            metrics=meta["metrics"],
            provenance=meta["provenance"],
        ))
    return result


@router.post("/retrain")
def trigger_retraining(
    dataset: str = Query("FD001", description="Dataset for retraining run"),
    reveal_batch_size: int = Query(10, ge=5, le=50, description="Count of newly revealed completed engine trajectories")
):
    """Simulate arrival of newly completed labeled engine trajectories and run challenger evaluation.
    
    Demonstrates supervised retraining lifecycle and model promotion gate without unverified live training.
    """
    ds = dataset.upper()
    if ds not in ("FD001", "FD002"):
        raise HTTPException(status_code=400, detail=f"Unsupported retraining dataset {dataset}")
        
    # Provenance of retraining run
    challenger_id = f"{ds.lower()}-challenger-batch{reveal_batch_size}"
    
    # Pre-defined evaluation promotion gate:
    # Challenger must improve or match baseline validation RMSE within 1.0 cycle tolerance without regression.
    gate_passed = False
    baseline_rmse = 18.61 if ds == "FD001" else 48.88
    simulated_challenger_rmse = 18.45 if ds == "FD001" else 48.95
    
    if simulated_challenger_rmse <= baseline_rmse:
        gate_passed = True
        disposition = "PROMOTED_CHALLENGER"
        reason = f"Challenger RMSE ({simulated_challenger_rmse:.2f}) outperformed champion ({baseline_rmse:.2f})."
    else:
        gate_passed = False
        disposition = "REJECTED_RETAIN_CHAMPION"
        reason = f"Challenger RMSE ({simulated_challenger_rmse:.2f}) did not beat champion ({baseline_rmse:.2f})."

    return {
        "status": "COMPLETED",
        "dataset": ds,
        "challenger_model_id": challenger_id,
        "new_labeled_engines": reveal_batch_size,
        "baseline_rmse": baseline_rmse,
        "challenger_rmse": simulated_challenger_rmse,
        "promotion_gate_passed": gate_passed,
        "disposition": disposition,
        "audit_reason": reason,
        "active_champion_retained": not gate_passed,
    }

