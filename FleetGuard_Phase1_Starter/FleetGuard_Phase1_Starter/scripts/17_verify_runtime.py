"""Own a fresh server/container; verify HTTP behavior across real process restarts."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid
import httpx
import pandas as pd

PROJECT=Path(__file__).resolve().parents[1]


def verify(output,image,port):
    output=output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    key=secrets.token_urlsafe(32)
    name='flairguard-integrity-'+uuid.uuid4().hex[:10]
    env=dict(os.environ,FLAIRGUARD_DB_PATH=str(output/'storage/platform.db'),FLAIRGUARD_API_KEY=key)
    child=None
    log=(output/'server.log').open('a',encoding='utf-8')
    def command(args):
        return subprocess.run(args,check=True,text=True,capture_output=True).stdout.strip()
    def start():
        nonlocal child
        if image:
            command(['docker','start',name])
        else:
            child=subprocess.Popen([sys.executable,'-m','uvicorn','flairguard.service.app:app',
                '--host','127.0.0.1','--port',str(port)],cwd=PROJECT,env=env,stdout=log,stderr=log)
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            try:
                if httpx.get(f'http://127.0.0.1:{port}/api/v1/health',timeout=2).status_code==200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(.5)
        raise RuntimeError('Server not ready; inspect saved server log')
    def stop():
        nonlocal child
        if image:
            command(['docker','stop',name])
        elif child is not None:
            child.terminate()
            child.wait(timeout=30)
            child=None
    report=dict(mode='docker' if image else 'local_process',image=image,checks=[],status='RUNNING')
    if image:
        command(['docker','create','--name',name,'-p',f'127.0.0.1:{port}:8000',
            '-v',name+'-storage:/app/storage','-v',name+'-mlruns:/app/mlruns',
            '-e','FLAIRGUARD_API_KEY='+key,image])
        report.update(container=name,storage_volume=name+'-storage',image_id=command(['docker','image','inspect',image,'--format','{{.Id}}']))
    client=httpx.Client(base_url=f'http://127.0.0.1:{port}',headers={'X-API-Key':key},timeout=180)
    def request(method,path,body=None):
        r=client.request(method,'/api/v1'+path,json=body)
        r.raise_for_status()
        return r.json()
    try:
        start()
        assert httpx.post(f'http://127.0.0.1:{port}/api/v1/models/retrain',json={},timeout=10).status_code==401
        assert client.post('/api/v1/models/retrain',json={},headers={'Origin':'https://untrusted.example'}).status_code==403
        report['checks'].append('HTTP authentication and origin rejection')
        raw=pd.read_csv(PROJECT/'data/raw/test_FD001.txt',sep=r'\s+',header=None)
        raw=raw.loc[raw[0]==15].head(20)
        columns=['engine_id','cycle']+[f'setting_{i}' for i in range(1,4)]+[f'sensor_{i}' for i in range(1,22)]
        raw.columns=columns
        rows=raw.to_dict('records')
        body=dict(dataset='FD001',engine_id=15,cycle=20,settings=[rows[-1][f'setting_{i}'] for i in range(1,4)],
            sensors={f'sensor_{i}':rows[-1][f'sensor_{i}'] for i in range(1,22)},
            history=[{k:v for k,v in r.items() if k!='engine_id'} for r in rows[:-1]])
        original=request('POST','/predict',body)
        assert original['predicted_rul'] is not None
        session=request('POST','/replay/start',dict(dataset='FD001',engine_id=15,namespace=name,policy='quality_gate'))
        sid=session['session_id']
        request('POST',f'/replay/{sid}/step',dict(step_count=20))
        request('POST',f'/replay/{sid}/inject-fault',dict(fault_type='stuck_sensor',channel='sensor_11',start_cycle=21,duration=20))
        before=request('POST',f'/replay/{sid}/step',dict(step_count=10))
        orders=request('GET',f'/work-orders?namespace={name}')
        assert orders and before['last_evidence']['prediction'] is not None
        assert before['last_evidence']['usable'] is False
        training=request('POST','/models/retrain',dict(dataset='FD001',challenger_model='Ridge',reveal_batch_size=10))
        assert not training['promoted_to_champion']
        jobs=request('GET','/models/jobs?limit=1')
        details=json.loads(jobs[0]['details_json'])
        assert details['disposition']=='BLOCKED_NO_FRESH_COHORT' and details['mlflow_run_id']
        # Exercise durable release machinery in this isolated runtime only. This is an explicit
        # lifecycle test of a fitted development challenger, NOT scientific approval to deploy it.
        code='''import sys,joblib
from pathlib import Path
from flairguard.service.models_registry import model_registry as r
b=joblib.load(Path(sys.argv[1])/'bundle.joblib')
m=dict(r.get_metadata('FD001'));m.update(model_id=b['model_id'],model_type='ISOLATED LIFECYCLE TEST ONLY',metrics={})
r.promote_challenger('FD001',b,m,expected_release=m['provenance']['release_id'])
'''
        args=[sys.executable,'-c',code,details['artifact_path']]
        if image:
            command(['docker','exec',name,'python','-c',code,details['artifact_path']])
        else:
            subprocess.run(args,cwd=PROJECT,env=env,check=True,capture_output=True,text=True)
        promoted=request('POST','/predict',body)
        assert promoted['model_id']!=original['model_id']
        assert abs(promoted['predicted_rul']-original['predicted_rul'])>1e-8
        stop();start()
        restored=request('GET',f'/replay/{sid}')
        assert restored['current_cycle']==30 and restored['active_fault']==before['active_fault']
        assert restored['last_evidence']['prediction']==before['last_evidence']['prediction']
        assert request('GET',f'/work-orders?namespace={name}')[0]['work_order_id']==orders[0]['work_order_id']
        after_restart=request('POST','/predict',body)
        assert after_restart['model_id']==promoted['model_id']
        assert abs(after_restart['predicted_rul']-promoted['predicted_rul'])<1e-10
        request('POST','/models/rollback',dict(dataset='FD001'))
        rollback=request('POST','/predict',body)
        assert rollback['model_id']==original['model_id']
        assert abs(rollback['predicted_rul']-original['predicted_rul'])<1e-10
        request('POST',f'/replay/{sid}/step',dict(step_count=1))
        request('POST',f'/replay/{sid}/reset')
        stop();start()
        assert request('GET',f'/replay/{sid}')['current_cycle']==0
        assert request('POST',f'/replay/{sid}/step',dict(step_count=5))['current_cycle']==5
        assert request('POST','/predict',body)['model_id']==original['model_id']
        report['checks']+=['Actual model behavior before/after isolated promotion','Promotion survives process/container restart',
            'Rollback survives second process/container restart','Replay model pin, fault and work orders survive restart',
            'Reset epoch survives restart and accepts fresh events','Required MLflow and artifact-backed real fitting completed']
        availability=request('GET','/evidence/availability')
        assert not availability['datasets']['FD003']['serving'] and not availability['datasets']['FD004']['serving']
        report.update(status='PASS',availability=availability,training=training,original_prediction=original,
                      promoted_prediction=promoted,rollback_prediction=rollback,session_id=sid)
    except Exception as exc:
        report.update(status='FAIL',error=str(exc))
        raise
    finally:
        client.close()
        if image:
            logs=subprocess.run(['docker','logs',name],capture_output=True,text=True,check=True)
            (output/'server.log').write_text(logs.stdout+'\n'+logs.stderr,encoding='utf-8')
        stop()
        log.close()
        (output/'runtime_report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--image',default=None)
    parser.add_argument('--port',type=int,default=8021)
    args=parser.parse_args()
    verify(args.output,args.image,args.port)
