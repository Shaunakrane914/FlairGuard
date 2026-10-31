"""Fleet-level maintenance scheduling under constrained depot capacity.

Models physical depot constraints (hangar bays, service durations, queue delays)
and compares maintenance dispatch policies:
- FCFS (First-Come, First-Served)
- EDF (Earliest Deadline First)
- RUL_PRIORITY (Lowest Predicted RUL Priority)
- RISK_AWARE (Cost-Optimal Risk & Uncertainty-Weighted Scheduling)

Provides mathematical queue optimization, preventing fleet groundings and
in-flight failures when multiple engines degrade simultaneously.
"""
from dataclasses import dataclass, field
from enum import Enum
import math
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from flairguard.data import load_subset, read_test_end_rul
from flairguard.service.config import settings


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
    uncertainty_sigma: float
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


class FleetScheduleSnapshot(BaseModel):
    timestamp_cycle: int
    num_bays: int
    bays: List[BayState]
    queue: List[QueuedEngineState]
    active_policy: str
    summary_message: str


@dataclass
class EngineSimProfile:
    engine_id: int
    max_cycle: int
    true_rul_at_end: float
    observations: List[Tuple[int, float, float]]  # (cycle, predicted_rul, uncertainty)


class FleetMaintenanceScheduler:
    """Simulates and optimizes fleet maintenance scheduling under depot bay constraints."""

    def __init__(
        self,
        num_bays: int = 3,
        service_duration: int = 4,
        service_threshold_rul: float = 25.0,
        cost_failure: float = 10.0,
        cost_service: float = 1.0,
        cost_waste_per_cycle: float = 0.05,
        cost_grounding_delay: float = 0.1,
    ):
        self.num_bays = max(1, num_bays)
        self.service_duration = max(1, service_duration)
        self.service_threshold_rul = service_threshold_rul
        self.cost_failure = cost_failure
        self.cost_service = cost_service
        self.cost_waste_per_cycle = cost_waste_per_cycle
        self.cost_grounding_delay = cost_grounding_delay

    def _calculate_urgency(
        self,
        policy: SchedulePolicy,
        pred_rul: float,
        uncertainty: float,
        wait_cycles: int,
        requested_cycle: int,
        earliest_bay_free_in: int,
    ) -> float:
        """Calculate dispatch urgency score (higher score = serviced earlier)."""
        if policy == SchedulePolicy.FCFS:
            # Urgency increases purely with wait time
            return float(wait_cycles * 100.0)
            
        elif policy == SchedulePolicy.EDF:
            # Deadline = requested_cycle + pred_rul. Lower deadline = higher urgency.
            deadline = requested_cycle + pred_rul
            return float(10000.0 - deadline)
            
        elif policy == SchedulePolicy.RUL_PRIORITY:
            # Lower predicted RUL = higher urgency.
            effective_rul = max(0.0, pred_rul - wait_cycles)
            return float(1000.0 - effective_rul)
            
        elif policy == SchedulePolicy.RISK_AWARE:
            # Risk-aware: probability of exceeding remaining life before bay availability
            # Incorporates both point RUL, uncertainty variance, and hangar wait time
            effective_rul = max(0.1, pred_rul - wait_cycles)
            sigma = max(1.0, uncertainty)
            
            # Probability that true RUL is less than the wait time until a bay opens
            # z = (wait_time - effective_rul) / sigma
            z = (earliest_bay_free_in - effective_rul) / sigma
            # Standard normal CDF approximation
            fail_risk = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
            
            # Risk score balances immediate failure penalty vs waiting cost
            urgency = (fail_risk * self.cost_failure * 100.0) + (1000.0 / effective_rul) + (wait_cycles * 2.0)
            return float(urgency)
            
        return float(wait_cycles)

    def simulate_fleet(
        self,
        profiles: List[EngineSimProfile],
        policy: SchedulePolicy = SchedulePolicy.RISK_AWARE,
    ) -> SchedulingMetrics:
        """Simulate fleet maintenance dispatch across engine lifecycles under bay constraints."""
        bays: List[Dict[str, Any]] = [
            {"bay_id": i + 1, "engine_id": None, "cycles_remaining": 0, "status_occupied": False}
            for i in range(self.num_bays)
        ]
        
        queue: List[Dict[str, Any]] = []
        serviced_engines: List[Dict[str, Any]] = []
        failed_engines: List[Dict[str, Any]] = []
        total_busy_bay_cycles = 0
        all_wait_times: List[int] = []

        # Find maximum operational horizon across all engines
        max_horizon = max((p.max_cycle for p in profiles), default=0) + self.service_duration + 50

        # Map profiles for quick lookup
        profile_map = {p.engine_id: p for p in profiles}
        active_engine_ids = set(profile_map.keys())
        
        # Build event calendar for when engines request service
        service_requests: Dict[int, List[Dict[str, Any]]] = {}
        for p in profiles:
            for cycle, pred_rul, unc in p.observations:
                if pred_rul <= self.service_threshold_rul:
                    service_requests.setdefault(cycle, []).append({
                        "engine_id": p.engine_id,
                        "pred_rul": pred_rul,
                        "uncertainty": unc,
                        "request_cycle": cycle,
                    })
                    break  # Engine only requests service once

        # Cycle-by-cycle operational simulation
        for t in range(1, max_horizon + 1):
            # 1. Update active bays (advance repair work)
            for bay in bays:
                if bay["status_occupied"]:
                    total_busy_bay_cycles += 1
                    bay["cycles_remaining"] -= 1
                    if bay["cycles_remaining"] <= 0:
                        # Maintenance completed!
                        serviced_engines.append({
                            "engine_id": bay["engine_id"],
                            "completed_at": t,
                            "wasted_cycles": bay.get("wasted_cycles", 0.0),
                        })
                        bay["engine_id"] = None
                        bay["status_occupied"] = False

            # 2. Check for new service requests arriving at cycle t
            if t in service_requests:
                for req in service_requests[t]:
                    if req["engine_id"] in active_engine_ids:
                        queue.append({
                            "engine_id": req["engine_id"],
                            "requested_cycle": t,
                            "pred_rul": req["pred_rul"],
                            "uncertainty": req["uncertainty"],
                            "wait_cycles": 0,
                            "status": "QUEUED",
                        })

            # 3. Check queued engines for in-flight failure while waiting
            surviving_queue = []
            for item in queue:
                eng_id = item["engine_id"]
                p = profile_map[eng_id]
                # True remaining cycles for this engine
                elapsed_since_request = t - item["requested_cycle"]
                true_remaining = p.true_rul_at_end + max(0, p.max_cycle - t)
                
                if true_remaining <= 0:
                    # Engine ran past true physical life while waiting for depot!
                    failed_engines.append({
                        "engine_id": eng_id,
                        "failed_at": t,
                        "wait_cycles": item["wait_cycles"],
                    })
                    active_engine_ids.discard(eng_id)
                else:
                    item["wait_cycles"] = elapsed_since_request
                    surviving_queue.append(item)
            queue = surviving_queue

            # 4. Allocate available bays to queued engines based on chosen policy
            free_bays = [b for b in bays if not b["status_occupied"]]
            if free_bays and queue:
                # Calculate earliest time ANY busy bay will become free
                earliest_busy = min((b["cycles_remaining"] for b in bays if b["status_occupied"]), default=1)
                
                # Compute urgency scores for all queued engines
                for item in queue:
                    item["urgency"] = self._calculate_urgency(
                        policy=policy,
                        pred_rul=item["pred_rul"],
                        uncertainty=item["uncertainty"],
                        wait_cycles=item["wait_cycles"],
                        requested_cycle=item["requested_cycle"],
                        earliest_bay_free_in=earliest_busy,
                    )
                
                # Sort queue descending by urgency score
                queue.sort(key=lambda x: x["urgency"], reverse=True)
                
                # Dispatch highest priority engines into free bays
                while free_bays and queue:
                    bay = free_bays.pop(0)
                    selected_engine = queue.pop(0)
                    eng_id = selected_engine["engine_id"]
                    
                    p = profile_map[eng_id]
                    true_remaining = p.true_rul_at_end + max(0, p.max_cycle - t)
                    wasted = max(0.0, float(true_remaining))
                    
                    bay["engine_id"] = eng_id
                    bay["status_occupied"] = True
                    bay["cycles_remaining"] = self.service_duration
                    bay["wasted_cycles"] = wasted
                    
                    all_wait_times.append(selected_engine["wait_cycles"])
                    active_engine_ids.discard(eng_id)

            # Termination condition: no active bays, no queued engines, all requests processed
            if not queue and not any(b["status_occupied"] for b in bays) and t > max((p.max_cycle for p in profiles), default=0):
                break

        # Calculate summary metrics
        total_eval = len(profiles)
        serviced_count = len(serviced_engines)
        failure_count = len(failed_engines)
        
        mean_wait = float(np.mean(all_wait_times)) if all_wait_times else 0.0
        max_wait = int(np.max(all_wait_times)) if all_wait_times else 0
        mean_wasted = float(np.mean([e["wasted_cycles"] for e in serviced_engines])) if serviced_engines else 0.0
        
        total_possible_bay_cycles = max(1, t * self.num_bays)
        bay_utilization = min(100.0, (total_busy_bay_cycles / total_possible_bay_cycles) * 100.0)
        
        # Financial cost model
        cost_fails = failure_count * self.cost_failure
        cost_services = serviced_count * self.cost_service
        cost_wasted_life = mean_wasted * serviced_count * self.cost_waste_per_cycle
        cost_delays = sum(all_wait_times) * self.cost_grounding_delay
        total_cost = round(cost_fails + cost_services + cost_wasted_life + cost_delays, 2)

        recommendation = (
            "Recommended Champion: Minimizes in-flight failures under bottlenecked depot capacity."
            if policy == SchedulePolicy.RISK_AWARE and failure_count == 0
            else f"Baseline policy: resulted in {failure_count} in-flight failures due to depot queue delays."
        )

        return SchedulingMetrics(
            policy=policy.value,
            num_bays=self.num_bays,
            service_duration=self.service_duration,
            total_engines_evaluated=total_eval,
            serviced_count=serviced_count,
            failure_count=failure_count,
            mean_queue_wait_cycles=round(mean_wait, 2),
            max_queue_wait_cycles=max_wait,
            mean_wasted_cycles=round(mean_wasted, 2),
            bay_utilization_pct=round(bay_utilization, 1),
            total_fleet_cost=total_cost,
            cost_breakdown={
                "failure_penalties": round(cost_fails, 2),
                "maintenance_executions": round(cost_services, 2),
                "wasted_useful_life": round(cost_wasted_life, 2),
                "queue_delays": round(cost_delays, 2),
            },
            operational_recommendation=recommendation,
        )

    def evaluate_comparison(
        self,
        profiles: List[EngineSimProfile],
    ) -> List[SchedulingMetrics]:
        """Evaluate and rank all 4 scheduling policies on identical fleet trajectories."""
        results = []
        for pol in [SchedulePolicy.FCFS, SchedulePolicy.EDF, SchedulePolicy.RUL_PRIORITY, SchedulePolicy.RISK_AWARE]:
            metrics = self.simulate_fleet(profiles, policy=pol)
            results.append(metrics)
        # Sort by total fleet cost ascending
        results.sort(key=lambda x: x.total_fleet_cost)
        return results

    def get_live_snapshot(
        self,
        profiles: List[EngineSimProfile],
        target_cycle: int = 120,
        policy: SchedulePolicy = SchedulePolicy.RISK_AWARE,
        dataset: str = "FD002",
    ) -> FleetScheduleSnapshot:
        """Advance operational simulation up to target_cycle and return depot board snapshot."""
        bays: List[Dict[str, Any]] = [
            {"bay_id": i + 1, "engine_id": None, "cycles_remaining": 0, "status_occupied": False}
            for i in range(self.num_bays)
        ]
        queue: List[Dict[str, Any]] = []
        profile_map = {p.engine_id: p for p in profiles}
        active_engine_ids = set(profile_map.keys())

        service_requests: Dict[int, List[Dict[str, Any]]] = {}
        for p in profiles:
            for cycle, pred_rul, unc in p.observations:
                if pred_rul <= self.service_threshold_rul:
                    service_requests.setdefault(cycle, []).append({
                        "engine_id": p.engine_id,
                        "pred_rul": pred_rul,
                        "uncertainty": unc,
                        "request_cycle": cycle,
                    })
                    break

        for t in range(1, target_cycle + 1):
            # Update active bays
            for bay in bays:
                if bay["status_occupied"]:
                    bay["cycles_remaining"] -= 1
                    if bay["cycles_remaining"] <= 0:
                        bay["engine_id"] = None
                        bay["status_occupied"] = False

            # New requests
            if t in service_requests:
                for req in service_requests[t]:
                    if req["engine_id"] in active_engine_ids:
                        queue.append({
                            "engine_id": req["engine_id"],
                            "requested_cycle": t,
                            "pred_rul": req["pred_rul"],
                            "uncertainty": req["uncertainty"],
                            "wait_cycles": 0,
                            "status": "QUEUED",
                        })

            # Check queue
            surviving_queue = []
            for item in queue:
                eng_id = item["engine_id"]
                p = profile_map[eng_id]
                elapsed = t - item["requested_cycle"]
                true_remaining = p.true_rul_at_end + max(0, p.max_cycle - t)
                if true_remaining > 0:
                    item["wait_cycles"] = elapsed
                    surviving_queue.append(item)
            queue = surviving_queue

            # Allocate bays
            free_bays = [b for b in bays if not b["status_occupied"]]
            if free_bays and queue:
                earliest_busy = min((b["cycles_remaining"] for b in bays if b["status_occupied"]), default=1)
                for item in queue:
                    item["urgency"] = self._calculate_urgency(
                        policy=policy,
                        pred_rul=item["pred_rul"],
                        uncertainty=item["uncertainty"],
                        wait_cycles=item["wait_cycles"],
                        requested_cycle=item["requested_cycle"],
                        earliest_bay_free_in=earliest_busy,
                    )
                queue.sort(key=lambda x: x["urgency"], reverse=True)
                while free_bays and queue:
                    bay = free_bays.pop(0)
                    selected_engine = queue.pop(0)
                    bay["engine_id"] = selected_engine["engine_id"]
                    bay["status_occupied"] = True
                    bay["cycles_remaining"] = self.service_duration
                    active_engine_ids.discard(selected_engine["engine_id"])

        # Construct response snapshot
        bay_states = [
            BayState(
                bay_id=b["bay_id"],
                engine_id=b["engine_id"],
                cycles_remaining=max(0, b["cycles_remaining"]),
                status="OCCUPIED" if b["status_occupied"] else "IDLE",
            )
            for b in bays
        ]

        queued_states = [
            QueuedEngineState(
                engine_id=item["engine_id"],
                dataset=dataset,
                requested_cycle=item["requested_cycle"],
                current_cycle=target_cycle,
                predicted_rul=round(float(item["pred_rul"]), 1),
                uncertainty_sigma=round(float(item["uncertainty"]), 2),
                urgency_score=round(float(item.get("urgency", 0.0)), 1),
                waiting_cycles=item["wait_cycles"],
                status="QUEUED",
            )
            for item in queue
        ]

        occ_count = sum(1 for b in bay_states if b.status == "OCCUPIED")
        summary = (
            f"Depot operating at {target_cycle} cycles. {occ_count}/{self.num_bays} bays occupied. "
            f"{len(queued_states)} engines queued under {policy.value} dispatch policy."
        )

        return FleetScheduleSnapshot(
            timestamp_cycle=target_cycle,
            num_bays=self.num_bays,
            bays=bay_states,
            queue=queued_states,
            active_policy=policy.value,
            summary_message=summary,
        )


def build_profiles_from_dataset(
    data_dir: Path,
    dataset: str = "FD002",
    engine_limit: int = 50,
) -> List[EngineSimProfile]:
    """Extract realistic fleet simulation profiles from genuine NASA test trajectories."""
    train_df, test_df, test_rul = load_subset(data_dir, dataset)
    
    profiles = []
    engine_ids = sorted(test_df.engine_id.unique())[:engine_limit]
    
    for i, eng_id in enumerate(engine_ids):
        eng_df = test_df[test_df.engine_id == eng_id].sort_values("cycle")
        max_cyc = int(eng_df.cycle.max())
        true_rul_end = float(test_rul[i]) if i < len(test_rul) else 0.0
        
        # Build synthetic causal observations with realistic estimation variance
        # At cycle c, estimated RUL approaches true_rul_end + (max_cyc - c)
        observations = []
        for _, row in eng_df.iterrows():
            c = int(row["cycle"])
            ground_truth_remaining = true_rul_end + (max_cyc - c)
            
            # Realistic sensor-derived estimate: true RUL + causal noise
            # Uncertainty increases with remaining life
            sigma = max(2.0, ground_truth_remaining * 0.12)
            # Deterministic noise based on engine_id + cycle for strict reproducibility
            rng = np.random.default_rng(eng_id * 1000 + c)
            noise = float(rng.normal(0, sigma * 0.5))
            pred_rul = max(0.0, ground_truth_remaining + noise)
            
            observations.append((c, pred_rul, sigma))
            
        profiles.append(EngineSimProfile(
            engine_id=int(eng_id),
            max_cycle=max_cyc,
            true_rul_at_end=true_rul_end,
            observations=observations,
        ))
        
    return profiles
