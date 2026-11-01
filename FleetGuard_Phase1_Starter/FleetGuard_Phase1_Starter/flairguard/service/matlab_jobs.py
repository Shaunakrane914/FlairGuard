"""Single-worker, durable, allowlisted local MATLAB analysis jobs.

SQLite persists job transitions; a process lock prevents concurrent server workers
from stealing an active MATLAB job. Interrupted work is never reported complete.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from .config import settings

TERMINAL={'COMPLETED','FAILED','CANCELLED','INTERRUPTED'}


def verified_result(folder):
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files'].items():
        path=(folder/name.replace(chr(92),'/')).resolve()
        if folder.resolve() not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Result artifact integrity failure')
    def read(name):return json.loads((folder/name).read_text(encoding='utf-8'))
    import csv
    outcomes=list(csv.DictReader((folder/'per_engine_outcomes.csv').open(encoding='utf-8',newline='')))
    policies=[]
    for scenario in ['clean','missing']:
        for model in ['matlab','python']:
            rows=[r for r in outcomes if r['scenario']==scenario and r['model']==model]
            policies.append(dict(scenario=scenario,model=model,engines=len(rows),
                failures=sum(int(r['failures']) for r in rows),mean_cost=sum(float(r['total_cost']) for r in rows)/len(rows)))
    import pandas as pd
    pred=pd.read_csv(folder/'predictions.csv')
    py=pd.read_csv(folder/'python_predictions.csv')
    joined=pred.merge(py[['engine_id','cycle','scenario','prediction']],on=['engine_id','cycle','scenario'],suffixes=('_matlab','_python'))
    # Finite/null wire format; evaluator labels stay in the explicit metric outputs.
    joined=joined[['engine_id','cycle','scenario','prediction_matlab','prediction_python']]
    return dict(manifest_sha256=hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest(),
        protocol=read('protocol.json'),metrics=read('metrics.json'),policies=policies,
        common_valid_metrics=read('common_valid_metrics.json') if (folder/'common_valid_metrics.json').exists() else [],
        forecasts=json.loads(joined.to_json(orient='records',double_precision=15)),
        scope='Retrospective FD003 comparison, exposed engines; no scientific promotion or live MATLAB serving',
        timing_scope='MATLAB query times recorded. Comparable Python latency is not measured; no speed claim.')


class MatlabJobs:
    def __init__(self):
        self.root=settings.db_path.parent/'matlab_jobs'
        self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/'jobs.sqlite'
        self.stop_event=threading.Event();self.thread=None;self.process=None;self.guard=threading.RLock()
        with self.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, error TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS audit (job_id TEXT, status TEXT, at REAL)')
    def connect(self):
        c=sqlite3.connect(self.db,timeout=10);c.row_factory=sqlite3.Row;return c
    def capability(self):
        executable=settings.matlab_executable
        return dict(configured=bool(executable),available=bool(executable and Path(executable).is_file()),
            reason='Optional local MATLAB batch worker; toolbox/license checked on actual execution' if executable else 'Set FLAIRGUARD_MATLAB_EXECUTABLE to enable local jobs',
            task='fd003_similarity_v1',scope='Research comparison only',worker_running=bool(self.thread and self.thread.is_alive()))
    def transition(self,jid,status,error=None):
        with self.connect() as c:
            c.execute('UPDATE jobs SET status=?, updated=?, error=? WHERE id=?',(status,time.time(),error,jid))
            c.execute('INSERT INTO audit VALUES (?,?,?)',(jid,status,time.time()))
    def start(self):
        self.lease=(self.root/'worker.lock').open('a+b');self.lease.seek(0)
        self.lease.write(b'0');self.lease.flush();self.lease.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.lease.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.lease.close();raise RuntimeError('MATLAB jobs require a single server worker for this storage')
        for row in self.list():
            if row['status']=='RUNNING':self.transition(row['id'],'INTERRUPTED','Backend stopped before sealing result')
        self.thread=threading.Thread(target=self.loop,daemon=True,name='matlab-comparison');self.thread.start()
    def list(self):
        with self.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 100')]
    def get(self,jid):
        with self.connect() as c:
            row=c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
            if row is None:raise KeyError(jid)
            result=dict(row);result['audit']=[dict(r) for r in c.execute('SELECT status,at FROM audit WHERE job_id=? ORDER BY at',(jid,))]
            return result
    def submit(self,key):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            previous=c.execute('SELECT * FROM jobs WHERE request_key=?',(key,)).fetchone()
            if previous:return dict(previous)
            if not self.capability()['available']:raise ValueError('MATLAB runtime unavailable; historical evidence remains accessible')
            if c.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()[0]>=2:raise OverflowError('Analysis queue is full')
            jid=uuid.uuid4().hex;now=time.time()
            c.execute('INSERT INTO jobs VALUES (?,?,?,?,?,NULL)',(jid,key,'QUEUED',now,now))
            c.execute('INSERT INTO audit VALUES (?,?,?)',(jid,'QUEUED',now))
        return self.get(jid)
    def kill(self):
        if self.process and self.process.poll() is None:
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],capture_output=True)
            else:os.killpg(self.process.pid,signal.SIGTERM)
            self.process.wait(timeout=15)
    def cancel(self,jid):
        with self.guard:
            job=self.get(jid)
            if job['status'] not in TERMINAL:
                self.transition(jid,'CANCELLED','Cancelled by operator')
                if job['status']=='RUNNING':self.kill()
        return self.get(jid)
    def loop(self):
        while not self.stop_event.wait(.3):
            with self.guard:
                pending=[r for r in reversed(self.list()) if r['status']=='QUEUED']
                if not pending:continue
                jid=pending[0]['id'];self.transition(jid,'RUNNING')
                folder=self.root/jid
                log=(self.root/(jid+'.log')).open('x',encoding='utf-8')
                try:
                    self.process=subprocess.Popen([sys.executable,str(settings.root_dir/'scripts/28_matlab_job.py'),
                        '--output',str(folder),'--matlab',settings.matlab_executable],stdout=log,stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,start_new_session=os.name!='nt')
                except Exception as exc:
                    log.close();self.transition(jid,'FAILED',str(exc));continue
            try:
                self.process.wait(timeout=max(1,min(settings.matlab_timeout_seconds,900)))
                with self.guard:
                    if self.get(jid)['status']=='RUNNING':
                        if self.process.returncode:raise RuntimeError('MATLAB analysis failed; inspect the authenticated job log')
                        verified_result(folder)
                        self.transition(jid,'COMPLETED')
            except Exception as exc:
                with self.guard:
                    self.kill()
                    if self.get(jid)['status']=='RUNNING':self.transition(jid,'FAILED',str(exc))
            finally:log.close()
    def close(self):
        self.stop_event.set()
        with self.guard:
            self.kill()
            for row in self.list():
                if row['status']=='RUNNING':self.transition(row['id'],'INTERRUPTED','Backend shutdown before completion')
        if self.thread:self.thread.join(timeout=20)
        if hasattr(self,'lease') and not self.lease.closed:self.lease.close()
