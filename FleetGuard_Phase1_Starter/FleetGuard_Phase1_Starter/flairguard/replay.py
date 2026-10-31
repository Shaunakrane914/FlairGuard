"""Causal inference and transactional replay; no future labels in this module."""
from dataclasses import asdict
import json
import math
import numpy as np
import pandas as pd
from .evidence import digest
from .features import RAW_FEATURES, SENSORS
from .quality import TelemetryQualityAuditor, TELEMETRY_CHANNELS, ACTIVE_SENSORS
from .storage import WorkOrderStore, EventConflict, OutOfOrder
from .triage import Proposal


def prefix_features(history):
    """One shared feature contract for available raw prefixes, rounded to 10dp."""
    row = history[-1]
    values = {k: row[k] for k in RAW_FEATURES}
    for sensor in SENSORS:
        for window in (5, 20):
            values[f"{sensor}_mean_{window}"] = float(np.mean([r[sensor] for r in history[-window:]]))
    return {k: float(np.round(v, 10)) for k, v in values.items()}


class InferenceEngine:
    def __init__(self, bundle):
        self.bundle = bundle

    def observe(self, engine_id, cycle, telemetry, state=None):
        state = dict(state or {})
        if set(telemetry) - set(TELEMETRY_CHANNELS):
            raise ValueError("Unexpected telemetry keys; labels/engine lifetime cannot enter inference")
        last = state.get("last_cycle")
        if last is not None and cycle <= last:
            raise OutOfOrder("Inference requires increasing cycles")
        qcfg = self.bundle.get("quality_config", {"bounds_sigma": 6.0, "stuck_window": 5})
        auditor = TelemetryQualityAuditor(**qcfg, required_channels=TELEMETRY_CHANNELS)
        auditor.nominal_ranges = self.bundle.get("quality_ranges", {})
        auditor.restore_state(engine_id, state.get("quality", {}))
        quality = auditor.audit_row(engine_id, cycle, telemetry)
        history = list(state.get("history", []))
        if last is not None and cycle != last + 1:
            history = []
        finite = len(telemetry) == len(TELEMETRY_CHANNELS) and all(
            isinstance(v, (float, int, np.number)) and not isinstance(v, bool) and math.isfinite(v)
            for v in telemetry.values())
        if finite:
            history.append({"cycle": cycle, **{k: float(v) for k, v in telemetry.items()}})
            history = history[-20:]
        else:
            history = []
        prediction = raw_prediction = score = None
        feature_hash = None
        if history:
            if "models" in self.bundle:
                selected_name = self.bundle.get("selected", "RegimeLightGBM")
                regime_model = self.bundle["models"][selected_name]
                df_obs = pd.DataFrame(history)
                df_obs["engine_id"] = engine_id
                preds, diag = regime_model.predict(df_obs)
                raw_prediction = float(preds[-1])
                prediction = float(np.clip(raw_prediction, 0, 125))
                feature_hash = digest(history[-1])
            else:
                features = prefix_features(history)
                if list(features) != self.bundle["features"]:
                    raise ValueError("Feature schema mismatch")
                X = pd.DataFrame([features], columns=self.bundle["features"])
                raw_prediction = float(self.bundle["model"].predict(X)[0])
                if not math.isfinite(raw_prediction):
                    raise ValueError("Nonfinite model output")
                prediction = float(np.clip(raw_prediction, 0, self.bundle.get("rul_cap", 125)))
                feature_hash = digest(features)
        threshold = None
        det = self.bundle.get("detector")
        if finite and det is not None:
            x = np.array([[telemetry[s] for s in ACTIVE_SENSORS if s in telemetry]], dtype=float)
            score = float(det.compute_raw_score(x)[0])
            threshold = det.threshold
        persistent = (state.get("persistence", 0) + 1 if last is not None and cycle == last + 1 else 1)
        if score is None or threshold is None or score < threshold or not quality.is_valid:
            persistent = 0
        min_hist = self.bundle.get("min_history", 20)
        usable = quality.is_valid and len(history) >= min_hist and prediction is not None
        previous_valid = state.get("last_valid")
        last_valid = {"cycle": cycle, "prediction": prediction} if usable else previous_valid
        q = self.bundle.get("interval_q")
        evidence = dict(engine_id=engine_id, cycle=cycle, prediction=prediction, raw_prediction=raw_prediction,
                        lower=max(0, prediction - q) if usable and q is not None else None,
                        upper=prediction + q if usable and q is not None else None,
                        interval_scope="clean frozen endpoints only; not a confidence ranking",
                        usable=bool(usable), history_length=len(history), quality=asdict(quality),
                        anomaly_score=score, anomaly_threshold=threshold,
                        persistence=persistent, features_hash=feature_hash,
                        model_id=self.bundle["model_id"], bundle_sha256=self.bundle.get("artifact_sha256"))
        new_state = dict(last_cycle=cycle, history=history, quality=auditor.state_for(engine_id),
                         persistence=persistent, last_valid=last_valid)
        return evidence, new_state


def policy_proposal(evidence, state, policy):
    cycle = evidence["cycle"]
    if policy["kind"] == "none":
        return Proposal("NORMAL", "NORMAL", False, "MONITOR", "Run-to-failure comparator")
    if policy["kind"] == "fixed":
        if cycle >= policy["fixed_age"]:
            return Proposal("HIGH", "HIGH", False, "WORK_ORDER_SCHEDULE_MAINTENANCE", "Frozen fit-OOF age baseline")
        return Proposal("NORMAL", "NORMAL", False, "MONITOR", "Fixed-age comparator waiting")
    if cycle < policy["min_history"]:
        return Proposal("NORMAL", "NORMAL", False, "MONITOR", "Initial declared observation warm-up")
    point = evidence["prediction"] if evidence["history_length"] >= policy["min_history"] else None
    invalid = not evidence["usable"] if policy["kind"] in ("gate", "quality_gate", "learned_gate", "quality_decision") else point is None
    if invalid:
        last = state.get("last_valid")
        stale = cycle - last["cycle"] if last else None
        if policy["kind"] == "point" and last and stale <= policy["stale_limit"]:
            point = max(0, last["prediction"] - stale)
        else:
            urgent = evidence["prediction"] is not None and evidence["prediction"] <= policy["critical_threshold"]
            return Proposal("CRITICAL" if urgent else "ESCALATE_HUMAN", "CRITICAL" if urgent else "MEDIUM",
                            True, "ESCALATE_HUMAN_DATA_FAULT", "Validity/referral fallback; inspection is not perfect information")
    if point is not None and point <= policy["threshold"]:
        priority = "CRITICAL" if point <= policy["critical_threshold"] else "HIGH"
        return Proposal(priority, priority, False, "WORK_ORDER_SCHEDULE_MAINTENANCE", "Frozen fit-OOF RUL threshold")
    return Proposal("NORMAL", "NORMAL", False, "MONITOR", "RUL threshold not reached; no health certification")


class CausalReplay:
    def __init__(self, bundle, store, policy):
        self.inference = InferenceEngine(bundle)
        self.store = store
        self.policy = dict(policy)
        self.model_id = bundle["model_id"]
        self.policy_id = digest(policy)
        self.store.bind_context(dict(model_id=self.model_id, bundle_sha256=bundle.get("artifact_sha256"),
                                     policy=policy, protocol_hash=bundle["protocol_hash"]))

    def consume(self, engine_id, cycle, telemetry, asset_id=None):
        ih = digest(dict(engine_id=engine_id, cycle=cycle, telemetry=telemetry, model_id=self.model_id, policy_id=self.policy_id))
        prior = self.store.get_event(engine_id, cycle, asset_id)
        if prior:
            if prior["input_hash"] != ih:
                raise EventConflict("Conflicting retry of an observed event")
            return json.loads(prior["result_json"])
        last, state = self.store.get_checkpoint(engine_id, asset_id)
        if last is not None and cycle <= last:
            raise OutOfOrder("Older uncommitted cycle")
        evidence, new_state = self.inference.observe(engine_id, cycle, telemetry, state)
        proposal = policy_proposal(evidence, state, self.policy)
        return self.store.record_decision(engine_id, cycle, proposal.severity, proposal.action_type,
                evidence["prediction"], None, evidence["anomaly_score"], evidence["persistence"], proposal.reason,
                telemetry, asset_id=asset_id, priority=proposal.priority, review_required=proposal.review_required,
                checkpoint=new_state, prediction_evidence=evidence, model_id=self.model_id, policy_id=self.policy_id,
                input_hash=ih, expected_previous_cycle=last, lead_time=self.policy["lead_time"],
                review_delay=self.policy["review_delay"])


def simulate_episode(replay, engine_id, observations, failure_cycle, restart_factory=None):
    """Evaluator boundary: future failure time is NEVER passed to replay/policy."""
    for observation in observations:
        cycle = int(observation["cycle"])
        if cycle >= failure_cycle:
            replay.store.record_failure(engine_id, failure_cycle)
            break
        replay.store.execute_due(engine_id, cycle, lead_time=replay.policy["lead_time"])
        with replay.store._get_connection() as c:
            ended = c.execute("SELECT 1 FROM episode_outcomes WHERE namespace=? AND asset_id=?",
                              (replay.store.namespace, str(engine_id))).fetchone()
        if ended:
            break
        telemetry = {k: observation.get(k) for k in TELEMETRY_CHANNELS}
        replay.consume(engine_id, cycle, telemetry)
        if restart_factory is not None and cycle == 60:
            replay.store.close()
            replay = restart_factory()
    return replay
