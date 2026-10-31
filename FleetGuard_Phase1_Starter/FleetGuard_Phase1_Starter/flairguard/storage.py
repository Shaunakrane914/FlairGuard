"""Persistent SQLite Storage and Audit Trail for FlairGuard AI Work Orders.

Enforces:
- Idempotent work order generation
- Duplicate suppression (prevents alert storms)
- Severity escalation (e.g. MEDIUM -> HIGH -> CRITICAL)
- Complete immutable audit logging with explicit decision rationale
"""
import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List

SEVERITY_RANKS = {
    "NORMAL": 0,
    "MEDIUM": 1,
    "HIGH": 2,
    "CRITICAL": 3,
    "ESCALATE_HUMAN": 3,
}


class WorkOrderStore:
    """Manages persistent SQLite tables for maintenance work orders and audit logs."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS work_orders (
                    work_order_id TEXT PRIMARY KEY,
                    engine_id INTEGER NOT NULL,
                    cycle INTEGER NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    predicted_rul REAL NOT NULL,
                    uncertainty REAL NOT NULL,
                    anomaly_score REAL NOT NULL,
                    persistence_count INTEGER NOT NULL,
                    decision_reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    engine_id INTEGER NOT NULL,
                    cycle INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    work_order_id TEXT,
                    decision_reason TEXT NOT NULL,
                    telemetry_snapshot_json TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wo_engine_status ON work_orders (engine_id, status)")
            conn.commit()

    def get_active_work_order(self, engine_id: int) -> Optional[Dict[str, Any]]:
        """Return the current active (OPEN or ACKNOWLEDGED) work order for an engine if one exists."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM work_orders 
                WHERE engine_id = ? AND status IN ('OPEN', 'ACKNOWLEDGED')
                ORDER BY updated_at DESC LIMIT 1
            """, (engine_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def record_decision(
        self,
        engine_id: int,
        cycle: int,
        severity: str,
        action_type: str,
        predicted_rul: float,
        uncertainty: float,
        anomaly_score: float,
        persistence_count: int,
        decision_reason: str,
        telemetry_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record a triage decision idempotently, handling deduplication and escalation."""
        now_iso = datetime.now(timezone.utc).isoformat()
        snapshot_json = json.dumps(telemetry_snapshot or {})
        
        # Nominal operational state without active work order requires no open order
        if severity == "NORMAL" and action_type == "MONITOR":
            active = self.get_active_work_order(engine_id)
            if not active:
                return {"status": "NOOP", "reason": "Nominal telemetry"}

        active = self.get_active_work_order(engine_id)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if active:
                active_id = active["work_order_id"]
                current_rank = SEVERITY_RANKS.get(active["severity"], 0)
                new_rank = SEVERITY_RANKS.get(severity, 0)
                
                # Check if severity has escalated
                if new_rank > current_rank:
                    cursor.execute("""
                        UPDATE work_orders
                        SET cycle = ?, severity = ?, action_type = ?, predicted_rul = ?,
                            uncertainty = ?, anomaly_score = ?, persistence_count = ?,
                            decision_reason = ?, updated_at = ?
                        WHERE work_order_id = ?
                    """, (
                        cycle, severity, action_type, predicted_rul, uncertainty,
                        anomaly_score, persistence_count, decision_reason, now_iso, active_id
                    ))
                    cursor.execute("""
                        INSERT INTO audit_log (engine_id, cycle, event_type, work_order_id, decision_reason, telemetry_snapshot_json, timestamp)
                        VALUES (?, ?, 'SEVERITY_ESCALATED', ?, ?, ?, ?)
                    """, (engine_id, cycle, active_id, f"Escalated from {active['severity']} to {severity}: {decision_reason}", snapshot_json, now_iso))
                    conn.commit()
                    return {"status": "ESCALATED", "work_order_id": active_id, "severity": severity}
                else:
                    # Duplicate suppression
                    cursor.execute("""
                        INSERT INTO audit_log (engine_id, cycle, event_type, work_order_id, decision_reason, telemetry_snapshot_json, timestamp)
                        VALUES (?, ?, 'DUPLICATE_SUPPRESSED', ?, ?, ?, ?)
                    """, (engine_id, cycle, active_id, f"Suppressed duplicate alert at cycle {cycle}. Existing active {active['severity']} order maintained.", snapshot_json, now_iso))
                    conn.commit()
                    return {"status": "SUPPRESSED", "work_order_id": active_id, "severity": active["severity"]}
            else:
                # Create brand new work order
                wo_id = f"WO-E{engine_id:03d}-C{cycle:03d}"
                cursor.execute("""
                    INSERT INTO work_orders (
                        work_order_id, engine_id, cycle, severity, status, action_type,
                        predicted_rul, uncertainty, anomaly_score, persistence_count,
                        decision_reason, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    wo_id, engine_id, cycle, severity, action_type,
                    predicted_rul, uncertainty, anomaly_score, persistence_count,
                    decision_reason, now_iso, now_iso
                ))
                event_type = "HUMAN_ESCALATION" if severity == "ESCALATE_HUMAN" else "WORK_ORDER_CREATED"
                cursor.execute("""
                    INSERT INTO audit_log (engine_id, cycle, event_type, work_order_id, decision_reason, telemetry_snapshot_json, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (engine_id, cycle, event_type, wo_id, decision_reason, snapshot_json, now_iso))
                conn.commit()
                return {"status": "CREATED", "work_order_id": wo_id, "severity": severity}

    def close_work_order(self, work_order_id: str, reason: str = "Servicing completed"):
        """Close an active work order and write to audit trail."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT engine_id, cycle FROM work_orders WHERE work_order_id = ?", (work_order_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Work order {work_order_id} not found")
            cursor.execute("UPDATE work_orders SET status = 'CLOSED', updated_at = ? WHERE work_order_id = ?", (now_iso, work_order_id))
            cursor.execute("""
                INSERT INTO audit_log (engine_id, cycle, event_type, work_order_id, decision_reason, timestamp)
                VALUES (?, ?, 'STATUS_CHANGED', ?, ?, ?)
            """, (row["engine_id"], row["cycle"], work_order_id, f"Work order CLOSED: {reason}", now_iso))
            conn.commit()

    def get_all_work_orders(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM work_orders ORDER BY created_at DESC")
            return [dict(r) for r in cursor.fetchall()]

    def get_audit_trail(self, engine_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if engine_id is not None:
                cursor.execute("SELECT * FROM audit_log WHERE engine_id = ? ORDER BY log_id ASC", (engine_id,))
            else:
                cursor.execute("SELECT * FROM audit_log ORDER BY log_id ASC")
            return [dict(r) for r in cursor.fetchall()]

