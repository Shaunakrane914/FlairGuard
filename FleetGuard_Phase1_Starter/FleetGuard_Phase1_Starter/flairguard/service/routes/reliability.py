"""Read-only, hash-verified Phase D benchmark contract. No experiment is run by a GET."""
import csv
import json
from pathlib import Path
from fastapi import APIRouter,HTTPException,Query
from flairguard.service.config import settings
from flairguard.evidence import file_sha

router=APIRouter(prefix='/api/v1/reliability',tags=['Reliability research'])


def accepted_run():
    root=settings.artifacts_dir/'phase_d'
    try:
        pointer=json.loads((root/'latest.json').read_text())
        run=(root/pointer['run']).resolve()
        if run.parent!=root.resolve():raise ValueError('Invalid run path')
        manifest=run/'manifest.json'
        if file_sha(manifest)!=pointer['manifest_sha256']:raise ValueError('Manifest mismatch')
        metadata=json.loads(manifest.read_text())
        metadata['files']={name.replace(chr(92),'/'):sha for name,sha in metadata['files'].items()}
        return run,metadata
    except (OSError,KeyError,ValueError) as exc:
        raise HTTPException(503,'No verified Phase D run is available') from exc


def read_artifact(run,manifest,name):
    path=run/name
    if name not in manifest['files'] or not path.is_file() or file_sha(path)!=manifest['files'][name]:
        raise HTTPException(503,'Benchmark evidence unavailable or hash mismatch: '+name)
    return json.loads(path.read_text())


@router.get('/summary')
def summary():
    run,manifest=accepted_run()
    return dict(run_id=run.name,scope=manifest['scope'],manifest_sha256=file_sha(run/'manifest.json'),
        protocol=read_artifact(run,manifest,'protocol.json'),
        execution=read_artifact(run,manifest,'execution.json'),
        results=read_artifact(run,manifest,'summary.json'),
        paired=read_artifact(run,manifest,'paired_engine_results.json'),
        uncertainty_scope='Paired ranges reweight fixed executed engine costs; shared queues are not re-executed. These are conditional sensitivity ranges, not confidence intervals for a new fleet.',
        fd004=read_artifact(run,manifest,'fd004_danger_diagnostic.json'))


@router.get('/ledger')
def ledger(run_id:str=Query(...,max_length=180)):
    run,manifest=accepted_run()
    if any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in run_id):
        raise HTTPException(422,'Invalid ledger identity')
    return read_artifact(run,manifest,'ledgers/'+run_id+'.json')
