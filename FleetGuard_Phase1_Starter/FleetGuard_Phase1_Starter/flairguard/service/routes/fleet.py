"""Fleet management and engine discovery endpoints."""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, HTTPException, Body
from pydantic import BaseModel, Field
from flairguard.service.schemas import DatasetInfo, EngineSummary, FleetSummary
from flairguard.service.config import settings
from flairguard.service.models_registry import model_registry
from flairguard.data import load_subset
from flairguard.storage import WorkOrderStore
from flairguard.fleet_scheduler import (
    FleetMaintenanceScheduler,
    build_profiles_from_dataset,
    SchedulePolicy,
    FleetScheduleSnapshot,
    SchedulingMetrics,
)

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
    ),
    "FD003": DatasetInfo(
        id="FD003",
        name="NASA C-MAPSS FD003 (Dual Fault Mode)",
        operating_conditions=1,
        fault_modes=2,
        train_engines=100,
        test_engines=100,
        total_records=41316,
        description="Sea level condition with two concurrent degradation modes: HPC and Fan degradation."
    ),
    "FD004": DatasetInfo(
        id="FD004",
        name="NASA C-MAPSS FD004 (Multi-Regime Dual Fault)",
        operating_conditions=6,
        fault_modes=2,
        train_engines=249,
        test_engines=248,
        total_records=102463,
        description="Six flight conditions with two concurrent degradation modes: HPC and Fan degradation."
    ),
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


@router.get("/kpis")
def get_fleet_kpis():
    """Return top-level aggregate KPIs for the platform dashboard."""
    store = WorkOrderStore(settings.db_path, namespace="default")
    orders = [o for o in store.get_all_work_orders() if o.get("status") in ("OPEN", "ACKNOWLEDGED", "IN_PROGRESS")]
    open_escalations = sum(1 for o in orders if o.get("severity") == "ESCALATE_HUMAN")
    total_monitored = sum(m.test_engines for m in DATASET_METADATA.values())
    return {
        "total_monitored_engines": total_monitored,
        "active_work_orders": len(orders),
        "open_escalations": open_escalations,
        "sensors_monitored": 21,
        "champion_policy": "Tuned Point-RUL",
    }


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


@router.get("/engines/{engine_id}/trajectory")
def get_engine_trajectory(
    engine_id: int,
    dataset: str = Query("FD002", description="Dataset identifier (FD001 or FD002)"),
    split: str = Query("test", description="Data split (train or test)"),
    limit: int = Query(150, ge=1, le=500),
):
    """Retrieve raw NASA sensor trajectory records for an individual turbofan engine."""
    ds = dataset.upper()
    try:
        train_df, test_df, _ = load_subset(settings.data_dir, ds)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read dataset: {str(e)}")
        
    target_df = train_df if split == "train" else test_df
    eng_df = target_df[target_df.engine_id == engine_id].sort_values("cycle").head(limit)
    if eng_df.empty:
        raise HTTPException(status_code=404, detail=f"Engine {engine_id} not found in {ds} {split} set")
        
    records = eng_df.to_dict(orient="records")
    return {
        "engine_id": engine_id,
        "dataset": ds,
        "split": split,
        "total_cycles": len(records),
        "trajectory": records
    }


class SchedulerSimulationRequest(BaseModel):
    dataset: str = "FD002"
    num_bays: int = Field(3, ge=1, le=10)
    service_duration: int = Field(4, ge=1, le=20)
    engine_limit: int = Field(30, ge=5, le=200)
    service_threshold_rul: float = Field(25.0, ge=5.0, le=50.0)


@router.get("/scheduler/snapshot", response_model=FleetScheduleSnapshot)
def get_scheduler_snapshot(
    dataset: str = Query("FD002", description="Dataset identifier (FD001-FD004)"),
    num_bays: int = Query(3, ge=1, le=10),
    service_duration: int = Query(4, ge=1, le=20),
    target_cycle: int = Query(120, ge=1, le=350),
    policy: str = Query("RISK_AWARE", description="Dispatch policy: FCFS, EDF, RUL_PRIORITY, RISK_AWARE"),
    engine_limit: int = Query(30, ge=5, le=100),
):
    """Retrieve real-time maintenance depot status (active bay occupation and prioritized queue)."""
    ds = dataset.upper()
    if ds not in DATASET_METADATA:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset} not supported")
        
    try:
        pol_enum = SchedulePolicy(policy.upper())
    except ValueError:
        pol_enum = SchedulePolicy.RISK_AWARE
        
    try:
        profiles = build_profiles_from_dataset(settings.data_dir, ds, engine_limit=engine_limit)
        scheduler = FleetMaintenanceScheduler(num_bays=num_bays, service_duration=service_duration)
        snapshot = scheduler.get_live_snapshot(
            profiles=profiles,
            target_cycle=target_cycle,
            policy=pol_enum,
            dataset=ds,
        )
        return snapshot
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate depot snapshot: {str(e)}")


@router.post("/scheduler/simulate", response_model=List[SchedulingMetrics])
def run_scheduler_simulation(
    req: SchedulerSimulationRequest = Body(...),
):
    """Simulate and compare all 4 fleet dispatch policies under constrained depot capacity."""
    ds = req.dataset.upper()
    if ds not in DATASET_METADATA:
        raise HTTPException(status_code=404, detail=f"Dataset {req.dataset} not supported")
        
    try:
        profiles = build_profiles_from_dataset(settings.data_dir, ds, engine_limit=req.engine_limit)
        scheduler = FleetMaintenanceScheduler(
            num_bays=req.num_bays,
            service_duration=req.service_duration,
            service_threshold_rul=req.service_threshold_rul,
        )
        comparison = scheduler.evaluate_comparison(profiles)
        return comparison
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation failed: {str(e)}")
