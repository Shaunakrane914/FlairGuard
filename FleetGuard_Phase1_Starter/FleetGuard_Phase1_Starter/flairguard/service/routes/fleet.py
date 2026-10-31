"""Fleet management and engine discovery endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException
from flairguard.service.schemas import DatasetInfo, EngineSummary, FleetSummary
from flairguard.service.config import settings
from flairguard.service.models_registry import model_registry
from flairguard.data import load_subset
from flairguard.storage import WorkOrderStore

router = APIRouter(prefix="/api/v1/fleet", tags=["Fleet Management"])

DATASET_METADATA = {
    "FD001": DatasetInfo(
        id="FD001",
        name="NASA C-MAPSS FD001 (Single Regime)",
        operating_conditions=1,
        fault_modes=1,
        train_engines=100,
        test_engines=100,
        total_records=33727,
        description="Single operating condition (Sea Level) with high-pressure compressor degradation."
    ),
    "FD002": DatasetInfo(
        id="FD002",
        name="NASA C-MAPSS FD002 (Multi-Regime)",
        operating_conditions=6,
        fault_modes=1,
        train_engines=260,
        test_engines=259,
        total_records=87455,
        description="Six complex operating conditions (varying altitude, Mach, throttle) with HPC degradation."
    )
}


@router.get("/datasets", response_model=List[DatasetInfo])
def list_datasets():
    """List available C-MAPSS fleet datasets and characteristics."""
    return list(DATASET_METADATA.values())


@router.get("/engines", response_model=List[EngineSummary])
def list_engines(
    dataset: str = Query("FD002", description="Dataset identifier (FD001 or FD002)"),
    split: str = Query("test", description="Data split (train or test)"),
    limit: int = Query(50, ge=1, le=300),
):
    """List engines for a dataset, reporting total cycles and current operational status."""
    ds = dataset.upper()
    if ds not in DATASET_METADATA:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset} not supported")
        
    try:
        train_df, test_df, _ = load_subset(settings.data_dir, ds)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read dataset: {str(e)}")
        
    target_df = train_df if split == "train" else test_df
    engine_ids = target_df.engine_id.unique()[:limit]
    
    store = WorkOrderStore(settings.db_path, namespace="default")
    summaries = []
    
    for eng_id in engine_ids:
        eng_rows = target_df[target_df.engine_id == eng_id]
        total_cyc = int(eng_rows.cycle.max())
        
        # Check if an active work order exists in the store
        active_wo = store.get_active_work_order(int(eng_id), asset_id=str(eng_id))
        
        status = "NOMINAL"
        active_wo_id = None
        if active_wo:
            status = active_wo.get("severity", "MEDIUM")
            active_wo_id = active_wo.get("work_order_id")
            
        summaries.append(EngineSummary(
            engine_id=int(eng_id),
            dataset=ds,
            total_cycles=total_cyc,
            last_observed_cycle=total_cyc,
            current_status=status,
            active_work_order_id=active_wo_id,
        ))
        
    return summaries


@router.get("/summary", response_model=FleetSummary)
def get_fleet_summary(
    dataset: str = Query("FD002", description="Dataset identifier")
):
    """Aggregate fleet KPIs across all monitored engines in the selected dataset."""
    ds = dataset.upper()
    if ds not in DATASET_METADATA:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset} not supported")
        
    meta = DATASET_METADATA[ds]
    store = WorkOrderStore(settings.db_path, namespace="default")
    all_orders = store.get_all_work_orders()
    orders = [o for o in all_orders if o.get("status") == "OPEN"]
    
    # Active model ID
    try:
        model_meta = model_registry.get_metadata(ds)
        active_model_id = model_meta["model_id"]
    except Exception:
        active_model_id = "unknown"
        
    crit_count = sum(1 for o in orders if o.get("severity") == "CRITICAL")
    warn_count = sum(1 for o in orders if o.get("severity") in ("HIGH", "MEDIUM"))
    fault_count = sum(1 for o in orders if o.get("severity") == "ESCALATE_HUMAN")
    nominal_count = max(0, meta.test_engines - len(orders))
    
    return FleetSummary(
        dataset=ds,
        total_engines=meta.test_engines,
        monitored_engines=meta.test_engines,
        nominal_count=nominal_count,
        warning_count=warn_count,
        critical_count=crit_count,
        active_work_orders=len(orders),
        telemetry_fault_count=fault_count,
        active_model_id=active_model_id,
    )
