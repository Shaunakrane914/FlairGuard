import hashlib
import json
from pathlib import Path
import pytest
from flairguard.service.matlab_jobs import MatlabJobs,verified_result
from flairguard.service.config import settings


@pytest.fixture
def jobs(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'db_path',tmp_path/'platform.db')
    monkeypatch.setattr(settings,'matlab_executable','')
    return MatlabJobs()


def test_optional_runtime_disabled_and_missing_job(jobs):
    assert not jobs.capability()['available']
    with pytest.raises(ValueError,match='unavailable'):jobs.submit('no-runtime')
    with pytest.raises(KeyError):jobs.get('does-not-exist')


def test_idempotent_submission_cancel_and_audit(jobs,monkeypatch,tmp_path):
    executable=tmp_path/'matlab.exe';executable.touch()
    monkeypatch.setattr(settings,'matlab_executable',str(executable))
    first=jobs.submit('stable-key');second=jobs.submit('stable-key')
    assert first['id']==second['id'] and len(jobs.list())==1
    assert jobs.cancel(first['id'])['status']=='CANCELLED'
    assert [r['status'] for r in jobs.get(first['id'])['audit']]==['QUEUED','CANCELLED']
    assert MatlabJobs().get(first['id'])['status']=='CANCELLED'


def test_queue_bound_and_restart_interruption(jobs,monkeypatch,tmp_path):
    executable=tmp_path/'matlab.exe';executable.touch()
    monkeypatch.setattr(settings,'matlab_executable',str(executable))
    first=jobs.submit('first-key');jobs.submit('second-key')
    with pytest.raises(OverflowError):jobs.submit('third-key')
    jobs.transition(first['id'],'RUNNING')
    # Disable executable; queued work remains cancellable, no fake execution used.
    jobs.cancel(jobs.list()[0]['id'])
    jobs.start()
    try:assert jobs.get(first['id'])['status']=='INTERRUPTED'
    finally:jobs.close()


def test_rejects_modified_historical_artifact(tmp_path):
    (tmp_path/'metrics.json').write_text('changed')
    (tmp_path/'manifest.json').write_text(json.dumps({'files':{'metrics.json':hashlib.sha256(b'original').hexdigest()}}))
    with pytest.raises(ValueError,match='integrity'):verified_result(tmp_path)


def test_matlab_contract_auth_and_arbitrary_task_rejection(jobs,monkeypatch):
    from fastapi.testclient import TestClient
    from flairguard.service.app import create_app
    monkeypatch.setattr(settings,'api_key','integration-test-key')
    with TestClient(create_app()) as client:
        assert client.get('/api/v1/matlab/capabilities').json()['available'] is False
        assert client.get('/api/v1/matlab/jobs').status_code==401
        assert client.post('/api/v1/matlab/jobs',json={'request_key':'safe-key'}).status_code==401
        headers={'X-API-Key':settings.api_key}
        assert client.post('/api/v1/matlab/jobs',headers=headers,json={'request_key':'safe-key','task':'arbitrary_code'}).status_code==422
        assert client.post('/api/v1/matlab/jobs',headers=headers,json={'request_key':'safe-key','path':'../anything'}).status_code==422
        assert client.post('/api/v1/matlab/jobs',headers=headers,json={'request_key':'safe-key'}).status_code==503
