"""Bounded train-archive FD003/FD004 engineering diagnostic; no test-set access."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

from .data import read_trajectories, add_train_rul
from .evidence import digest, file_sha, write_json
from .metrics import regression_metrics
from .quality import ACTIVE_SENSORS
from .regimes import RegimeModel


SEED = 2026103104
MODELS = ("RegimeLightGBM", "GlobalLightGBM", "AgeRidge")


def freeze_protocol(raw, subset, source_sha):
    """Use only engine IDs, never lifetimes or labels, to assign roles/endpoints."""
    if subset not in ("FD003", "FD004"):
        raise ValueError("Coverage diagnostic supports FD003/FD004 only")
    ids = np.array(sorted(map(int, raw.engine_id.unique())))
    if len(ids) < 20:
        raise ValueError("At least 20 engines required")
    seed = SEED + int(subset[-1])
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(ids)
    n_dev = n_eval = len(ids) // 5
    partitions = {
        "fit": sorted(map(int, shuffled[:len(ids)-n_dev-n_eval])),
        "development": sorted(map(int, shuffled[len(ids)-n_dev-n_eval:-n_eval])),
        "evaluation": sorted(map(int, shuffled[-n_eval:])),
    }
    p = dict(protocol_id=f"coverage-{subset.lower()}-v1", subset=subset,
             seed=seed, source_sha256=source_sha, engine_count=len(ids),
             partitions=partitions,
             endpoint_cycles={str(i): int(rng.choice([40, 80, 120, 160, 200])) for i in ids},
             regimes=1 if subset == "FD003" else 6, nominal_cutoff=30, rul_cap=125,
             candidates=list(MODELS), selection="none; all fixed candidates reported",
             predictor=dict(n_estimators=180, learning_rate=0.07, num_leaves=15,
                            min_child_samples=20, reg_alpha=0.1, reg_lambda=1.0),
             matlab=dict(algorithm="fit-only first-PC plus age, weighted ridge alpha=100",
                         inputs=[f"{s}_mean_20" for s in ACTIVE_SENSORS],
                         pca="unweighted centered SVD on fit rows only",
                         target="fit RUL clipped to [0,125]",
                         intercept_penalty=0, coefficient_penalty=100),
             scoring=dict(primary="one frozen endpoint per surviving engine",
                          endpoint_grid=[40, 80, 120, 160, 200],
                          unavailable="engine ends before assigned cycle; retain denominator",
                          secondary="all cycles >=20, original unintervened histories",
                          target="uncapped true remaining life",
                          danger="prediction - true_rul >20 when true_rul <=30"),
             interpretation="secondary diagnostic; no policy, Trust or superiority acceptance claim")
    validate_protocol(p, ids)
    return p


def validate_protocol(p, engine_ids):
    roles = [set(p["partitions"][r]) for r in ("fit", "development", "evaluation")]
    if any(not s for s in roles) or set.union(*roles) != set(map(int, engine_ids)):
        raise ValueError("Partition coverage mismatch")
    if sum(map(len, roles)) != len(set.union(*roles)):
        raise ValueError("Engine leakage across partitions")
    if set(p["endpoint_cycles"]) != {str(int(i)) for i in engine_ids}:
        raise ValueError("Missing frozen endpoint")
    if any(c not in (40, 80, 120, 160, 200) for c in p["endpoint_cycles"].values()):
        raise ValueError("Endpoint outside preregistered grid")


def score_predictions(frame, p, role):
    """Score persisted predictions, preserving endpoint availability denominators."""
    endpoint = frame.cycle == frame.engine_id.map(lambda i: p["endpoint_cycles"][str(i)])
    result = []
    for population, mask in (("endpoint", endpoint), ("all_cycles_ge20", frame.cycle >= 20)):
        selected = frame.loc[mask]
        if selected.empty:
            raise ValueError("No eligible diagnostic observations")
        near = selected.true_rul <= 30
        errors = selected.prediction - selected.true_rul
        result.append(dict(role=role, population=population,
            expected_engines=len(p["partitions"][role]),
            available_engines=int(selected.engine_id.nunique()),
            **regression_metrics(selected.true_rul, selected.prediction),
            near_failure_rows=int(near.sum()),
            dangerous_overestimate_rows=int((near & (errors > 20)).sum()),
            dangerous_overestimate_rate=float((errors[near] > 20).mean()) if near.any() else None,
            max_overestimate_cycles=float(errors.max())))
    return result


def write_csv(path, frame):
    with Path(path).open("x", encoding="utf-8", newline="") as stream:
        frame.to_csv(stream, index=False, float_format="%.17g")


def run_study(project, output, matlab=None):
    project, output = Path(project).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_files = [project / "flairguard" / n for n in
                    ("coverage_study.py", "data.py", "evidence.py", "metrics.py", "regimes.py", "quality.py")]
    source_files += [project / "scripts/14_coverage_study.py", project / "scripts/matlab/coverage_pca.m"]
    snapshots = output / "source"
    snapshots.mkdir()
    for src in source_files:
        target = snapshots / src.relative_to(project)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
    raw_by_subset = {s: read_trajectories(project / f"data/raw/train_{s}.txt") for s in ("FD003", "FD004")}
    protocols = {s: freeze_protocol(raw, s, file_sha(project / f"data/raw/train_{s}.txt"))
                 for s, raw in raw_by_subset.items()}
    # Both protocols are durable before the first label, model fit or score is created.
    for subset, p in protocols.items():
        write_json(output / subset / "protocol.json", p)
    write_json(output / "preregistration.json", dict(
        created_utc=datetime.now(timezone.utc).isoformat(), protocol_hashes={s: digest(p) for s,p in protocols.items()},
        source_hashes={str(s.relative_to(project)): file_sha(s) for s in source_files},
        official_test_access=False, model_selection=False,
        acceptance="engineering execution only: disjoint roles, causal prefixes, saved fitted artifacts; no Trust/Value gate"))
    all_metrics = []
    prefix_checks = []
    for subset, raw in raw_by_subset.items():
        p, folder = protocols[subset], output / subset
        labeled = add_train_rul(raw)
        roles = {role: raw.loc[raw.engine_id.isin(ids)].copy().reset_index(drop=True)
                 for role, ids in p["partitions"].items()}
        labels = {role: labeled.loc[labeled.engine_id.isin(ids), "true_rul"].to_numpy()
                  for role, ids in p["partitions"].items()}
        for name in MODELS:
            model = RegimeModel(name, p).fit(roles["fit"], labels["fit"])
            if model.features_.fit_engines_ != p["partitions"]["fit"]:
                raise AssertionError("Fitted preprocessing engines differ from protocol")
            joblib.dump(model, folder / f"{name}.joblib")
            if name == MODELS[0]:
                # One shared, fit-only normalization contract for MATLAB input.
                for role, part in roles.items():
                    X, _ = model.features_.transform(part)
                    matlab_frame = part[["engine_id", "cycle"]].copy()
                    matlab_frame["true_rul"] = labels[role]
                    for col in p["matlab"]["inputs"]:
                        matlab_frame[col] = X[col].to_numpy()
                    write_csv(folder / f"matlab_{role}_input.csv", matlab_frame)
            for role in ("development", "evaluation"):
                part = roles[role]
                prediction, _ = model.predict(part)
                frame = part[["engine_id", "cycle"]].copy()
                frame["true_rul"] = labels[role]
                frame["prediction_raw"] = prediction
                frame["prediction"] = np.clip(prediction, 0, p["rul_cap"])
                path = folder / f"{name}_{role}_predictions.csv"
                write_csv(path, frame)
                # Independent prefixes exercise causal rolling features and fitted inference.
                for engine in p["partitions"][role][:2]:
                    trajectory = part.loc[part.engine_id == engine].reset_index(drop=True)
                    for cutoff in (40, 80):
                        if len(trajectory) < cutoff:
                            continue
                        prefix, _ = model.predict(trajectory.iloc[:cutoff].copy())
                        expected = frame.loc[(frame.engine_id == engine) & (frame.cycle <= cutoff), "prediction_raw"].to_numpy()
                        np.testing.assert_allclose(prefix, expected, rtol=0, atol=1e-10)
                        prefix_checks.append(dict(subset=subset, model=name, role=role, engine=engine, cutoff=cutoff, passed=True))
                persisted = pd.read_csv(path, float_precision="round_trip")
                all_metrics.extend(dict(subset=subset, model=name, **m) for m in score_predictions(persisted, p, role))
    write_json(output / "prefix_checks.json", prefix_checks)
    matlab_status = dict(status="NOT_RUN", reason="MATLAB executable not supplied")
    if matlab:
        script_folder = str(project / "scripts/matlab").replace("'", "''").replace("\\", "/")
        run_folder = str(output).replace("'", "''").replace("\\", "/")
        command = f"addpath('{script_folder}'); coverage_pca('{run_folder}')"
        with (output / "matlab_batch.log").open("x", encoding="utf-8") as log:
            try:
                completed = subprocess.run([str(matlab), "-batch", command], stdout=log,
                                           stderr=subprocess.STDOUT, timeout=360, check=False)
                matlab_status = dict(status="PASS" if completed.returncode == 0 else "FAIL", returncode=completed.returncode)
            except (OSError, subprocess.TimeoutExpired) as exc:
                matlab_status = dict(status="FAIL", reason=str(exc))
        if matlab_status["status"] == "PASS":
            for subset, p in protocols.items():
                for role in ("development", "evaluation"):
                    path = output / subset / f"MatlabPCAAgeRidge_{role}_predictions.csv"
                    frame = pd.read_csv(path, float_precision="round_trip")
                    reference = pd.read_csv(output / subset / f"AgeRidge_{role}_predictions.csv", float_precision="round_trip")
                    pd.testing.assert_frame_equal(frame[["engine_id", "cycle", "true_rul"]],
                                                  reference[["engine_id", "cycle", "true_rul"]], check_dtype=False)
                    all_metrics.extend(dict(subset=subset, model="MatlabPCAAgeRidge", **m) for m in score_predictions(frame, p, role))
    write_json(output / "matlab_status.json", matlab_status)
    write_json(output / "metrics.json", all_metrics)
    write_csv(output / "metrics.csv", pd.DataFrame(all_metrics))
    write_json(output / "acceptance.json", dict(
        role_disjointness="PASS", frozen_before_fit="PASS", prefix_causality="PASS",
        saved_models_predictions="PASS", full_precision_serialization="PASS",
        matlab_comparison=matlab_status["status"], trust_value_success="NOT_TESTED",
        limitation="Secondary clean-telemetry diagnostics. No policies, confidence calibration, interventions or official test benchmark evaluated."))
    manifest = {str(path.relative_to(output)): file_sha(path) for path in sorted(output.rglob("*")) if path.is_file()}
    write_json(output / "manifest.json", dict(files=manifest, python=sys.version, protocol_hashes={s:digest(p) for s,p in protocols.items()}))
    return output
