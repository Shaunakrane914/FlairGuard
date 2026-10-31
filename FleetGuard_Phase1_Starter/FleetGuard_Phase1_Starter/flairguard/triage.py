"""Pure deterministic proposals with an explicit persistence boundary.

The compatibility agent commits proposals but never claims service execution.
"""
from dataclasses import dataclass
import math
from .quality import QualityAssessment
from .storage import WorkOrderStore

@dataclass
class Proposal:
    severity: str
    priority: str
    review_required: bool
    action_type: str
    reason: str

@dataclass
class TriageDecision:
    engine_id: int
    cycle: int
    severity: str
    action_type: str
    predicted_rul: float | None
    uncertainty: float | None
    anomaly_score: float | None
    persistence_count: int
    decision_reason: str
    store_status: str
    work_order_id: str | None = None
    priority: str = "NORMAL"
    review_required: bool = False

class RiskAwareTriageAgent:
    def __init__(self, store, crit_threshold=15.0, high_threshold=35.0, med_threshold=55.0,
                 persistence_crit=3, conflict_rul_cutoff=60.0, conflict_persistence_cutoff=4):
        self.store = store
        self.crit_threshold = crit_threshold
        self.high_threshold = high_threshold
        self.med_threshold = med_threshold
        self.persistence_crit = persistence_crit
        self.conflict_rul_cutoff = conflict_rul_cutoff
        self.conflict_persistence_cutoff = conflict_persistence_cutoff

    def propose(self, predicted_rul, anomaly_score, persistence_count, quality):
        if predicted_rul is not None and (not math.isfinite(predicted_rul) or predicted_rul < 0):
            raise ValueError("Invalid predicted RUL")
        urgent = predicted_rul is not None and predicted_rul <= self.crit_threshold
        if not quality.is_valid or predicted_rul is None:
            return Proposal('CRITICAL' if urgent else 'ESCALATE_HUMAN',
                            'CRITICAL' if urgent else 'MEDIUM',True,'ESCALATE_HUMAN_DATA_FAULT',
                            'Unreliable measurement/model evidence; '+quality.quality_code+
                            ('; urgent RUL evidence retained for review' if urgent else ''))
        if urgent or (predicted_rul <= self.crit_threshold+10 and persistence_count >= self.persistence_crit):
            return Proposal('CRITICAL','CRITICAL',False,'WORK_ORDER_IMMEDIATE_OVERHAUL',
                            'Critical RUL threshold: maintenance proposed, not yet executed')
        if persistence_count >= self.conflict_persistence_cutoff and predicted_rul > self.conflict_rul_cutoff:
            return Proposal('ESCALATE_HUMAN','MEDIUM',True,'ESCALATE_HUMAN_CONFLICT',
                            'Persistent sensor deviation conflicts with RUL estimate; cause unverified')
        if predicted_rul <= self.high_threshold and persistence_count >= 2:
            return Proposal('HIGH','HIGH',False,'WORK_ORDER_SCHEDULE_MAINTENANCE','RUL/persistence rule proposes maintenance')
        if predicted_rul <= self.med_threshold and (persistence_count >= 1 or predicted_rul <= 40):
            return Proposal('MEDIUM','MEDIUM',True,'WORK_ORDER_PREVENTIVE_INSPECTION','Inspection proposed; no physical intervention claimed')
        return Proposal('NORMAL','NORMAL',False,'MONITOR','Continue monitoring; no health certification')

    def evaluate(self, engine_id, cycle, predicted_rul, uncertainty, anomaly_score,
                 persistence_count, quality, telemetry_snapshot=None):
        proposal = self.propose(predicted_rul,anomaly_score,persistence_count,quality)
        rec = self.store.record_decision(engine_id,cycle,proposal.severity,proposal.action_type,
                predicted_rul,uncertainty,anomaly_score,persistence_count,proposal.reason,telemetry_snapshot,
                priority=proposal.priority,review_required=proposal.review_required)
        return TriageDecision(engine_id,cycle,proposal.severity,proposal.action_type,predicted_rul,
                uncertainty,anomaly_score,persistence_count,proposal.reason,rec['status'],
                rec.get('work_order_id'),proposal.priority,proposal.review_required)
