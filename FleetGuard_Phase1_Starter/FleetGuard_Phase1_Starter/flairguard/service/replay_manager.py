"""Session manager for causal engine telemetry replay and simulation lab."""
import json
import uuid
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
import pandas as pd
from .config import settings
from .models_registry import model_registry
from flairguard.data import load_subset
from flairguard.quality import TELEMETRY_CHANNELS
from flairguard.storage import WorkOrderStore
from flairguard.replay import CausalReplay, InferenceEngine, policy_proposal


class ReplaySession:
    """Represents a single active engine replay session with isolated state and persistence."""

    def __init__(
        self,
        session_id: str,
        dataset: str,
        engine_id: int,
        split: str,
        policy_name: str,
        namespace: str,
        trajectory_df: pd.DataFrame,
        store: WorkOrderStore,
    ):
        self.session_id = session_id
        self.dataset = dataset.upper()
        self.engine_id = engine_id
        self.split = split
        self.policy_name = policy_name
        self.namespace = namespace
        self.trajectory_df = trajectory_df.sort_values("cycle").reset_index(drop=True)
        self.total_cycles = len(self.trajectory_df)
        self.current_index = 0
        self.store = store
        
        # Load bundle and initialize replay
        self.bundle = model_registry.get_bundle(self.dataset)
        self.model_id = self.bundle["model_id"]
        
        # Build policy definition
        if self.dataset == "FD002":
            policy_def = self.bundle["policies"].get(policy_name, self.bundle["policies"]["point"])
        else:
            policy_def = {
                "kind": policy_name,
                "threshold": 20.0,
                "stale_limit": 10,
                "fixed_age": 140,
                "min_history": 20,
                "lead_time": 5,
                "review_delay": 2,
                "critical_threshold": 15.0
            }
        self.policy_def = policy_def
        self.replay = CausalReplay(self.bundle, self.store, self.policy_def)
        
        # Fault injection state
        self.active_fault: Optional[Dict[str, Any]] = None
        self.last_evidence: Optional[Dict[str, Any]] = None

    def inject_fault(self, fault_type: str, channel: str, start_cycle: int, duration: int, magnitude: float = 1.0):
        """Configure synthetic telemetry fault without modifying raw NASA dataset."""
        self.active_fault = {
            "fault_type": fault_type,
            "channel": channel,
            "start_cycle": start_cycle,
            "end_cycle": start_cycle + duration,
            "duration": duration,
            "magnitude": magnitude,
        }

    def _apply_fault_if_active(self, cycle: int, telemetry: Dict[str, float]) -> Dict[str, float]:
        if not self.active_fault:
            return telemetry
        f = self.active_fault
        if f["start_cycle"] <= cycle < f["end_cycle"]:
            modified = dict(telemetry)
            ch = f["channel"]
            if ch in modified:
                if f["fault_type"] == "stuck_sensor":
                    # Freeze at baseline value
                    modified[ch] = 500.0
                elif f["fault_type"] == "sensor_drift":
                    # Gradual ramp
                    offset = (cycle - f["start_cycle"] + 1) * 2.5 * f["magnitude"]
                    modified[ch] += offset
                elif f["fault_type"] == "missing_data":
                    modified[ch] = np.nan
                elif f["fault_type"] == "gaussian_noise":
                    modified[ch] += np.random.normal(0, 15.0 * f["magnitude"])
            return modified
        return telemetry

    def step(self, count: int = 1) -> List[Dict[str, Any]]:
        """Advance simulation by count cycles."""
        results = []
        for _ in range(count):
            if self.current_index >= self.total_cycles:
                break
            row = self.trajectory_df.iloc[self.current_index]
            cycle = int(row["cycle"])
            raw_telemetry = {k: float(row[k]) for k in TELEMETRY_CHANNELS if k in row}
            
            # Apply fault if configured
            effective_telemetry = self._apply_fault_if_active(cycle, raw_telemetry)
            
            # Consume via CausalReplay
            asset_id = str(self.engine_id)
            decision_record = self.replay.consume(self.engine_id, cycle, effective_telemetry, asset_id=asset_id)
            
            # Retrieve latest checkpoint evidence
            _, state = self.store.get_checkpoint(self.engine_id, asset_id=asset_id)
            event = self.store.get_event(self.engine_id, cycle, asset_id=asset_id)
            pred_evidence = json.loads(event["prediction_evidence_json"]) if event and event.get("prediction_evidence_json") else {}
            prop_data = json.loads(event["proposal_json"]) if event and event.get("proposal_json") else {}
            
            last_valid = state.get("last_valid") if state else None
            is_usable = bool(last_valid and isinstance(last_valid, dict) and last_valid.get("cycle") == cycle)
            
            evidence = {
                "cycle": cycle,
                "telemetry": effective_telemetry,
                "prediction": pred_evidence.get("prediction"),
                "usable": is_usable,
                "anomaly_score": pred_evidence.get("anomaly_score"),
                "persistence": pred_evidence.get("persistence"),
                "decision": decision_record,
                "work_order_id": decision_record.get("work_order_id"),
                "severity": decision_record.get("severity") or prop_data.get("severity"),
                "action_type": prop_data.get("action_type"),
            }
            self.last_evidence = evidence
            self.current_index += 1
            results.append(evidence)
        return results

    def reset(self):
        """Reset replay session back to cycle 1."""
        self.current_index = 0
        self.last_evidence = None


class ReplayManager:
    """Manages active replay sessions across datasets."""

    def __init__(self):
        self.sessions: Dict[str, ReplaySession] = {}
        self._cache_data: Dict[str, Tuple[pd.DataFrame, pd.DataFrame]] = {}

    def _get_dataset_data(self, dataset: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        dataset = dataset.upper()
        if dataset not in self._cache_data:
            train_df, test_df, _ = load_subset(settings.data_dir, dataset)
            self._cache_data[dataset] = (train_df, test_df)
        return self._cache_data[dataset]

    def create_session(
        self,
        dataset: str,
        engine_id: int,
        split: str = "test",
        policy_name: str = "point",
        namespace: Optional[str] = None,
    ) -> ReplaySession:
        dataset = dataset.upper()
        session_id = str(uuid.uuid4())[:8]
        ns = namespace or f"session_{session_id}"
        
        train_df, test_df = self._get_dataset_data(dataset)
        source_df = train_df if split == "train" else test_df
        engine_df = source_df[source_df.engine_id == engine_id]
        if engine_df.empty:
            raise ValueError(f"Engine {engine_id} not found in {dataset} {split} set")
            
        store = WorkOrderStore(settings.db_path, namespace=ns)
        session = ReplaySession(
            session_id=session_id,
            dataset=dataset,
            engine_id=engine_id,
            split=split,
            policy_name=policy_name,
            namespace=ns,
            trajectory_df=engine_df,
            store=store,
        )
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> ReplaySession:
        if session_id not in self.sessions:
            raise KeyError(f"Session {session_id} not found")
        return self.sessions[session_id]


# Global singleton manager
replay_manager = ReplayManager()
