"""Evidence numbers from hash-verified inputs; missing runs are explicitly unavailable."""
import json
from pathlib import Path
from typing import List, Optional
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from flairguard.service.config import settings
from flairguard.evidence import file_sha
from flairguard.metrics import regression_metrics
router = APIRouter(prefix="/api/v1/evidence",tags=["Scientific Evidence"])
ARTIFACTS_DIR = settings.artifacts_dir

class BenchmarkModelMetric(BaseModel):
    model_name: str
    dataset: str
    split: str
    engine_count: int
    mae: float
    rmse: float
    nasa_score: Optional[float] = None
    status: str
    source_artifact: str
    source_sha256: str = ""
    row_count: int = 0
    near_failure_engine_count: Optional[int] = None
    dangerous_engine_count: Optional[int] = None


class PolicyEconomicSummary(BaseModel):
    dataset: str
    policy: str
    policy_kind: str
    mean_cost_per_engine: float
    failure_rate_pct: float
    inspection_rate_pct: float
    mean_wasted_cycles: float
    scientific_finding: str
    governance_status: str


class EvidenceProvenance(BaseModel):
    dataset: str
    run_id: str
    protocol_hash: str
    data_sha256: str
    bundle_sha256: str
    selected_model: str
    independent_evaluator_verified: bool


def verified_file(folder, name):
    root = ARTIFACTS_DIR / folder
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        expected = (manifest.get("artifact_hashes") or manifest.get("files"))[name]
        path = root / name.replace(chr(92),"/")
        if file_sha(path) != expected:
            raise ValueError("Artifact hash mismatch")
        return path
    except (OSError,KeyError,ValueError,TypeError) as exc:
        raise HTTPException(status_code=503,detail=f"Evidence unavailable or invalid: {folder}/{name}") from exc


@router.get("/benchmarks",response_model=List[BenchmarkModelMetric])
def get_verified_benchmarks():
    results = []
    a = "phase_a/fd001-v1-run002"
    labels = pd.read_csv(verified_file(a,"labels_evaluator_only.csv"))
    endpoints = pd.read_csv(verified_file(a,"endpoint_population.csv"))
    for name in ("LightGBM","Ridge","Random Forest","HistGradientBoosting","AgeRidge","Constant"):
        path = verified_file(a,f"predictions/{name}.csv")
        frame = pd.read_csv(path).merge(labels,on=["engine_id","cycle"],validate="one_to_one")
        frame = frame.merge(endpoints.rename(columns={"cutoff":"cycle"}),on=["engine_id","cycle","role"],validate="one_to_one")
        frame = frame.loc[(frame.role=="evaluation") & (frame.status=="AVAILABLE")]
        m = regression_metrics(frame.true_rul,frame.prediction)
        results.append(BenchmarkModelMetric(model_name=name,dataset="FD001",split="Frozen evaluation endpoints",
            engine_count=frame.engine_id.nunique(),row_count=len(frame),mae=m["mae_cycles"],rmse=m["rmse_cycles"],
            nasa_score=m["phm08_mean"],status="Fit-OOF selected predictor" if name=="LightGBM" else "Fixed comparator",
            source_artifact="artifacts/"+path.relative_to(ARTIFACTS_DIR).as_posix(),source_sha256=file_sha(path)))
    b = "phase_b/fd002-v1-run002"
    path = verified_file(b,"selection.json")
    selection = json.loads(path.read_text())
    for name,m in selection["selection_metrics"].items():
        # Engine count is distinct engines at available frozen endpoints, never snapshot count.
        protocol = json.loads(verified_file(b,"protocol.json").read_text())
        oof = pd.read_csv(verified_file(b,f"oof/{name}.csv"))
        endpoint = oof.loc[oof.cycle == oof.engine_id.map(lambda i:protocol["endpoint_cycles"][str(i)])]
        results.append(BenchmarkModelMetric(model_name=name,dataset="FD002",split="Fit-only OOF endpoints",
            engine_count=endpoint.engine_id.nunique(),row_count=m["n_snapshots"],mae=m["mae_cycles"],rmse=m["rmse_cycles"],
            nasa_score=m["phm08_mean"],status="OOF selected candidate" if name==selection["model"] else "Fixed comparator",
            source_artifact="artifacts/"+path.relative_to(ARTIFACTS_DIR).as_posix(),source_sha256=file_sha(path)))
    cov = "coverage_study/run001"
    for ds in ("FD003","FD004"):
        for name in ("RegimeLightGBM","GlobalLightGBM","AgeRidge","MatlabPCAAgeRidge"):
            path = verified_file(cov,ds+chr(92)+name+"_evaluation_predictions.csv")
            frame = pd.read_csv(path)
            frame = frame.loc[frame.cycle>=20]  # Complete available histories, including terminal RUL=0.
            m = regression_metrics(frame.true_rul,frame.prediction)
            near = frame.loc[frame.true_rul<=30]
            danger = near.loc[near.prediction-near.true_rul>20]
            results.append(BenchmarkModelMetric(model_name=name,dataset=ds,split="All evaluation cycles >=20; includes terminal cycle",
                engine_count=frame.engine_id.nunique(),row_count=len(frame),mae=m["mae_cycles"],rmse=m["rmse_cycles"],
                nasa_score=m["phm08_mean"],near_failure_engine_count=near.engine_id.nunique(),dangerous_engine_count=danger.engine_id.nunique(),
                status="Secondary full-life diagnostic; no safety superiority claim",
                source_artifact="artifacts/"+path.relative_to(ARTIFACTS_DIR).as_posix(),source_sha256=file_sha(path)))
    return results


@router.get("/policies",response_model=List[PolicyEconomicSummary])
def get_policy_economics():
    results = []
    for ds,folder in [("FD001","phase_a/fd001-v1-run002"),("FD002","phase_b/fd002-v1-run002")]:
        path = verified_file(folder,"policy_costs.csv")
        df = pd.read_csv(path)
        for pol,rows in df.groupby("policy"):
            if ds=="FD002" and pol not in ("point","learned_gate","quality_gate","quality_decision","fixed","none"):
                continue
            m = rows[["total_cost","failures","inspections","wasted_cycles"]].mean()
            results.append(PolicyEconomicSummary(dataset=ds,policy=str(pol).upper(),policy_kind=str(pol),
                mean_cost_per_engine=m.total_cost,failure_rate_pct=100*m.failures,
                inspection_rate_pct=100*m.inspections,mean_wasted_cycles=m.wasted_cycles,
                scientific_finding=f"Descriptive mean over {len(rows)} engine-scenarios from {path.name}; no superiority inference.",
                governance_status="Current Champion" if pol=="point" else "Research comparator (not promoted)"))
    return results


@router.get("/provenance",response_model=List[EvidenceProvenance])
def get_evidence_provenance():
    results = []
    for ds,folder in [("FD001","phase_a/fd001-v1-run002"),("FD002","phase_b/fd002-v1-run002")]:
        manifest = json.loads((ARTIFACTS_DIR / folder / "manifest.json").read_text())
        bundle = verified_file(folder,"models/bundle.joblib")
        results.append(EvidenceProvenance(dataset=ds,run_id=folder.split('/')[-1],
            protocol_hash=manifest['protocol_hash'],data_sha256=manifest['data_sha256'],
            bundle_sha256=file_sha(bundle),selected_model=manifest['selected_model'],
            independent_evaluator_verified=False))  # Hash integrity is not independent rerun verification.
    return results


@router.get("/availability")
def availability():
    return {"datasets": {ds:{"browsing":(settings.data_dir / f"test_{ds}.txt").is_file(),
        "serving":ds in __import__('flairguard.service.models_registry',fromlist=['model_registry']).model_registry.list_models(),
        "research":"phase_a" if ds=="FD001" else "phase_b" if ds=="FD002" else "coverage_study"}
        for ds in ("FD001","FD002","FD003","FD004")}}
