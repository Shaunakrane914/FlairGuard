"""Telemetry Data Quality & Fault Separation for FlairGuard AI.

Separates raw telemetry quality defects (stuck sensors, missing data, physical envelope
violations) from physical engine degradation anomalies.
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd

# Active varying sensors in NASA C-MAPSS FD001 (excluding constant simulation channels)
ACTIVE_SENSORS = [
    "sensor_2", "sensor_3", "sensor_4", "sensor_7", "sensor_8",
    "sensor_9", "sensor_11", "sensor_12", "sensor_13", "sensor_14",
    "sensor_15", "sensor_17", "sensor_20", "sensor_21"
]


@dataclass
class QualityAssessment:
    is_valid: bool
    quality_code: str  # NOMINAL, MISSING_DATA, IRREGULAR_CYCLE, STUCK_SENSOR, OUT_OF_BOUNDS
    details: Dict[str, Any]


class TelemetryQualityAuditor:
    """Audits incoming sensor telemetry streams for data acquisition and instrumentation faults."""

    def __init__(self, bounds_sigma: float = 6.0, stuck_window: int = 5):
        self.bounds_sigma = bounds_sigma
        self.stuck_window = stuck_window
        self.nominal_ranges: Dict[str, Dict[str, float]] = {}
        self._history: Dict[int, List[Dict[str, float]]] = {}  # engine_id -> list of recent cycles

    def fit_reference_ranges(self, train_df: pd.DataFrame):
        """Learn physical telemetry envelope (mean +/- k*sigma) from nominal training data."""
        self.nominal_ranges.clear()
        for s in ACTIVE_SENSORS:
            vals = train_df[s].to_numpy()
            mean = float(np.mean(vals))
            std = float(np.std(vals))
            std = max(std, 1e-3)
            self.nominal_ranges[s] = {
                "min": mean - self.bounds_sigma * std,
                "max": mean + self.bounds_sigma * std,
                "mean": mean,
                "std": std,
            }

    def audit_row(self, engine_id: int, cycle: int, telemetry_dict: Dict[str, float]) -> QualityAssessment:
        """Audit a single cycle of telemetry for an engine."""
        # 1. Missing or non-finite values
        for k, v in telemetry_dict.items():
            if not np.isfinite(v):
                return QualityAssessment(
                    is_valid=False,
                    quality_code="MISSING_DATA",
                    details={"channel": k, "value": v, "reason": "Non-finite or missing telemetry value"}
                )

        # 2. Cycle sequence monotonicity check
        if engine_id in self._history and len(self._history[engine_id]) > 0:
            last_cycle = self._history[engine_id][-1]["cycle"]
            if cycle <= last_cycle or cycle > last_cycle + 1:
                return QualityAssessment(
                    is_valid=False,
                    quality_code="IRREGULAR_CYCLE",
                    details={"last_cycle": last_cycle, "current_cycle": cycle, "reason": "Non-consecutive cycle sequence"}
                )

        # 3. Physical envelope / out-of-bounds check
        if self.nominal_ranges:
            for s in ACTIVE_SENSORS:
                if s in telemetry_dict:
                    val = telemetry_dict[s]
                    b = self.nominal_ranges[s]
                    if val < b["min"] or val > b["max"]:
                        return QualityAssessment(
                            is_valid=False,
                            quality_code="OUT_OF_BOUNDS",
                            details={
                                "sensor": s,
                                "value": val,
                                "expected_min": round(b["min"], 3),
                                "expected_max": round(b["max"], 3),
                                "reason": "Value outside physical operational envelope"
                            }
                        )

        # 4. Stuck sensor flatline check (across rolling buffer)
        if engine_id not in self._history:
            self._history[engine_id] = []
        
        row_entry = {"cycle": cycle}
        row_entry.update({s: telemetry_dict.get(s, 0.0) for s in ACTIVE_SENSORS})
        self._history[engine_id].append(row_entry)

        # Keep buffer bounded
        if len(self._history[engine_id]) > self.stuck_window:
            self._history[engine_id].pop(0)

        if len(self._history[engine_id]) >= self.stuck_window:
            buf = self._history[engine_id]
            for s in ACTIVE_SENSORS:
                vals = [entry[s] for entry in buf]
                if np.allclose(vals, vals[0], atol=1e-7):
                    return QualityAssessment(
                        is_valid=False,
                        quality_code="STUCK_SENSOR",
                        details={
                            "sensor": s,
                            "stuck_value": vals[0],
                            "window_cycles": self.stuck_window,
                            "reason": f"Sensor flatlined identically across {self.stuck_window} consecutive cycles"
                        }
                    )

        return QualityAssessment(is_valid=True, quality_code="NOMINAL", details={})

