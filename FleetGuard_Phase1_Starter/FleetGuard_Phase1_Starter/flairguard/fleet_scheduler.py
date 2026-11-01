"""Observation-only fleet dispatch. Global t equals each engine's cycle (offset=0).

Engines continue ageing while queued and in service. A service is protective only
at completion. Failure notifications are external observations, never forecasts.
RISK_AWARE is an uncalibrated lower-margin heuristic, not a failure probability.
"""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
from pydantic import BaseModel, Field
from flairguard.data import read_trajectories
from flairguard.serving import predict_observations

class SchedulePolicy(str, Enum):
    FCFS = "FCFS"
    EDF = "EDF"
    RUL_PRIORITY = "RUL_PRIORITY"
    RISK_AWARE = "RISK_AWARE"


class BayState(BaseModel):
    bay_id: int
    engine_id: Optional[int] = None
    cycles_remaining: int = 0
    status: str = "IDLE"  # "IDLE" or "OCCUPIED"


class QueuedEngineState(BaseModel):
    engine_id: int
    dataset: str
    requested_cycle: int
    current_cycle: int
    predicted_rul: float
    uncertainty_sigma: Optional[float]  # legacy name; unavailable without a validated estimate
    urgency_score: float
    waiting_cycles: int
    status: str = "QUEUED"  # "QUEUED", "IN_SERVICE", "SERVICED", "FAILED"


class SchedulingMetrics(BaseModel):
    policy: str
    num_bays: int
    service_duration: int
    total_engines_evaluated: int
    serviced_count: int
    failure_count: int
    mean_queue_wait_cycles: float
    max_queue_wait_cycles: int
    mean_wasted_cycles: float
    bay_utilization_pct: float
    total_fleet_cost: float
    cost_breakdown: Dict[str, float]
    operational_recommendation: str
    evaluation_scope: str = "Censored operational trace; failure and wasted-life costs unavailable"
    censored_count: int = 0
    events: List[Dict[str, Any]] = Field(default_factory=list)


class FleetScheduleSnapshot(BaseModel):
    timestamp_cycle: int
    num_bays: int
    bays: List[BayState]
    queue: List[QueuedEngineState]
    active_policy: str
    summary_message: str


@dataclass(frozen=True)
class EngineSimProfile:
    engine_id: int
    max_cycle: int
    observations: List[Tuple[int, float, float]]
    model_id: str = "unspecified"
    artifact_sha256: str = ""


class FleetMaintenanceScheduler:
    def __init__(self, num_bays=3, service_duration=4, service_threshold_rul=25.0,
                 cost_failure=10.0, cost_service=1.0, cost_waste_per_cycle=0.05,
                 cost_grounding_delay=0.1):
        if num_bays < 1 or service_duration < 1:
            raise ValueError("Positive bay count and duration required")
        self.num_bays = int(num_bays)
        self.service_duration = int(service_duration)
        self.service_threshold_rul = service_threshold_rul
        self.cost_failure, self.cost_service = cost_failure, cost_service
        self.cost_waste_per_cycle, self.cost_grounding_delay = cost_waste_per_cycle, cost_grounding_delay

    def _calculate_urgency(self, policy, pred_rul, uncertainty, wait_cycles,
                           requested_cycle, earliest_bay_free_in=0):
        if policy == SchedulePolicy.FCFS:
            return -float(requested_cycle)
        if policy == SchedulePolicy.EDF:
            return -float(requested_cycle + pred_rul)
        if policy == SchedulePolicy.RUL_PRIORITY:
            return -float(pred_rul)
        # Uncalibrated conservative margin. No Gaussian assumption or truth-derived uncertainty.
        return -float(pred_rul - uncertainty - self.service_duration)

    def run(self, profiles, policy=SchedulePolicy.RISK_AWARE, target_cycle=None,
            failure_observer=None, horizon=None):
        if len({p.engine_id for p in profiles}) != len(profiles):
            raise ValueError("Duplicate engine IDs")
        calendar = {}
        for p in profiles:
            last = 0
            for c, pred, margin in p.observations:
                if c <= last or not np.isfinite([pred, margin]).all() or margin < 0:
                    raise ValueError("Invalid observation sequence")
                calendar.setdefault(c, []).append((p.engine_id, pred, margin))
                last = c
        end = target_cycle if target_cycle is not None else (horizon or max((p.max_cycle for p in profiles), default=0) + len(profiles)*self.service_duration)
        bays = [dict(bay_id=i+1, engine_id=None, due=None) for i in range(self.num_bays)]
        queue, last_obs, requests, done, events = {}, {}, {}, set(), []
        for t in range(1, end + 1):
            # World reports only failures observable NOW; exact-time failures precede completions.
            for eid in sorted(failure_observer(t) if failure_observer else []):
                if eid in done:
                    continue
                events.append(dict(kind="FAILURE", engine_id=eid, cycle=t))
                done.add(eid)
                queue.pop(eid, None)
                for bay in bays:
                    if bay["engine_id"] == eid:
                        bay.update(engine_id=None, due=None)
            for bay in bays:
                if bay["engine_id"] is not None and t >= bay["due"]:
                    eid = bay["engine_id"]
                    events.append(dict(kind="COMPLETE", engine_id=eid, cycle=t, bay_id=bay["bay_id"]))
                    done.add(eid)
                    bay.update(engine_id=None, due=None)
            for eid, pred, margin in calendar.get(t, []):
                if eid in done or any(b["engine_id"] == eid for b in bays):
                    continue
                last_obs[eid] = (t, pred, margin)
                if eid not in requests and pred <= self.service_threshold_rul:
                    requests[eid] = (t, pred)
                    queue[eid] = dict(engine_id=eid, requested_cycle=t)
                    events.append(dict(kind="REQUEST", engine_id=eid, cycle=t, predicted_rul=pred))
            for eid, item in queue.items():
                observed, prediction, margin = last_obs[eid]
                current = max(0., prediction - (t-observed))
                item.update(pred_rul=current, uncertainty=margin, wait_cycles=t-item["requested_cycle"])
                priority_rul = requests[eid][1] if policy == SchedulePolicy.EDF else current
                item["urgency"] = self._calculate_urgency(policy, priority_rul, margin,
                    item["wait_cycles"], item["requested_cycle"])
            for bay in bays:
                if bay["engine_id"] is None and queue:
                    item = sorted(queue.values(), key=lambda q:(-q["urgency"],q["requested_cycle"],q["engine_id"]))[0]
                    eid = item["engine_id"]
                    queue.pop(eid)
                    bay.update(engine_id=eid, due=t+self.service_duration)
                    events.append(dict(kind="START", engine_id=eid, cycle=t, bay_id=bay["bay_id"],
                                       request_cycle=item["requested_cycle"], predicted_rul=item["pred_rul"],
                                       uncertainty_margin=item["uncertainty"], urgency=item["urgency"]))
            if target_cycle is None and len(done) == len(profiles):
                break
        return dict(events=events, bays=bays, queue=list(queue.values()), cycle=t if end else 0,
                    censored_count=len(profiles)-len(done), profiles=profiles)

    def simulate_fleet(self, profiles, policy=SchedulePolicy.RISK_AWARE):
        raise ValueError("Evaluation requires the explicit evaluator and failure timeline; censored costs are unavailable")

    def evaluate_comparison(self, profiles):
        raise ValueError("Use scheduler_evaluation.compare_fleet with an explicit evaluator-only failure timeline")

    def get_live_snapshot(self, profiles, target_cycle=120, policy=SchedulePolicy.RISK_AWARE, dataset="FD002"):
        trace = self.run(profiles, policy, target_cycle=target_cycle)
        bays = [BayState(bay_id=b["bay_id"], engine_id=b["engine_id"],
                         cycles_remaining=max(0,(b["due"] or target_cycle)-target_cycle),
                         status="OCCUPIED" if b["engine_id"] is not None else "IDLE") for b in trace["bays"]]
        queue = [QueuedEngineState(engine_id=q["engine_id"],dataset=dataset,
                 requested_cycle=q["requested_cycle"], current_cycle=target_cycle,
                 predicted_rul=q["pred_rul"], uncertainty_sigma=q["uncertainty"] if q["uncertainty"] > 0 else None,
                 urgency_score=q["urgency"],waiting_cycles=q["wait_cycles"]) for q in trace["queue"]]
        return FleetScheduleSnapshot(timestamp_cycle=target_cycle,num_bays=self.num_bays,bays=bays,
            queue=queue,active_policy=policy.value,
            summary_message=f"Operational forecast at {target_cycle}: {sum(b.status=='OCCUPIED' for b in bays)}/{self.num_bays} bays occupied; {len(queue)} queued. Censored beyond telemetry; uncalibrated margin heuristic.")


def build_profiles_from_dataset(data_dir: Path, dataset="FD002", engine_limit=50, bundle=None):
    # Deliberately read only the observation file. No RUL loader or label alignment.
    if dataset not in ("FD001", "FD002", "FD003", "FD004"):
        raise ValueError("Unknown dataset")
    if bundle is None:
        from .service.models_registry import model_registry
        bundle = model_registry.get_bundle(dataset)
    raw = read_trajectories(Path(data_dir) / f"test_{dataset}.txt")
    raw = raw.loc[raw.engine_id.isin(sorted(raw.engine_id.unique())[:engine_limit])].reset_index(drop=True)
    raw_predictions, predictions = predict_observations(bundle, raw)
    raw["prediction"] = predictions
    # Fixed unavailable uncertainty is encoded as zero margin; never estimated using evaluator labels.
    # All policies receive identical point predictions. Risk calibration is NOT established.
    profiles = []
    for eid, rows in raw.groupby("engine_id", sort=True):
        observations = [(int(r.cycle), float(r.prediction), 0.0)
                        for r in rows.itertuples() if r.cycle >= bundle.get("min_history",20)]
        profiles.append(EngineSimProfile(int(eid),int(rows.cycle.max()),observations,
            bundle["model_id"],bundle.get("artifact_sha256", "")))
    return profiles
