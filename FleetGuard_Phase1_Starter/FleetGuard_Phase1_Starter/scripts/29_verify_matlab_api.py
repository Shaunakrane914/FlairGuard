"""Execute a real API-created MATLAB analysis and verify restart/result integrity."""
import argparse,json,os,secrets,subprocess,sys,time
from pathlib import Path
import httpx


def run(output,matlab,port):
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    project=Path(__file__).resolve().parents[1];key=secrets.token_hex(24)
    env=dict(os.environ,FLAIRGUARD_DB_PATH=str(output/'storage/platform.db'),FLAIRGUARD_API_KEY=key,
        FLAIRGUARD_MATLAB_EXECUTABLE=str(matlab),FLAIRGUARD_CORS_ORIGINS=json.dumps([f'http://127.0.0.1:{port}']))
    log=(output/'server.log').open('x',encoding='utf-8');server=None
    client=httpx.Client(base_url=f'http://127.0.0.1:{port}/api/v1',headers={'X-API-Key':key},timeout=60)
    def start():
        nonlocal server
        server=subprocess.Popen([sys.executable,'-m','uvicorn','flairguard.service.app:app','--port',str(port)],cwd=project,env=env,stdout=log,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        for _ in range(120):
            try:
                if client.get('/health').status_code==200:return
            except httpx.HTTPError:pass
            time.sleep(.25)
        raise RuntimeError('API failed to start')
    def stop():
        if server and server.poll() is None:server.terminate();server.wait(timeout=30)
    def get(path):
        r=client.get(path);r.raise_for_status();return r.json()
    report={'status':'FAIL'}
    try:
        start();assert get('/matlab/capabilities')['available']
        assert httpx.get(str(client.base_url).rstrip('/')+'/matlab/jobs').status_code==401
        response=client.post('/matlab/jobs',json={'request_key':'verified-api-matlab-v1'});response.raise_for_status()
        job=response.json();jid=job['id']
        assert client.post('/matlab/jobs',json={'request_key':'verified-api-matlab-v1'}).json()['id']==jid
        for _ in range(480):
            job=get('/matlab/jobs/'+jid)
            if job['status'] in ['COMPLETED','FAILED','INTERRUPTED','CANCELLED']:break
            time.sleep(1)
        assert job['status']=='COMPLETED',job
        result=get('/matlab/jobs/'+jid+'/result')
        assert result['common_valid_metrics'] and len(result['policies'])==4
        (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        stop();start();restored=get('/matlab/jobs/'+jid)
        assert restored['status']=='COMPLETED'
        assert get('/matlab/jobs/'+jid+'/result')['manifest_sha256']==result['manifest_sha256']
        historical=get('/matlab/historical');assert historical['policies']
        report=dict(status='PASS',job=restored,manifest_sha256=result['manifest_sha256'],
            real_matlab_job=True,restart_verified=True,historical_evidence_available=True,scientific_promotion=False)
    finally:
        stop();client.close();log.close()
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--matlab',type=Path,required=True)
    p.add_argument('--port',type=int,default=8037);a=p.parse_args();run(a.output,a.matlab,a.port)
