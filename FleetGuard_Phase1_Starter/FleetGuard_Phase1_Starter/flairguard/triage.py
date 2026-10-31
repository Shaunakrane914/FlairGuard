"""Risk-Aware Non-LLM Triage Agent for FlairGuard AI.

A deterministic, fully auditable closed-loop decision engine that:
1. Synthesizes RUL prediction, model uncertainty, anomaly scores, and anomaly persistence.
2. Evaluates telemetry data quality (stuck sensors, missing data, out-of-range envelope).
3. Detects model/telemetry evidence conflicts and escalates to human reliability engineers.
4. Categorizes actionable maintenance severities (CRITICAL, HIGH, MEDIUM, NORMAL).
5. Interacts with persistent SQLite storage for duplicate suppression and severity escalation.
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional
from pathlib import Path
from flairguard.quality import QualityAssessment
from flairguard.storage import WorkOrderStore


@dataclass
class TriageDecision:
    engine_id: int
    cycle: int
    severity: str  # CRITICAL, HIGH, MEDIUM, NORMAL, ESCALATE_HUMAN
    action_type: str
    predicted_rul: float
    uncertainty: float
    anomaly_score: float
    persistence_count: int
    decision_reason: str
    store_status: str  # CREATED, ESCALATED, SUPPRESSED, NOOP
    work_order_id: Optional[str] = None


class RiskAwareTriageAgent:
    """Non-LLM deterministic policy engine for autonomous fleet maintenance decisions."""

    def __init__(
        self,
        store: WorkOrderStore,
        crit_threshold: float = 15.0,  # Cycles
        high_threshold: float = 35.0,  # Cycles
        med_threshold: float = 55.0,   # Cycles
        persistence_crit: int = 3,
        conflict_rul_cutoff: float = 60.0,
        conflict_persistence_cutoff: int = 4,
    ):
        self.store = store
        self.crit_threshold = crit_threshold
        self.high_threshold = high_threshold
        self.med_threshold = med_threshold
        self.persistence_crit = persistence_crit
        self.conflict_rul_cutoff = conflict_rul_cutoff
        self.conflict_persistence_cutoff = conflict_persistence_cutoff

    def evaluate(
        self,
        engine_id: int,
        cycle: int,
        predicted_rul: float,
        uncertainty: float,
        anomaly_score: float,
        persistence_count: int,
        quality: QualityAssessment,
        telemetry_snapshot: Optional[Dict[str, Any]] = None,
    ) -> TriageDecision:
        """Evaluate operational telemetry snapshot and produce an auditable maintenance decision."""
        # Rule 1: Data-Quality Fault Separation
        if not quality.is_valid:
            severity = "ESCALATE_HUMAN"
            action_type = "ESCALATE_HUMAN_DATA_FAULT"
            reason = (
                f"Data quality defect ({quality.quality_code}): "
                f"{quality.details.get('reason', 'Unverified sensor stream')}"
            )
        # Rule 2: Conflicting Model Evidence Detection
        elif (persistence_count >= self.conflict_persistence_cutoff and
              predicted_rul > self.conflict_rul_cutoff):
            severity = "ESCALATE_HUMAN"
            action_type = "ESCALATE_HUMAN_CONFLICT"
            reason = (
                f"Conflicting telemetry evidence: persistent degradation detected "
                f"({persistence_count} cycles, anomaly score={anomaly_score:.2f}) "
                f"conflicts with optimistic predicted RUL ({predicted_rul:.1f} cycles). "
                f"Manual inspection required."
            )
        elif (predicted_rul < self.crit_threshold and
              persistence_count == 0 and
              anomaly_score < 0.20):
            severity = "ESCALATE_HUMAN"
            action_type = "ESCALATE_HUMAN_CONFLICT"
            reason = (
                f"Conflicting telemetry evidence: model predicts imminent failure "
                f"(RUL={predicted_rul:.1f} cycles) while sensor health is strictly nominal. "
                f"Verification required."
            )
        # Rule 3: Critical Condition (P1)
        elif (predicted_rul <= self.crit_threshold or
              (predicted_rul <= (self.crit_threshold + 10.0) and persistence_count >= self.persistence_crit)):
            severity = "CRITICAL"
            action_type = "WORK_ORDER_IMMEDIATE_OVERHAUL"
            reason = (
                f"Critical degradation: Remaining useful life is {predicted_rul:.1f} cycles "
                f"(uncertainty +/-{uncertainty:.1f}), persistence={persistence_count}. "
                f"Immediate overhaul scheduled."
            )
        # Rule 4: High Priority Servicing (P2)
        elif (predicted_rul <= self.high_threshold and persistence_count >= 2):
            severity = "HIGH"
            action_type = "WORK_ORDER_SCHEDULE_MAINTENANCE"
            reason = (
                f"Confirmed progressive wear: RUL is {predicted_rul:.1f} cycles with "
                f"confirmed anomaly persistence ({persistence_count} cycles). "
                f"Servicing scheduled in next depot window."
            )
        # Rule 5: Medium Preventive Maintenance (P3)
        elif (predicted_rul <= self.med_threshold and
              (persistence_count >= 1 or predicted_rul <= 40.0)):
            severity = "MEDIUM"
            action_type = "WORK_ORDER_PREVENTIVE_INSPECTION"
            reason = (
                f"Preventive wear threshold: RUL is {predicted_rul:.1f} cycles. "
                f"Dispatched line inspection and lubrication."
            )
        # Rule 6: Nominal Operation (P4)
        else:
            severity = "NORMAL"
            action_type = "MONITOR"
            reason = (
                f"Nominal operating state: RUL is {predicted_rul:.1f} cycles, "
                f"telemetry is within nominal operating limits."
            )

        # Idempotent database storage
        rec = self.store.record_decision(
            engine_id=engine_id,
            cycle=cycle,
            severity=severity,
            action_type=action_type,
            predicted_rul=predicted_rul,
            uncertainty=uncertainty,
            anomaly_score=anomaly_score,
            persistence_count=persistence_count,
            decision_reason=reason,
            telemetry_snapshot=telemetry_snapshot,
        )

        return TriageDecision(
            engine_id=engine_id,
            cycle=cycle,
            severity=severity,
            action_type=action_type,
            predicted_rul=predicted_rul,
            uncertainty=uncertainty,
            anomaly_score=anomaly_score,
            persistence_count=persistence_count,
            decision_reason=reason,
            store_status=rec.get("status", "NOOP"),
            work_order_id=rec.get("work_order_id"),
        )

