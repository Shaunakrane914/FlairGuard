"""Policy Evaluation and Cost Simulation for FlairGuard AI.

Compares:
1. Fixed-Interval Maintenance (e.g. overhaul every N cycles)
2. Basic RUL-Threshold Policy (e.g. intervene if predicted RUL <= 25)
3. FlairGuard Risk-Aware Triage Policy (RUL + anomaly persistence + quality + human triage)

Documented Cost Assumptions:
- Planned maintenance cost (C_planned): 1.0 unit
- Unplanned breakdown penalty (C_unplanned): 10.0 units (10x penalty for catastrophic failure)
- Wasted component life cost (C_waste): 0.05 units per unspent cycle of true RUL
- Inspection / triage cost (C_inspect): 0.20 units per human engineering review
"""
from dataclasses import dataclass
from typing import Dict, List, Any
import numpy as np
import pandas as pd
from flairguard.storage import WorkOrderStore
from flairguard.triage import RiskAwareTriageAgent
from flairguard.quality import TelemetryQualityAuditor
from flairguard.anomaly import BaseAnomalyDetector, PersistenceFilter

COST_PLANNED = 1.0
COST_UNPLANNED = 10.0
COST_WASTE_PER_CYCLE = 0.05
COST_INSPECTION = 0.20


@dataclass
class PolicySummary:
    policy_name: str
    total_cost: float
    unplanned_breakdowns: int
    planned_maintenances: int
    inspections_dispatched: int
    avg_wasted_rul_cycles: float
    fleet_reliability_pct: float


def simulate_fixed_interval_policy(
    heldout_engines: List[pd.DataFrame],
    interval_cycles: int = 140,
) -> PolicySummary:
    """Evaluate standard fixed-interval scheduled overhaul policy."""
    total_cost = 0.0
    breakdowns = 0
    planned = 0
    wasted_cycles = []
    
    for engine_df in heldout_engines:
        max_cycle = int(engine_df["cycle"].max())
        if max_cycle < interval_cycles:
            # Engine broke down before reaching maintenance interval
            breakdowns += 1
            total_cost += COST_UNPLANNED
            wasted_cycles.append(0.0)
        else:
            # Overhauled at scheduled interval
            planned += 1
            waste = max_cycle - interval_cycles
            wasted_cycles.append(waste)
            total_cost += COST_PLANNED + waste * COST_WASTE_PER_CYCLE
            
    n = len(heldout_engines)
    return PolicySummary(
        policy_name=f"Fixed-Interval ({interval_cycles} cycles)",
        total_cost=round(total_cost, 2),
        unplanned_breakdowns=breakdowns,
        planned_maintenances=planned,
        inspections_dispatched=0,
        avg_wasted_rul_cycles=round(float(np.mean(wasted_cycles)), 2),
        fleet_reliability_pct=round(100.0 * (n - breakdowns) / n, 2),
    )


def simulate_basic_rul_policy(
    heldout_engines: List[pd.DataFrame],
    predictions_map: Dict[tuple[int, int], float],
    trigger_rul: float = 25.0,
) -> PolicySummary:
    """Evaluate simple uncalibrated RUL threshold policy."""
    total_cost = 0.0
    breakdowns = 0
    planned = 0
    wasted_cycles = []
    
    for engine_df in heldout_engines:
        engine_id = int(engine_df["engine_id"].iloc[0])
        max_cycle = int(engine_df["cycle"].max())
        intervened = False
        
        for _, row in engine_df.iterrows():
            c = int(row["cycle"])
            pred_rul = predictions_map.get((engine_id, c), 100.0)
            if pred_rul <= trigger_rul:
                # Intervene
                intervened = True
                planned += 1
                waste = max_cycle - c
                wasted_cycles.append(waste)
                total_cost += COST_PLANNED + waste * COST_WASTE_PER_CYCLE
                break
                
        if not intervened:
            breakdowns += 1
            total_cost += COST_UNPLANNED
            wasted_cycles.append(0.0)
            
    n = len(heldout_engines)
    return PolicySummary(
        policy_name=f"Basic RUL Threshold (<= {trigger_rul} cycles)",
        total_cost=round(total_cost, 2),
        unplanned_breakdowns=breakdowns,
        planned_maintenances=planned,
        inspections_dispatched=0,
        avg_wasted_rul_cycles=round(float(np.mean(wasted_cycles)), 2),
        fleet_reliability_pct=round(100.0 * (n - breakdowns) / n, 2),
    )


def simulate_flairguard_triage_policy(
    heldout_engines: List[pd.DataFrame],
    predictions_map: Dict[tuple[int, int], float],
    anomaly_detector: BaseAnomalyDetector,
    quality_auditor: TelemetryQualityAuditor,
    db_path: str,
    feature_cols: List[str],
    persistence_length: int = 3,
) -> PolicySummary:
    """Evaluate FlairGuard risk-aware closed-loop triage policy."""
    store = WorkOrderStore(db_path)
    agent = RiskAwareTriageAgent(store=store, persistence_crit=persistence_length)
    persistence_filter = PersistenceFilter(persistence_length=persistence_length)
    
    total_cost = 0.0
    breakdowns = 0
    planned = 0
    inspections = 0
    wasted_cycles = []
    
    for engine_df in heldout_engines:
        engine_id = int(engine_df["engine_id"].iloc[0])
        max_cycle = int(engine_df["cycle"].max())
        intervened = False
        persistence_filter.reset_engine(engine_id)
        
        for _, row in engine_df.iterrows():
            c = int(row["cycle"])
            telemetry_dict = {col: float(row[col]) for col in row.index if col.startswith("sensor_") or col.startswith("setting_")}
            
            # 1. Quality audit
            quality = quality_auditor.audit_row(engine_id, c, telemetry_dict)
            
            # 2. Anomaly scoring
            feat_vec = row[feature_cols].to_numpy(dtype=float).reshape(1, -1)
            raw_anomaly_score = float(anomaly_detector.compute_raw_score(feat_vec)[0])
            is_anom = raw_anomaly_score >= anomaly_detector.threshold
            p_count = persistence_filter.update(engine_id, is_anom)
            
            # 3. RUL prediction
            pred_rul = predictions_map.get((engine_id, c), 100.0)
            uncertainty = 15.0  # Approx RMSE uncertainty band
            
            # 4. Triage evaluation
            decision = agent.evaluate(
                engine_id=engine_id,
                cycle=c,
                predicted_rul=pred_rul,
                uncertainty=uncertainty,
                anomaly_score=raw_anomaly_score,
                persistence_count=p_count,
                quality=quality,
                telemetry_snapshot=telemetry_dict
            )
            
            if decision.severity == "ESCALATE_HUMAN" and decision.store_status in ("CREATED", "ESCALATED"):
                inspections += 1
                total_cost += COST_INSPECTION
                
            if decision.severity in ("HIGH", "CRITICAL"):
                intervened = True
                planned += 1
                waste = max_cycle - c
                wasted_cycles.append(waste)
                total_cost += COST_PLANNED + waste * COST_WASTE_PER_CYCLE
                break
                
        if not intervened:
            breakdowns += 1
            total_cost += COST_UNPLANNED
            wasted_cycles.append(0.0)
            
    n = len(heldout_engines)
    return PolicySummary(
        policy_name="FlairGuard Risk-Aware Triage Policy",
        total_cost=round(total_cost, 2),
        unplanned_breakdowns=breakdowns,
        planned_maintenances=planned,
        inspections_dispatched=inspections,
        avg_wasted_rul_cycles=round(float(np.mean(wasted_cycles)), 2),
        fleet_reliability_pct=round(100.0 * (n - breakdowns) / n, 2),
    )

