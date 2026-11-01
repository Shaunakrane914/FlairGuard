"""Session manager for causal engine telemetry replay and simulation lab.

Provides durable SQLite session tracking, scientific perturbation modeling,
deterministic reset epochs, and cross-process restart recovery.
"""
import json
import uuid
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
import pandas as pd
from .config import settings
from .models_registry import model_registry
from flairguard.data import read_trajectories
from flairguard.quality import TELEMETRY_CHANNELS, ACTIVE_SENSORS
from flairguard.storage import WorkOrderStore
from flairguard.replay import CausalReplay


class ReplaySession:
    """Represents a single active engine replay session with durable state and scientific perturbations."""

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
        current_cycle: int = 0,
        reset_epoch: int = 0,
        model_release: Optional[str] = None,
    ):
        self.session_id = session_id
        self.dataset = dataset.upper()
        self.engine_id = engine_id
        self.split = split
        self.policy_name = policy_name
        self.base_namespace = namespace
        self.reset_epoch = reset_epoch
        self.namespace = f"{namespace}_ep{reset_epoch}" if reset_epoch > 0 else namespace
        self.trajectory_df = trajectory_df.sort_values("cycle").reset_index(drop=True)
        self.total_cycles = len(self.trajectory_df)
        self.current_index = current_cycle
        self.store = store
        
        # Load bundle and initialize replay
        self.model_release = model_release or model_registry.get_metadata(self.dataset)["provenance"]["release_id"]
        self.bundle = model_registry.get_release_bundle(self.dataset,self.model_release)
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
        
        # Calculate scientific baseline channel standard deviations for perturbation scaling
        self.sensor_stds = self.bundle.get("corruption_sensor_stds", {})
        if not self.sensor_stds:
            if "models" in self.bundle:
                references = self.bundle["models"][self.bundle["selected"]].features_.scales_
                self.sensor_stds = dict(zip(ACTIVE_SENSORS,map(float,references.mean(axis=0))))
            else:
                raise ValueError("Fit-only perturbation reference unavailable")

        # Scientific Fault injection state
        self.active_fault: Optional[Dict[str, Any]] = None
        self.last_evidence: Optional[Dict[str, Any]] = None
        self.last_raw_values: Dict[str, float] = {}

    def inject_fault(
        self,
        fault_type: str,
        channel: str,
        start_cycle: int,
        duration: int,
        magnitude: float = 1.0,
        direction: int = 1,
        seed: int = 42,
    ):
        """Configure scientific synthetic perturbation without modifying raw NASA files.
        
        Perturbations use standard deviation scaling from training baseline distributions:
        - stuck_sensor: freezes at the last observed real sensor measurement
        - sensor_drift: linear bias ramp scaled by reference standard deviations
        - missing_data: introduces causal NaN missingness
        - gaussian_noise: zero-mean additive noise scaled by channel standard deviation with seeded RNG
        """
        self.active_fault = {
            "fault_type": fault_type,
            "channel": channel,
            "start_cycle": start_cycle,
            "end_cycle": start_cycle + duration,
            "duration": duration,
            "magnitude": magnitude,
            "direction": direction,
            "seed": seed,
        }
        self.persist()

    def persist(self):
        self.store.save_replay_session(self.session_id,self.dataset,self.engine_id,self.split,
            self.policy_name,self.base_namespace,self.current_index,self.total_cycles,
            "COMPLETED" if self.current_index>=self.total_cycles else "ACTIVE",
            dict(base_namespace=self.base_namespace,reset_epoch=self.reset_epoch,
                 model_release=self.model_release,active_fault=self.active_fault,
                 last_raw_values=self.last_raw_values))

    def _apply_fault_if_active(self, cycle: int, telemetry: Dict[str, float]) -> Tuple[Dict[str, float], bool]:
        """Apply active perturbation and return (effective_telemetry, is_perturbed)."""
        if not self.active_fault:
            return telemetry, False
        f = self.active_fault
        if f["start_cycle"] <= cycle < f["end_cycle"]:
            modified = dict(telemetry)
            ch = f["channel"]
            if ch in modified:
                ch_std = self.sensor_stds.get(ch, 1.0)
                if f["fault_type"] == "stuck_sensor":
                    # Freeze at the last observed genuine sensor reading
                    if "frozen_value" not in f:
                        f["frozen_value"] = self.last_raw_values.get(ch, modified[ch])
                    modified[ch] = f["frozen_value"]
                elif f["fault_type"] == "sensor_drift":
                    # Causal drift ramp: std * 0.1 per elapsed cycle * magnitude * direction
                    elapsed = cycle - f["start_cycle"] + 1
                    drift_offset = elapsed * (0.1 * ch_std) * f["magnitude"] * f["direction"]
                    modified[ch] += drift_offset
                elif f["fault_type"] == "missing_data":
                    # Causal dropout
                    modified[ch] = np.nan
                elif f["fault_type"] == "gaussian_noise":
                    # Seeded Gaussian perturbation scaled to sensor std
                    rng = np.random.default_rng(f["seed"] + cycle)
                    noise = rng.normal(0, ch_std * 0.5 * f["magnitude"])
                    modified[ch] += float(noise)
                return modified, True
        return telemetry, False

    def step(self, count: int = 1) -> List[Dict[str, Any]]:
        """Advance causal telemetry stream by count cycles."""
        results = []
        for _ in range(count):
            if self.current_index >= self.total_cycles:
                break
            row = self.trajectory_df.iloc[self.current_index]
            cycle = int(row["cycle"])
            raw_telemetry = {k: float(row[k]) for k in TELEMETRY_CHANNELS if k in row}
            
            # Record last observed raw values before applying any fault
            # Apply scientific perturbation if active
            effective_telemetry, is_perturbed = self._apply_fault_if_active(cycle, raw_telemetry)
            self.last_raw_values = dict(raw_telemetry)
            
            # Consume strictly causally via CausalReplay
            asset_id = str(self.engine_id)
            decision_record = self.replay.consume(self.engine_id, cycle, effective_telemetry, asset_id=asset_id)
            
            # Retrieve latest checkpoint evidence
            _, state = self.store.get_checkpoint(self.engine_id, asset_id=asset_id)
            event = self.store.get_event(self.engine_id, cycle, asset_id=asset_id)
            pred_evidence = json.loads(event["prediction_json"]) if event and event.get("prediction_json") else {}
            prop_data = json.loads(event["proposal_json"]) if event and event.get("proposal_json") else {}
            
            last_valid = state.get("last_valid") if state else None
            is_usable = bool(last_valid and isinstance(last_valid, dict) and last_valid.get("cycle") == cycle)
            
            evidence = {
                "cycle": cycle,
                "telemetry": effective_telemetry,
                "raw_telemetry": raw_telemetry,
                "is_perturbed": is_perturbed,
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

            # Persist progress position to durable SQLite store
            status = "COMPLETED" if self.current_index >= self.total_cycles else "ACTIVE"
            self.persist()

        return results

    def reset(self):
        """Reset replay session with epoch isolation to guarantee zero event collisions."""
        self.reset_epoch += 1
        self.current_index = 0
        self.last_evidence = None
        self.active_fault = None
        self.last_raw_values = {}
        
        # Fork into a fresh isolated namespace for the new epoch
        self.namespace = f"{self.base_namespace}_ep{self.reset_epoch}"
        self.store = WorkOrderStore(settings.db_path, namespace=self.namespace)
        self.replay = CausalReplay(self.bundle, self.store, self.policy_def)
        
        # Persist reset epoch to database
        self.persist()


class ReplayManager:
    """Manages replay sessions across datasets with durable SQLite backing."""

    def __init__(self):
        self.sessions: Dict[str, ReplaySession] = {}
        self._cache_data: Dict[str, Tuple[pd.DataFrame, pd.DataFrame]] = {}
        self.db_store = WorkOrderStore(settings.db_path, namespace="default")

    def _get_dataset_data(self, dataset: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        dataset = dataset.upper()
        if dataset not in self._cache_data:
            train_df = read_trajectories(settings.data_dir / f"train_{dataset}.txt")
            test_df = read_trajectories(settings.data_dir / f"test_{dataset}.txt")
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
            current_cycle=0,
            reset_epoch=0,
        )
        self.sessions[session_id] = session
        
        # Persist session metadata into durable SQLite store
        self.db_store.save_replay_session(
            session_id=session_id,
            dataset=dataset,
            engine_id=engine_id,
            split=split,
            policy_name=policy_name,
            namespace=ns,
            current_cycle=0,
            total_cycles=session.total_cycles,
            status="ACTIVE",
            config={"split": split, "policy": policy_name, "namespace": ns},
        )
        session.persist()
        return session

    def get_session(self, session_id: str) -> ReplaySession:
        """Retrieve active session, restoring transparently from SQLite if process restarted."""
        if session_id in self.sessions:
            return self.sessions[session_id]
            
        # Cross-process restart recovery: hydrate from SQLite
        sess_record = self.db_store.get_replay_session(session_id)
        if not sess_record:
            raise KeyError(f"Session {session_id} not found")
            
        dataset = sess_record["dataset"]
        engine_id = sess_record["engine_id"]
        split = sess_record["split"]
        policy_name = sess_record["policy_name"]
        config = json.loads(sess_record["config_json"])
        namespace = config.get("base_namespace",sess_record["namespace"])
        current_cycle = sess_record["current_cycle"]
        
        train_df, test_df = self._get_dataset_data(dataset)
        source_df = train_df if split == "train" else test_df
        engine_df = source_df[source_df.engine_id == engine_id]
        
        restored_namespace = f"{namespace}_ep{config.get('reset_epoch',0)}" if config.get('reset_epoch',0) else namespace
        store = WorkOrderStore(settings.db_path, namespace=restored_namespace)
        session = ReplaySession(
            session_id=session_id,
            dataset=dataset,
            engine_id=engine_id,
            split=split,
            policy_name=policy_name,
            namespace=namespace,
            trajectory_df=engine_df,
            store=store,
            current_cycle=current_cycle,
            reset_epoch=config.get("reset_epoch",0),
            model_release=config.get("model_release"),
        )
        session.active_fault = config.get("active_fault")
        session.last_raw_values = config.get("last_raw_values",{})
        checkpoint_cycle,_ = store.get_checkpoint(engine_id,asset_id=str(engine_id))
        if checkpoint_cycle is not None:
            session.current_index = max(current_cycle,checkpoint_cycle)
            current_cycle = session.current_index
        # Rehydrate last evidence if available
        if current_cycle > 0:
            last_event = store.get_event(engine_id, current_cycle)
            if last_event:
                pred_ev = json.loads(last_event["prediction_json"]) if last_event.get("prediction_json") else {}
                prop = json.loads(last_event["proposal_json"]) if last_event.get("proposal_json") else {}
                res = json.loads(last_event["result_json"]) if last_event.get("result_json") else {}
                session.last_evidence = {
                    "cycle": current_cycle,
                    "telemetry": json.loads(last_event["telemetry_json"]),
                    "raw_telemetry": json.loads(last_event["telemetry_json"]),
                    "is_perturbed": False,
                    "prediction": pred_ev.get("prediction"),
                    "usable": bool(pred_ev.get("usable")),
                    "anomaly_score": pred_ev.get("anomaly_score"),
                    "persistence": pred_ev.get("persistence"),
                    "decision": res,
                    "work_order_id": res.get("work_order_id"),
                    "severity": res.get("severity") or prop.get("severity"),
                    "action_type": prop.get("action_type"),
                }
                
        self.sessions[session_id] = session
        return session


# Global singleton manager
replay_manager = ReplayManager()
