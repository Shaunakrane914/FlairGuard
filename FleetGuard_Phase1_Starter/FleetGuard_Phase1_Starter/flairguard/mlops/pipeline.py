"""Real supervised development comparison. Historical cohorts cannot prove promotion safety."""
import json
import uuid
from pathlib import Path
from typing import Optional
import joblib
import numpy as np
from lightgbm import LGBMRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from flairguard.data import read_trajectories, add_train_rul
from flairguard.features import add_causal_features
from flairguard.metrics import regression_metrics
from flairguard.evidence import file_sha, digest
from flairguard.serving import predict_observations, predictor_fit_engines
from flairguard.service.config import settings
from flairguard.service.models_registry import model_registry
from flairguard.storage import WorkOrderStore

def get_challenger_model(algorithm: str, seed: int = 42):
    """Factory for genuine challenger algorithms."""
    algo_lower = algorithm.lower()
    if "ridge" in algo_lower:
        return Ridge(alpha=100.0)
    elif "hist" in algo_lower:
        return HistGradientBoostingRegressor(max_iter=80, random_state=seed)
    elif "forest" in algo_lower or "rf" in algo_lower:
        return RandomForestRegressor(n_estimators=40, max_depth=10, random_state=seed, n_jobs=2)
    elif algo_lower in ("lightgbm", "lightgbm_optuna"):
        # Fixed LightGBM settings; no Optuna search is performed
        return LGBMRegressor(
            n_estimators=80,
            learning_rate=0.06,
            num_leaves=31,
            random_state=seed,
            verbose=-1,
            n_jobs=2,
        )


    raise ValueError("Unknown challenger algorithm")


class RetrainingEngine:
    def __init__(self, db_path: Optional[Path] = None, registry=None):
        self.db_path = db_path or settings.db_path
        self.registry = registry or model_registry
        self.store = WorkOrderStore(self.db_path, namespace="mlops_system")

    def run_training_job(self, dataset="FD001", challenger_algorithm="LightGBM",
                         reveal_batch_size=10, hurdle_pct=2.0):
        ds = dataset.upper()
        if ds not in ("FD001", "FD002"):
            raise ValueError("Retraining requires an active supported serving model (FD001/FD002)")
        if not 1 <= reveal_batch_size <= 10 or not 0 <= hurdle_pct <= 100:
            raise ValueError("Reveal batch must be 1..10 and hurdle must be 0..100")
        job_id = f"job-{ds.lower()}-{uuid.uuid4().hex}"
        output = self.db_path.parent / "training_artifacts" / job_id
        output.mkdir(parents=True, exist_ok=False)
        def record(status, details, previous=None, new=None, improvement=None):
            self.store.save_training_job(job_id=job_id,dataset=ds,
                challenger_algorithm=challenger_algorithm,status=status,gate_passed=False,
                promoted=False,previous_rmse=previous,new_rmse=new,improvement_pct=improvement,
                details=details,completed=status!="RUNNING")
        record("RUNNING", {"stage":"verifying_champion"})
        try:
            active = self.registry.get_bundle(ds)  # Failure is fatal; never substitute a score.
            meta = self.registry.get_metadata(ds)
            original_fit = predictor_fit_engines(active)
            if ds == "FD001":
                candidates = list(active.get("calibration_engines", []))
            else:
                candidates = list(active["protocol"]["partitions"]["selector_fit"])
            candidates = sorted(set(map(int,candidates))-set(original_fit))
            # Fixed, independent engines, identical observations/truth for both predictors.
            # These labels have previously been used in research: NOT a fresh promotion cohort.
            if len(candidates) < reveal_batch_size + 5:
                raise ValueError("Insufficient disjoint development engines; champion lineage blocked")
            reveal = candidates[:reveal_batch_size]
            validation = candidates[10:]
            if set(reveal) & set(validation):
                raise ValueError("Fit/validation overlap")
            protocol = dict(protocol_id="integrity-development-v1",dataset=ds,
                champion_release=meta["provenance"]["release_id"],champion_fit=original_fit,
                revealed_to_predictor=reveal,fit=sorted(set(original_fit+reveal)),validation=validation,
                scoring_truth="uncapped",fit_target_cap=125,prediction_cap=125,
                population="all cycles >=20 of fixed development engines; engine macro metrics also reported",
                label_provenance="Previously used historical research cohort; newly added to predictor only",
                promotion_eligible=False,
                blocking_reason="No untouched post-development validation cohort or fresh labeled batch supplied",
                algorithm=challenger_algorithm,seed=42,hurdle_pct=hurdle_pct,
                train_source_sha256=file_sha(settings.data_dir / f"train_{ds}.txt"))
            (output / "protocol.json").write_text(json.dumps(protocol,indent=2),encoding="utf-8")
            raw = read_trajectories(settings.data_dir / f"train_{ds}.txt")
            fit_raw = raw.loc[raw.engine_id.isin(protocol["fit"])].reset_index(drop=True)
            val_raw = raw.loc[raw.engine_id.isin(validation)].reset_index(drop=True)
            if set(val_raw.engine_id) & set(original_fit):
                raise ValueError("Champion trained on evaluation engines")
            fit_labeled = add_train_rul(fit_raw)
            X_fit, columns = add_causal_features(fit_raw)
            model = get_challenger_model(challenger_algorithm)
            model.fit(X_fit[columns].round(10),np.clip(fit_labeled.true_rul.to_numpy(),0,125))
            challenger = dict(model=model,model_id=job_id,features=columns,fit_engines=protocol["fit"],
                rul_cap=125,min_history=20,interval_q=None,protocol_hash=digest(protocol),
                quality_config=active.get("quality_config",{}),quality_ranges=active.get("quality_ranges",{}))
            joblib.dump(challenger,output / "bundle.joblib")
            # The same serving adapter respects EACH fitted model's own preprocessing contract.
            champ_raw, champ_pred = predict_observations(active,val_raw)
            challenger_raw, challenger_pred = predict_observations(challenger,val_raw)
            predictions = add_train_rul(val_raw)[["engine_id","cycle","true_rul"]]
            predictions["champion_raw"], predictions["champion"] = champ_raw, champ_pred
            predictions["challenger_raw"], predictions["challenger"] = challenger_raw, challenger_pred
            predictions.to_csv(output / "predictions.csv",index=False,float_format="%.17g")
            scored = predictions.loc[predictions.cycle>=20]
            champion_metrics = regression_metrics(scored.true_rul,scored.champion)
            challenger_metrics = regression_metrics(scored.true_rul,scored.challenger)
            previous, new = champion_metrics["rmse_cycles"],challenger_metrics["rmse_cycles"]
            if not np.isfinite([previous,new]).all() or previous <= 0:
                raise ValueError("Invalid champion comparison")
            improvement = 100*(previous-new)/previous
            result = dict(job_id=job_id,dataset=ds,challenger_algorithm=challenger_algorithm,
                previous_rmse=previous,new_rmse=new,improvement_pct=improvement,
                numerical_hurdle_passed=bool(improvement>=hurdle_pct and new<previous),
                gate_passed=False,promoted_to_champion=False,disposition="BLOCKED_NO_FRESH_COHORT",
                message="Development comparison completed; promotion blocked: historical research labels are not a fresh acceptance cohort.",
                champion_metrics=champion_metrics,challenger_metrics=challenger_metrics,
                validation_engines=validation,fit_engines=protocol["fit"],
                model_artifact_sha256=file_sha(output / "bundle.joblib"),
                artifact_path=str(output),protocol_hash=digest(protocol))
            macro = []
            for eid,g in scored.groupby("engine_id"):
                macro.append(dict(engine_id=int(eid),champion=regression_metrics(g.true_rul,g.champion),
                                  challenger=regression_metrics(g.true_rul,g.challenger)))
            result["per_engine_metrics"] = macro
            if settings.mlflow_required:
                import mlflow
                tracking = settings.mlflow_tracking_uri or ("sqlite:///" + str((self.db_path.parent / "mlflow.sqlite").resolve()).replace(chr(92),"/"))
                mlflow.set_tracking_uri(tracking)
                experiment = f"flairguard_{ds.lower()}_integrity_development"
                mlflow.set_experiment(experiment)
                with mlflow.start_run(run_name=job_id) as run:
                    mlflow.log_params(dict(dataset=ds,algorithm=challenger_algorithm,protocol_hash=digest(protocol),promotion_eligible=False))
                    mlflow.log_metrics(dict(champion_rmse=previous,challenger_rmse=new,improvement_pct=improvement))
                    mlflow.log_artifact(str(output / "protocol.json"))
                    mlflow.log_artifact(str(output / "predictions.csv"))
                    mlflow.log_artifact(str(output / "bundle.joblib"))
                    mlflow.set_tag("disposition","BLOCKED_NO_FRESH_COHORT")
                    result.update(mlflow_run_id=run.info.run_id,mlflow_experiment_name=experiment)
            else:
                result.update(mlflow_run_id=None,mlflow_experiment_name=None,tracking_status="Explicitly disabled; promotion remains blocked")
            (output / "result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
            hashes = {f.name:file_sha(f) for f in output.iterdir() if f.is_file()}
            (output / "manifest.json").write_text(json.dumps(dict(files=hashes,protocol_hash=digest(protocol)),indent=2))
            record("COMPLETED",result,previous,new,improvement)
            return result
        except Exception as exc:
            error = dict(error=str(exc),status="FAILED",promotion_blocked=True)
            (output / "failure.json").write_text(json.dumps(error,indent=2),encoding="utf-8")
            record("FAILED",error)
            raise RuntimeError(f"Retraining pipeline failed: {exc}") from exc


retraining_engine = RetrainingEngine()
