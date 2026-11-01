"""Optional MATLAB analysis, distinct from accepted operational predictors."""
import secrets
from fastapi import APIRouter,HTTPException,Request,Depends
from pydantic import BaseModel,Field,ConfigDict
from typing import Literal
from ..config import settings
from ..matlab_jobs import verified_result

router=APIRouter(prefix='/api/v1/matlab',tags=['MATLAB research'])
class AnalysisRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_key:str=Field(min_length=8,max_length=100,pattern=r'^[a-zA-Z0-9_-]+$')
    task:Literal['fd003_similarity_v1']='fd003_similarity_v1'

def operator(request:Request):
    if not settings.api_key or not secrets.compare_digest(request.headers.get('x-api-key',''),settings.api_key):
        raise HTTPException(401,'Valid operator API key required')

@router.get('/capabilities')
def capabilities(request:Request):return request.app.state.matlab_jobs.capability()

@router.get('/historical')
def historical():
    try:return verified_result(settings.artifacts_dir/'phase_d/matlab-similarity-v1-run001')
    except (OSError,ValueError,KeyError) as exc:raise HTTPException(503,'Verified MATLAB historical evidence unavailable') from exc

@router.get('/jobs',dependencies=[Depends(operator)])
def jobs(request:Request):return request.app.state.matlab_jobs.list()

@router.post('/jobs',status_code=202)
def submit(body:AnalysisRequest,request:Request):
    try:return request.app.state.matlab_jobs.submit(body.request_key)
    except ValueError as exc:raise HTTPException(503,str(exc)) from exc
    except OverflowError as exc:raise HTTPException(429,str(exc)) from exc

def get_job(request,jid):
    try:return request.app.state.matlab_jobs.get(jid)
    except KeyError:raise HTTPException(404,'MATLAB job not found')

@router.get('/jobs/{jid}',dependencies=[Depends(operator)])
def job(jid:str,request:Request):return get_job(request,jid)

@router.post('/jobs/{jid}/cancel')
def cancel(jid:str,request:Request):
    get_job(request,jid);return request.app.state.matlab_jobs.cancel(jid)

@router.get('/jobs/{jid}/result',dependencies=[Depends(operator)])
def result(jid:str,request:Request):
    job=get_job(request,jid)
    if job['status']!='COMPLETED':raise HTTPException(409,'Job has no completed result')
    try:return verified_result(request.app.state.matlab_jobs.root/job['id'])
    except (OSError,ValueError,KeyError) as exc:raise HTTPException(503,'Job artifact integrity failure') from exc

@router.get('/jobs/{jid}/log',dependencies=[Depends(operator)])
def log(jid:str,request:Request):
    job=get_job(request,jid);path=request.app.state.matlab_jobs.root/(job['id']+'.log')
    return dict(job_id=jid,log=path.read_text(encoding='utf-8',errors='replace')[-20000:] if path.exists() else 'Not started')
