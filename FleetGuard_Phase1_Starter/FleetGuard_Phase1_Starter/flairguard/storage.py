"""Transactional Phase A event, order and simulated-execution ledger.

Legacy databases are deliberately refused, never migrated in place. Review is a
separate flag from urgency. Proposals, commitments and executions are distinct.
"""
import json
import math
import sqlite3
import threading
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path
from .evidence import canonical, digest

SEVERITY_RANKS = {"NORMAL": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3, "ESCALATE_HUMAN": 1}
MAINTENANCE_ACTIONS = {"WORK_ORDER_IMMEDIATE_OVERHAUL", "WORK_ORDER_SCHEDULE_MAINTENANCE"}
ACTIVE = "('OPEN','ACKNOWLEDGED','IN_PROGRESS')"

class EventConflict(ValueError):
    pass

class OutOfOrder(ValueError):
    pass

class ConcurrentUpdate(ValueError):
    pass


def finalize_ledger(db_path):
    """Seal a completed, exclusively owned ledger into one stable artifact.

    Call only after every replay store is closed. A busy reader/writer fails
    finalization rather than allowing a manifest of mutable WAL/SHM files.
    """
    with closing(sqlite3.connect(db_path, timeout=30)) as conn:
        checkpoint=conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
        if checkpoint[0]:
            raise RuntimeError('Ledger still busy; cannot finalize evidence')
        if conn.execute('PRAGMA journal_mode=DELETE').fetchone()[0].lower()!='delete':
            raise RuntimeError('Ledger did not enter stable standalone mode')
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('Cannot finalize corrupt ledger')


class WorkOrderStore:
    def __init__(self, db_path, namespace="default"):
        self.db_path = Path(db_path)
        self.namespace = namespace
        self._lock = threading.RLock()
        if self.db_path.exists() and self.db_path.stat().st_size:
            with closing(sqlite3.connect(self.db_path.resolve().as_uri()+"?mode=ro", uri=True)) as old:
                names = {r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if names and "phase_a_meta" not in names:
                    raise ValueError("Historical/legacy database protected: use a new Phase A database path")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS phase_a_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        INSERT OR IGNORE INTO phase_a_meta VALUES('schema_version','1');
        CREATE TABLE IF NOT EXISTS contexts(namespace TEXT PRIMARY KEY,context_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS asset_state(namespace TEXT,asset_id TEXT,last_cycle INTEGER NOT NULL,
            checkpoint_json TEXT NOT NULL,PRIMARY KEY(namespace,asset_id));
        CREATE TABLE IF NOT EXISTS replay_sessions(
            session_id TEXT PRIMARY KEY,
            dataset TEXT NOT NULL,
            engine_id INTEGER NOT NULL,
            split TEXT NOT NULL,
            policy_name TEXT NOT NULL,
            namespace TEXT NOT NULL,
            current_cycle INTEGER NOT NULL,
            total_cycles INTEGER NOT NULL,
            status TEXT NOT NULL,
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS training_jobs(
            job_id TEXT PRIMARY KEY,
            dataset TEXT NOT NULL,
            challenger_algorithm TEXT NOT NULL,
            status TEXT NOT NULL,
            gate_passed INTEGER NOT NULL,
            promoted INTEGER NOT NULL,
            previous_rmse REAL,
            new_rmse REAL,
            improvement_pct REAL,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT);
        CREATE TABLE IF NOT EXISTS decision_events(
            event_id TEXT PRIMARY KEY,namespace TEXT NOT NULL,asset_id TEXT NOT NULL,engine_id INTEGER NOT NULL,
            cycle INTEGER NOT NULL,input_hash TEXT NOT NULL,telemetry_json TEXT NOT NULL,
            proposal_json TEXT NOT NULL,prediction_json TEXT NOT NULL,result_json TEXT NOT NULL,
            checkpoint_json TEXT NOT NULL,model_id TEXT NOT NULL,policy_id TEXT NOT NULL,
            UNIQUE(namespace,asset_id,cycle));
        CREATE TABLE IF NOT EXISTS work_orders(
            work_order_id TEXT PRIMARY KEY,namespace TEXT NOT NULL,asset_id TEXT NOT NULL,engine_id INTEGER NOT NULL,
            cycle INTEGER NOT NULL,severity TEXT NOT NULL,priority TEXT NOT NULL,
            review_required INTEGER NOT NULL CHECK(review_required IN (0,1)),
            status TEXT NOT NULL CHECK(status IN ('OPEN','ACKNOWLEDGED','IN_PROGRESS','CLOSED','CANCELLED')),
            action_type TEXT NOT NULL,predicted_rul REAL,uncertainty REAL,anomaly_score REAL,
            persistence_count INTEGER NOT NULL,decision_reason TEXT NOT NULL,
            due_cycle INTEGER,review_due_cycle INTEGER,event_id TEXT NOT NULL REFERENCES decision_events(event_id),
            row_version INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_order ON work_orders(namespace,asset_id)
            WHERE status IN ('OPEN','ACKNOWLEDGED','IN_PROGRESS');
        CREATE TABLE IF NOT EXISTS audit_log(log_id INTEGER PRIMARY KEY,namespace TEXT NOT NULL,
            engine_id INTEGER NOT NULL,cycle INTEGER NOT NULL,event_type TEXT NOT NULL,
            work_order_id TEXT REFERENCES work_orders(work_order_id),event_id TEXT,
            decision_reason TEXT NOT NULL,telemetry_snapshot_json TEXT,timestamp TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS executions(execution_id TEXT PRIMARY KEY,namespace TEXT NOT NULL,
            asset_id TEXT NOT NULL,engine_id INTEGER NOT NULL,cycle INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('INSPECTION','MAINTENANCE')),
            work_order_id TEXT NOT NULL REFERENCES work_orders(work_order_id),
            event_id TEXT NOT NULL REFERENCES decision_events(event_id),
            UNIQUE(work_order_id,kind));
        CREATE TABLE IF NOT EXISTS episode_outcomes(namespace TEXT,asset_id TEXT,engine_id INTEGER,
            cycle INTEGER NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('FAILURE','MAINTENANCE')),
            PRIMARY KEY(namespace,asset_id));
        """)
        self.conn.commit()

    def close(self):
        with self._lock:
            if self.conn is not None:
                self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                self.conn.close()
                self.conn = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    @contextmanager
    def _get_connection(self, write=False):
        with self._lock:
            try:
                if write:
                    self.conn.execute("BEGIN IMMEDIATE")
                yield self.conn
                if write:
                    self.conn.commit()
            except Exception:
                if write:
                    self.conn.rollback()
                raise

    def bind_context(self, context):
        data = canonical(context)
        with self._get_connection(True) as c:
            row = c.execute("SELECT context_json FROM contexts WHERE namespace=?", (self.namespace,)).fetchone()
            if row and row[0] != data:
                raise EventConflict("Namespace already pinned to a different model/policy/context")
            c.execute("INSERT OR IGNORE INTO contexts VALUES(?,?)", (self.namespace, data))

    def get_event(self, engine_id, cycle, asset_id=None):
        with self._get_connection() as c:
            r = c.execute("SELECT * FROM decision_events WHERE namespace=? AND asset_id=? AND cycle=?",
                          (self.namespace, asset_id or str(engine_id), cycle)).fetchone()
            return dict(r) if r else None

    def get_checkpoint(self, engine_id, asset_id=None):
        with self._get_connection() as c:
            row = c.execute("SELECT * FROM asset_state WHERE namespace=? AND asset_id=?",
                            (self.namespace, asset_id or str(engine_id))).fetchone()
            return (row['last_cycle'], json.loads(row['checkpoint_json'])) if row else (None, {})

    def get_active_work_order(self, engine_id, asset_id=None):
        with self._get_connection() as c:
            row = c.execute(f"SELECT * FROM work_orders WHERE namespace=? AND asset_id=? AND status IN {ACTIVE}",
                            (self.namespace, asset_id or str(engine_id))).fetchone()
            return dict(row) if row else None

    def _audit(self, c, engine_id, cycle, kind, order_id, event_id, reason, telemetry=None):
        c.execute("""INSERT INTO audit_log(namespace,engine_id,cycle,event_type,work_order_id,event_id,
                  decision_reason,telemetry_snapshot_json,timestamp) VALUES(?,?,?,?,?,?,?,?,?)""",
                  (self.namespace,engine_id,cycle,kind,order_id,event_id,reason,canonical(telemetry or {}),
                   datetime.now(timezone.utc).isoformat()))

    def record_decision(self, engine_id, cycle, severity, action_type, predicted_rul, uncertainty,
                        anomaly_score, persistence_count, decision_reason, telemetry_snapshot=None,
                        *, asset_id=None, priority=None, review_required=False, checkpoint=None,
                        prediction_evidence=None, model_id="legacy-caller", policy_id="legacy-caller",
                        input_hash=None, expected_previous_cycle="unchecked", lead_time=5, review_delay=2):
        if severity not in SEVERITY_RANKS or not isinstance(cycle, int) or isinstance(cycle,bool) or cycle < 1:
            raise ValueError("Invalid severity/cycle")
        for value in (predicted_rul, uncertainty, anomaly_score):
            if value is not None and not math.isfinite(value):
                raise ValueError("Nonfinite decision value; use explicit unavailable/null")
        if lead_time < 1 or review_delay < 1:
            raise ValueError("Lead/review delays must be positive")
        asset = asset_id or str(engine_id)
        priority = priority or ("MEDIUM" if severity == "ESCALATE_HUMAN" else severity)
        if priority not in {'NORMAL','MEDIUM','HIGH','CRITICAL'}:
            raise ValueError("Invalid priority")
        review_required = bool(review_required or severity == "ESCALATE_HUMAN")
        proposal = dict(severity=severity,priority=priority,review_required=review_required,action_type=action_type,
                        predicted_rul=predicted_rul,uncertainty=uncertainty,anomaly_score=anomaly_score,
                        persistence_count=persistence_count,decision_reason=decision_reason)
        telemetry = telemetry_snapshot or {}
        ih = input_hash or digest(dict(engine_id=engine_id,cycle=cycle,telemetry=telemetry,proposal=proposal,model_id=model_id,policy_id=policy_id))
        event_id = digest([self.namespace,asset,cycle])
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection(True) as c:
            prior = c.execute("SELECT * FROM decision_events WHERE event_id=?", (event_id,)).fetchone()
            if prior:
                if prior['input_hash'] != ih:
                    raise EventConflict("Different input at an already committed cycle")
                return json.loads(prior['result_json'])
            state = c.execute("SELECT last_cycle FROM asset_state WHERE namespace=? AND asset_id=?",(self.namespace,asset)).fetchone()
            last = state[0] if state else None
            if last is not None and cycle <= last:
                raise OutOfOrder("Uncommitted older event cannot mutate current state")
            if expected_previous_cycle != "unchecked" and last != expected_previous_cycle:
                raise ConcurrentUpdate("Checkpoint changed; recompute and retry the event")
            if c.execute("SELECT 1 FROM episode_outcomes WHERE namespace=? AND asset_id=?",(self.namespace,asset)).fetchone():
                raise EventConflict("Episode already ended")
            # Insert placeholder before order foreign key, then fill result in the same transaction.
            c.execute("INSERT INTO decision_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (event_id,self.namespace,asset,engine_id,cycle,ih,canonical(telemetry),canonical(proposal),
                       canonical(prediction_evidence or {}),'{}',canonical({'state_sha256':digest(checkpoint or {})}),model_id,policy_id))
            active = c.execute(f"SELECT * FROM work_orders WHERE namespace=? AND asset_id=? AND status IN {ACTIVE}",
                               (self.namespace,asset)).fetchone()
            actionable = action_type != 'MONITOR'
            result = dict(status='NOOP',event_id=event_id,work_order_id=None,severity=severity,priority=priority)
            if active:
                result.update(status='SUPPRESSED',work_order_id=active['work_order_id'])
                higher = SEVERITY_RANKS[priority] > SEVERITY_RANKS[active['priority']]
                material = higher or (actionable and review_required and not active['review_required'] and active['action_type'] not in MAINTENANCE_ACTIONS)
                # A valid maintenance authorization may replace a review-only task at equal priority.
                material |= action_type in MAINTENANCE_ACTIONS and active['action_type'] not in MAINTENANCE_ACTIONS
                if material:
                    new_priority = priority if higher else active['priority']
                    # A review request never cancels an already authorized maintenance action.
                    new_action = active['action_type'] if active['action_type'] in MAINTENANCE_ACTIONS and action_type not in MAINTENANCE_ACTIONS else action_type
                    review = review_required if new_action == action_type else bool(active['review_required'])
                    due = active['due_cycle']
                    if new_action in MAINTENANCE_ACTIONS:
                        due = min(due,cycle+lead_time) if due is not None else cycle+lead_time
                    review_due = cycle+review_delay if review else None
                    c.execute("""UPDATE work_orders SET cycle=?,severity=?,priority=?,review_required=?,action_type=?,
                              predicted_rul=?,uncertainty=?,anomaly_score=?,persistence_count=?,decision_reason=?,
                              due_cycle=?,review_due_cycle=?,event_id=?,row_version=row_version+1,updated_at=? WHERE work_order_id=?""",
                              (cycle,new_priority,new_priority,int(review),new_action,predicted_rul,uncertainty,anomaly_score,
                               persistence_count,decision_reason,due,review_due,event_id,now,active['work_order_id']))
                    self._audit(c,engine_id,cycle,'SEVERITY_ESCALATED' if higher else 'ORDER_UPDATED',active['work_order_id'],event_id,decision_reason,telemetry)
                    result.update(status='ESCALATED' if higher else 'UPDATED',priority=new_priority)
            elif actionable:
                oid = 'WO-'+event_id[:24]
                due = cycle+lead_time if action_type in MAINTENANCE_ACTIONS else None
                rdue = cycle+review_delay if review_required else None
                c.execute("""INSERT INTO work_orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (oid,self.namespace,asset,engine_id,cycle,severity,priority,int(review_required),'OPEN',action_type,
                           predicted_rul,uncertainty,anomaly_score,persistence_count,decision_reason,due,rdue,event_id,1,now,now))
                self._audit(c,engine_id,cycle,'HUMAN_ESCALATION' if review_required else 'WORK_ORDER_CREATED',oid,event_id,decision_reason,telemetry)
                result.update(status='CREATED',work_order_id=oid)
            if result['work_order_id']:
                committed = c.execute("SELECT priority,review_required,status,action_type,due_cycle,row_version,event_id FROM work_orders WHERE work_order_id=?",(result['work_order_id'],)).fetchone()
                result['committed_order'] = dict(committed)
            c.execute("UPDATE decision_events SET result_json=? WHERE event_id=?",(canonical(result),event_id))
            c.execute("INSERT INTO asset_state VALUES(?,?,?,?) ON CONFLICT(namespace,asset_id) DO UPDATE SET last_cycle=excluded.last_cycle,checkpoint_json=excluded.checkpoint_json",
                      (self.namespace,asset,cycle,canonical(checkpoint or {})))
            return result

    def execute_due(self, engine_id, cycle, asset_id=None, lead_time=5):
        """Simulated executor. Caller must check failure boundary BEFORE invoking."""
        asset = asset_id or str(engine_id)
        with self._get_connection(True) as c:
            if c.execute("SELECT 1 FROM episode_outcomes WHERE namespace=? AND asset_id=?",(self.namespace,asset)).fetchone():
                return []
            row = c.execute(f"SELECT * FROM work_orders WHERE namespace=? AND asset_id=? AND status IN {ACTIVE}",(self.namespace,asset)).fetchone()
            if not row:
                return []
            if cycle < row['cycle']:
                raise OutOfOrder("Execution cannot precede its commitment")
            made = []
            if row['review_required'] and row['review_due_cycle'] <= cycle:
                xid = digest([row['work_order_id'],'INSPECTION'])
                c.execute("INSERT INTO executions VALUES(?,?,?,?,?,?,?,?)",(xid,self.namespace,asset,engine_id,cycle,'INSPECTION',row['work_order_id'],row['event_id']))
                # Explicit hypothetical fallback, not an oracle inspection or failure label.
                c.execute("""UPDATE work_orders SET review_required=0,review_due_cycle=NULL,
                          priority=CASE WHEN priority='CRITICAL' THEN 'CRITICAL' ELSE 'HIGH' END,
                          action_type='WORK_ORDER_SCHEDULE_MAINTENANCE',due_cycle=?,row_version=row_version+1 WHERE work_order_id=?""",
                          (min(row['due_cycle'],cycle+lead_time) if row['due_cycle'] is not None else cycle+lead_time,row['work_order_id']))
                self._audit(c,engine_id,cycle,'REVIEW_COMPLETED',row['work_order_id'],row['event_id'],'Simulated uninformative inspection; conservative replacement authorized')
                made.append(xid)
                row = c.execute("SELECT * FROM work_orders WHERE work_order_id=?",(row['work_order_id'],)).fetchone()
            if not row['review_required'] and row['action_type'] in MAINTENANCE_ACTIONS and row['due_cycle'] <= cycle:
                xid = digest([row['work_order_id'],'MAINTENANCE'])
                c.execute("INSERT INTO executions VALUES(?,?,?,?,?,?,?,?)",(xid,self.namespace,asset,engine_id,cycle,'MAINTENANCE',row['work_order_id'],row['event_id']))
                c.execute("UPDATE work_orders SET status='CLOSED',row_version=row_version+1 WHERE work_order_id=?",(row['work_order_id'],))
                c.execute("INSERT INTO episode_outcomes VALUES(?,?,?,?,?)",(self.namespace,asset,engine_id,cycle,'MAINTENANCE'))
                self._audit(c,engine_id,cycle,'MAINTENANCE_EXECUTED',row['work_order_id'],row['event_id'],'Retrospective simulated service executed')
                made.append(xid)
            return made

    def record_failure(self, engine_id, cycle, asset_id=None):
        asset = asset_id or str(engine_id)
        with self._get_connection(True) as c:
            old = c.execute("SELECT * FROM episode_outcomes WHERE namespace=? AND asset_id=?",(self.namespace,asset)).fetchone()
            if old:
                if old['kind']=='FAILURE' and old['cycle']==cycle:
                    return
                raise EventConflict("Episode already has a different outcome")
            c.execute("INSERT INTO episode_outcomes VALUES(?,?,?,?,?)",(self.namespace,asset,engine_id,cycle,'FAILURE'))
            c.execute(f"UPDATE work_orders SET status='CANCELLED',row_version=row_version+1 WHERE namespace=? AND asset_id=? AND status IN {ACTIVE}",(self.namespace,asset))
            self._audit(c,engine_id,cycle,'FAILURE_RECORDED',None,None,'Evaluator-owned historical failure boundary')

    def transition_work_order(self, work_order_id, target_status, reason='Operator workflow transition'):
        valid_transitions = {
            'OPEN': ['ACKNOWLEDGED', 'CANCELLED'],
            'ACKNOWLEDGED': ['IN_PROGRESS', 'CANCELLED'],
            'IN_PROGRESS': ['CLOSED', 'CANCELLED'],
            'CLOSED': [],
            'CANCELLED': []
        }
        with self._get_connection(True) as c:
            row = c.execute("SELECT * FROM work_orders WHERE namespace=? AND work_order_id=?", (self.namespace, work_order_id)).fetchone()
            if not row:
                raise ValueError(f"Work order {work_order_id} not found")
            current = row['status']
            if target_status not in valid_transitions.get(current, []):
                raise ValueError(f"Invalid transition from {current} to {target_status}")
            c.execute("UPDATE work_orders SET status=?, row_version=row_version+1, updated_at=? WHERE work_order_id=?",
                      (target_status, datetime.now(timezone.utc).isoformat(), work_order_id))
            self._audit(c, row['engine_id'], row['cycle'], 'STATUS_CHANGED', work_order_id, row['event_id'], f"Status transitioned {current} -> {target_status}: {reason}")
            updated = c.execute("SELECT * FROM work_orders WHERE work_order_id=?", (work_order_id,)).fetchone()
            return dict(updated)

    def close_work_order(self, work_order_id, reason='Human workflow closure; no simulated service implied'):
        with self._get_connection(True) as c:
            row=c.execute("SELECT * FROM work_orders WHERE namespace=? AND work_order_id=?",(self.namespace,work_order_id)).fetchone()
            if not row:
                raise ValueError('Work order not found')
            if row['status']=='CLOSED':
                return
            if row['status']=='CANCELLED':
                raise ValueError('Cancelled order cannot be closed')
            c.execute("UPDATE work_orders SET status='CLOSED',row_version=row_version+1 WHERE work_order_id=?",(work_order_id,))
            self._audit(c,row['engine_id'],row['cycle'],'STATUS_CHANGED',work_order_id,row['event_id'],reason)

    def get_all_work_orders(self):
        with self._get_connection() as c:
            return [dict(r) for r in c.execute("SELECT * FROM work_orders WHERE namespace=? ORDER BY work_order_id",(self.namespace,))]

    def get_audit_trail(self, engine_id=None):
        with self._get_connection() as c:
            sql='SELECT * FROM audit_log WHERE namespace=?'
            args=[self.namespace]
            if engine_id is not None:
                sql+=' AND engine_id=?';args.append(engine_id)
            return [dict(r) for r in c.execute(sql+' ORDER BY log_id',args)]

    def save_replay_session(self, session_id, dataset, engine_id, split, policy_name, namespace, current_cycle, total_cycles, status, config):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection(True) as c:
            c.execute("""INSERT INTO replay_sessions(session_id, dataset, engine_id, split, policy_name, namespace, current_cycle, total_cycles, status, config_json, created_at, updated_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                         ON CONFLICT(session_id) DO UPDATE SET
                         current_cycle=excluded.current_cycle,
                         status=excluded.status,
                         namespace=excluded.namespace,
                         config_json=excluded.config_json,
                         updated_at=excluded.updated_at""",
                      (session_id, dataset, engine_id, split, policy_name, namespace, current_cycle, total_cycles, status, canonical(config), now, now))

    def get_replay_session(self, session_id):
        with self._get_connection() as c:
            row = c.execute("SELECT * FROM replay_sessions WHERE session_id=?", (session_id,)).fetchone()
            return dict(row) if row else None

    def update_replay_session_cycle(self, session_id, current_cycle, status="ACTIVE", namespace=None):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection(True) as c:
            if namespace:
                c.execute("UPDATE replay_sessions SET current_cycle=?, status=?, namespace=?, updated_at=? WHERE session_id=?",
                          (current_cycle, status, namespace, now, session_id))
            else:
                c.execute("UPDATE replay_sessions SET current_cycle=?, status=?, updated_at=? WHERE session_id=?",
                          (current_cycle, status, now, session_id))

    def save_training_job(self, job_id, dataset, challenger_algorithm, status, gate_passed, promoted, previous_rmse, new_rmse, improvement_pct, details, completed=False):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection(True) as c:
            c.execute("""INSERT INTO training_jobs(job_id, dataset, challenger_algorithm, status, gate_passed, promoted, previous_rmse, new_rmse, improvement_pct, details_json, created_at, completed_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                         ON CONFLICT(job_id) DO UPDATE SET
                         status=excluded.status,
                         gate_passed=excluded.gate_passed,
                         promoted=excluded.promoted,
                         previous_rmse=excluded.previous_rmse,
                         new_rmse=excluded.new_rmse,
                         improvement_pct=excluded.improvement_pct,
                         details_json=excluded.details_json,
                         completed_at=excluded.completed_at""",
                      (job_id, dataset, challenger_algorithm, status, int(gate_passed), int(promoted), previous_rmse, new_rmse, improvement_pct, canonical(details), now, now if completed else None))

    def get_training_job(self, job_id):
        with self._get_connection() as c:
            row = c.execute("SELECT * FROM training_jobs WHERE job_id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def list_training_jobs(self, limit=50):
        with self._get_connection() as c:
            return [dict(r) for r in c.execute("SELECT * FROM training_jobs ORDER BY created_at DESC LIMIT ?", (limit,))]
