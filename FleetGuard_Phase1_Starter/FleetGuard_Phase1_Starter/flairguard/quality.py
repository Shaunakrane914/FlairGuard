"""Causal FD001 measurement checks. Learned support is not a physical limit."""
from dataclasses import dataclass
from numbers import Real
import copy
import numpy as np

ACTIVE_SENSORS = [f"sensor_{i}" for i in (2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17, 20, 21)]
TELEMETRY_CHANNELS = [f"setting_{i}" for i in range(1, 4)] + [f"sensor_{i}" for i in range(1, 22)]

@dataclass
class QualityAssessment:
    is_valid: bool
    quality_code: str
    details: dict

class TelemetryQualityAuditor:
    def __init__(self, bounds_sigma=6.0, stuck_window=10, stuck_atol=0.0, required_channels=None):
        if bounds_sigma <= 0 or stuck_window < 2 or stuck_atol < 0:
            raise ValueError("Invalid quality configuration")
        self.bounds_sigma = bounds_sigma
        self.stuck_window = stuck_window
        self.stuck_atol = stuck_atol
        self.required_channels = list(required_channels or ACTIVE_SENSORS)
        self.nominal_ranges = {}
        self._history = {}
        self._last_cycles = {}

    def fit_reference_ranges(self, train_df):
        self.nominal_ranges = {}
        for sensor in ACTIVE_SENSORS:
            x = train_df[sensor].to_numpy(dtype=float)
            if not len(x) or not np.isfinite(x).all():
                raise ValueError("Reference data must be finite")
            mean, std = float(x.mean()), max(float(x.std()), 1e-3)
            self.nominal_ranges[sensor] = dict(min=mean-self.bounds_sigma*std,
                                              max=mean+self.bounds_sigma*std, mean=mean, std=std)

    def state_for(self, engine_id):
        return copy.deepcopy({"last_cycle": self._last_cycles.get(engine_id),
                              "history": self._history.get(engine_id, [])})

    def restore_state(self, engine_id, state):
        if state.get("last_cycle") is not None:
            self._last_cycles[engine_id] = state["last_cycle"]
        self._history[engine_id] = copy.deepcopy(state.get("history", []))

    def audit_row(self, engine_id, cycle, telemetry_dict):
        if not isinstance(cycle, (int, np.integer)) or isinstance(cycle, bool) or cycle < 1:
            raise ValueError("Cycle must be a positive integer")
        last = self._last_cycles.get(engine_id)
        if last is not None and cycle <= last:
            return QualityAssessment(False, "OUT_OF_ORDER", {"reason": "Earlier/repeated cycle", "last_cycle": last})
        self._last_cycles[engine_id] = int(cycle)
        gap = last is not None and cycle != last + 1
        if gap:
            self._history[engine_id] = []
        missing = [k for k in self.required_channels if k not in telemetry_dict]
        invalid = [k for k, v in telemetry_dict.items()
                   if not isinstance(v, Real) or isinstance(v, bool) or not np.isfinite(v)]
        if missing or invalid:
            self._history[engine_id] = []
            return QualityAssessment(False, "MISSING_DATA", {"reason": "Absent/nonfinite/nonnumeric channel",
                                                             "missing": missing, "invalid": invalid})
        history = self._history.setdefault(engine_id, [])
        history.append({"cycle": int(cycle), **{s: float(telemetry_dict[s]) for s in ACTIVE_SENSORS}})
        del history[:-self.stuck_window]
        reasons = ["CYCLE_GAP"] if gap else []
        outside = [s for s, b in self.nominal_ranges.items()
                   if not b["min"] <= telemetry_dict[s] <= b["max"]]
        if outside:
            reasons.append("OUT_OF_REFERENCE")
        stuck = []
        if len(history) == self.stuck_window:
            for s in ACTIVE_SENSORS:
                vals = np.asarray([r[s] for r in history])
                if np.allclose(vals, vals[0], atol=self.stuck_atol, rtol=0.0):
                    stuck.append(s)
        if stuck:
            reasons.append("STUCK_SENSOR")
        return QualityAssessment(not reasons, reasons[0] if reasons else "NOMINAL",
                                 {"reason": ",".join(reasons) if reasons else "Checks passed; health not certified",
                                  "codes": reasons, "outside_reference": outside, "stuck": stuck})
