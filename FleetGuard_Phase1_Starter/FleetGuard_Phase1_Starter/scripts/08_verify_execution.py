"""Saved-model, real-FD001 duplicate/restart verification in NEW databases."""
import argparse
import copy
import json
from pathlib import Path
import sqlite3
import sys
from contextlib import closing
import joblib
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from flairguard.data import read_trajectories
from flairguard.evidence import digest, file_sha, write_json
from flairguard.phase_a import corrupt
from flairguard.replay import CausalReplay
from flairguard.storage import WorkOrderStore
from flairguard.quality import TELEMETRY_CHANNELS


def normalized(path):
    result={}
    with closing(sqlite3.connect(path)) as c:
        for table in ('asset_state','decision_events','work_orders','audit_log','executions','episode_outcomes'):
            columns=[r[1] for r in c.execute('PRAGMA table_info('+table+')') if r[1] not in ('timestamp','created_at','updated_at','log_id')]
            result[table]=sorted(c.execute('SELECT '+','.join(columns)+' FROM '+table).fetchall(),key=repr)
    return result


def verify(run, data_dir, output_dir):
    run=Path(run);out=Path(output_dir);out.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((run/'manifest.json').read_text())
    expected=manifest['artifact_hashes']['models/bundle.joblib']
    if file_sha(run/'models/bundle.joblib')!=expected:raise ValueError('Untrusted/changed saved bundle')
    bundle=joblib.load(run/'models/bundle.joblib');bundle['artifact_sha256']=expected
    p=json.loads((run/'protocol.json').read_text());policies=json.loads((run/'policies.json').read_text())
    if file_sha(Path(data_dir)/'train_FD001.txt')!=p['data_sha256']:raise ValueError('Dataset mismatch')
    engine=p['partitions']['evaluation'][0]
    source=read_trajectories(Path(data_dir)/'train_FD001.txt');source=source[source.engine_id==engine]
    T=int(source.cycle.max());results=[]
    with threadpool_limits(limits=2):
        for scenario in p['scenarios']:
            data=corrupt(source,scenario,bundle['corruption_sensor_stds'],p['seed'])
            paths=[];retries=0;restarts=0
            for mode in ('uninterrupted','restarted'):
                path=out/(scenario['name']+'-'+mode+'.db');paths.append(path)
                store=WorkOrderStore(path,'verification/point');replay=CausalReplay(bundle,store,policies['point'])
                for row in data.to_dict('records'):
                    cycle=int(row['cycle'])
                    if cycle>=T:
                        store.record_failure(engine,T);break
                    store.execute_due(engine,cycle,lead_time=policies['point']['lead_time'])
                    with store._get_connection() as c:
                        if c.execute('SELECT 1 FROM episode_outcomes').fetchone():break
                    payload={k:row[k] for k in TELEMETRY_CHANNELS}
                    result=replay.consume(engine,cycle,payload)
                    if mode=='restarted' and cycle%17==0:
                        assert replay.consume(engine,cycle,payload)==result;retries+=1
                    if mode=='restarted' and cycle==10:
                        store.close();store=WorkOrderStore(path,'verification/point')
                        replay=CausalReplay(bundle,store,policies['point']);restarts+=1
                store.close()
            a,b=normalized(paths[0]),normalized(paths[1])
            if a!=b or restarts!=1 or retries<1:raise AssertionError('Replay/duplicate/restart mismatch')
            results.append(dict(scenario=scenario['name'],engine_id=engine,duplicate_retries=retries,restarts=restarts,
                                normalized_sha256=digest(a),event_count=len(a['decision_events']),
                                executions=len(a['executions']),status='PASS'))
    write_json(out/'execution_verification.json',dict(status='PASS',source_run=str(run),bundle_sha256=expected,
               cases=results,scope='One frozen evaluation engine, all five declared scenarios; no new economic superiority claim'))
    print(json.dumps(results,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run-dir',type=Path,required=True)
    ap.add_argument('--data-dir',type=Path,default=ROOT/'data/raw')
    ap.add_argument('--output-dir',type=Path,required=True)
    args=ap.parse_args();verify(args.run_dir,args.data_dir,args.output_dir)
