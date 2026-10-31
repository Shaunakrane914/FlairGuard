# Phase A reproducibility

Read [RESULTS.md](RESULTS.md) for the completed run, acceptance gates, negative pilot findings and saved evidence. [SPECIFICATION.md](SPECIFICATION.md) contains the frozen contracts, experiment definitions, acceptance gates and limitations.

From the repository root in PowerShell:

```powershell
$project = 'FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'

# Existing plus Phase A behavioral regressions. No historical test cache writes.
python -B -m pytest -q -p no:cacheprovider

# Fits fixed candidates and fit-only OOF selection, calibrates, evaluates the pilot,
# saves artifacts, replays real models and independently scores the ledger.
# The destination MUST NOT already exist. Choose a new name for each run.
python -B "$project/scripts/06_phase_a.py" --run-dir "$project/artifacts/phase_a/my-reproduction"

# Independently recompute metrics/costs with Python's standard library only.
# Select a fresh output filename; existing evidence is never overwritten.
python -B "$project/scripts/07_score_phase_a.py" --run-dir "$project/artifacts/phase_a/my-reproduction" --data-dir "$project/data/raw" --output "$project/artifacts/phase_a/my-reproduction-independent-recheck.json"

# Reuse the saved model to compare uninterrupted versus store/object restart and
# duplicate-event replay, using new databases outside the original run directory.
python -B "$project/scripts/08_verify_execution.py" --run-dir "$project/artifacts/phase_a/my-reproduction" --output-dir "$project/artifacts/phase_a/my-reproduction-execution"
```

The inspected interpreter is Python3.13.5 on Windows. Exact core runtime/test package versions are in the project's `requirements-phase-a.lock.txt`; the run records interpreter/platform/packages and snapshots the source. For a fresh environment, create a Python3.13 environment and install that file. Cross-platform numerical identity and a fresh dependency installation must be verified separately; do not infer they passed from a same-environment reload check.

`06_phase_a.py` defaults to the frozen `configs/phase_a_fd001_v1.json` and the existing NASA raw-data directory. It reads only `train_FD001.txt`, not official-test files. Run IDs and database namespaces isolate evidence. A technical exception leaves `FAILED.json` in the new run rather than replacing old outputs. Reruns must disclose the reason and use a new directory.

## Artifact map

| File/directory in a run | Purpose |
|---|---|
| `run_plan.json`, `protocol.json` | Pre-fit protocol, membership, cutoff, configuration, environment and source digests |
| `source/` | Exact project source snapshot for this run; not another application checkout |
| `selection.json`, `oof/` | Fit-only out-of-fold predictions and model/policy choices |
| `models/`, `model_metadata.json` | All fitted candidates, anomaly detectors, serving/replay bundle and reload verification |
| `predictions/` | Full-precision raw/clipped per-engine/per-cycle candidate predictions, with role labels |
| `labels_evaluator_only.csv` | Independent evaluator labels; never fed to inference or triage |
| `endpoint_population.csv` | Available versus failed-before-cutoff cases; unavailable endpoints remain visible |
| `interval_calibration.json` | Effective independent-engine count, quantile rank and limited coverage scope |
| `anomaly_scores.csv`, `anomaly_episodes.csv`, `anomaly_report.json` | Independent held-out nominal-reference and synthetic-event results, availability and persistence delays |
| `scenario_predictions.csv` | Unintervened causal prediction/validity histories for clean and raw-corruption scenarios |
| `policies.json`, `workflow.db`, `policy_costs.csv` | Frozen policies; proposed/committed/executed action ledger; per-engine cost decomposition |
| `manifest.json` | Artifact/source/model/dataset version fingerprints and selection declarations |
| `independent_score.json` | Independent scorer output: metric/cost identity plus descriptive Trust/Value pilot results |

The separate execution-verification directory contains fresh uninterrupted/restarted databases and normalized-equality evidence. The original model/ledger run is read-only during that check.

The existing audit documents remain historical records. The pre-change snapshot is under `artifacts/phase_a/baseline-2026-10-31/`; modified original source has a copied baseline, and its `before.json` tracks historical file hashes. Artifacts remain local under the existing ignored `artifacts/` path; no remote push or competition submission is part of Phase A.
