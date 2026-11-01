# FlairGuard scientific and operational correction ? 1 November 2026

Work is on `fix/scientific-operational-integrity`, based on `f6f4977`. No commit or push to public main was performed. The two pre-existing blank-line edits were retained. Accepted Phase A/B and coverage artifacts were not rewritten.

The implementation corrects the scheduler leakage, failure clock, fabricated fallback scores, in-memory governance and misleading evidence labels. **Competition-grade reliability is not established.** Automatic scientific promotion is intentionally blocked without a fresh acceptance cohort. Browser verification could not run because the available computer-use service reports no browsers and rejects creation of an in-app browser.

## What changed

- `flairguard/serving.py` provides a shared observation-only saved-model adapter. Each fitted predictor keeps its own preprocessing; target or outcome columns are rejected. FD001 uses the saved causal feature order/rounding, and FD002 uses its fitted operating-condition normalization before rolling features.
- `fleet_scheduler.py` reads only `test_FDxxx.txt`, uses actual saved-model predictions, and carries the actual model/release hash. It never loads official RUL labels. Warm-up is 20 observations. Its state machine receives only failures observable at the current tick. Legacy calls without an evaluator fail visibly rather than returning invented zero costs. The scheduler regression tests now exercise the explicit evaluator instead of an unscored forecast. Operational snapshots are explicitly censored forecasts.
- `scheduler_evaluation.py` alone loads official failure labels: `T = terminal_observed_cycle + official_terminal_RUL`. T continues beyond the truncated trajectory. Failure precedes service completion at a tie, applies during queueing and service, and includes engines that never requested maintenance. Completed service and failure are mutually exclusive.
- The Gaussian CDF was removed. The retained `RISK_AWARE` identifier denotes an **uncalibrated margin heuristic**. No deployable per-engine uncertainty is available; its margin is disabled, and it currently has the same ordering as RUL priority. The interface displays uncertainty as unavailable. No scheduler is automatically called champion.
- `scheduler_scorer.py` is a standard-library-only independent ledger validator. Production accounting uses a separate calculation. The scorer checks terminal population coverage, bay capacity, dispatch/completion timing and cost components. `18_score_integrity.py` rechecks sealed outputs using the snapshotted scorer without importing the application.
- Retraining now resolves the actual champion training engines, enforces disjoint predictor-fit and development populations, uses identical observations and uncapped scoring truth for both models, and persists full-precision predictions, fitted challenger, frozen protocol, metrics and hashes. Both champion loading and champion prediction failure are fatal. Required MLflow failures are fatal. Failed jobs have null unavailable scores rather than fallback numbers.
- Governance stores immutable fitted releases, hashes, active pointers, ancestry and operation history in transactional SQLite beside the persistent runtime database. Artifacts are flushed before pointer commits. Promotion checks the expected champion release to reject a stale comparison; rollback checks artifact integrity. Reads refresh the active release across processes. Existing replays pin their immutable release.
- Replay recovery now restores fault settings and reset epochs, reads the correct persisted prediction field, and uses fit-only perturbation scales. A restarted replay can continue on its original model after champion promotion.
- Evidence endpoints verify input hashes, recompute complete-population metrics from persisted predictions, distinguish engines from rows, and remove fabricated defaults and safety-winner labels. Missing or corrupt required evidence returns HTTP 503. Dataset browsing/research and actual model serving are exposed separately.
- State-changing routes require an operator key, reject untrusted origins and fail closed when no key is configured. This is a local operator authentication boundary, not a claim of complete production security assurance. The browser accepts the key for the current session only.
- Docker numerical constraints match the serialized-model environment. Mutable governance and training evidence live under the storage volume. No public deployment was made.

## Explicit modelling boundary

The scheduling experiment synchronizes all engines: global fleet tick `t` equals each engine's individual cycle, with offsets fixed at zero. A service starts at tick `s` and completes at `s + duration`. Failure at or before completion wins. The degradation clock continues through queueing and service; this is a conservative stylized threat-clock assumption. It does not establish how grounded aircraft engines physically degrade. NASA provides no counterfactual repair trajectories.

After telemetry ends, no sensor samples or new model predictions are invented. Queued point estimates count down by elapsed ticks. Engines that never crossed the service threshold receive no new telemetry-triggered request and eventually fail in the evaluator. These results describe this particular information-limited simulation, not field failure rates or an optimized fleet deployment. Bay work spent on a subsequently failed engine consumes capacity; planned-maintenance cost is charged only for completed service. Wasted life is measured at completion. Queue cost includes time waiting before either dispatch or failure.

## Executed results

The final full suite contains the original 81 regressions plus 19 integrity checks: **100 passed**. Logs and JUnit XML are under the versioned evidence root below. The frontend TypeScript/Vite build passed; Vite reports a bundle-size warning. No browser-to-backend pass is claimed.

A fresh local Uvicorn process and a newly built Docker image each underwent genuine restarts. HTTP prediction changed after an isolated lifecycle-test activation of a genuinely fitted Ridge challenger, survived restart, and returned to the original prediction after rollback and a second restart. Replay fault state, pinned model, work orders and reset epochs survived. Authentication and origin rejection were exercised over HTTP. Required MLflow logging produced real run IDs. Local and container predictions matched exactly for original, activated and rolled-back predictors.

**The lifecycle-test activation is not scientific model promotion.** It occurred only in isolated verification databases/volumes, used an explicitly labelled development challenger, and ended with rollback. The normal retraining route remained blocked. Fault/work-order recovery used the quality-gate comparator; the point champion was not silently changed to refer every telemetry defect.

The FD001 development comparison fitted on 70 engines and evaluated on 10 different engines. Uncapped RMSE was 39.39402075015384 for the champion and 39.03378214212484 for Ridge, a 0.9144499626319396% reduction. It failed the numerical 2% hurdle and also lacked fresh acceptance labels. Neither predictor was scientifically promoted. A separate real FD002 LightGBM development job fitted 110 engines and evaluated 20 other engines through each saved preprocessing contract: champion RMSE 35.57038844773116, challenger 36.68567786502905 (3.135443457236199% worse). It was also not promoted. Its fitted artifact, full-precision predictions, manifest and MLflow run are under `fd002-training-v1/`.

The sealed corrected scheduler run is `causal-scheduler-v1-run003`: 16 policy runs, **2,872 engine episodes**, all independently checked. Each dataset uses all official test engines (100 FD001, 259 FD002), and each policy sees identical actual predictions and failure timelines. Settings were fixed before inference: threshold 25; costs failure 10, completed service 1, unused life 0.05/cycle, queue 0.1/cycle; capacities (1 bay, 10-cycle duration) and (3 bays, 4-cycle duration). These are descriptive scenarios, not tuned acceptance thresholds.

| Dataset / bays / duration | FCFS failures / cost | EDF failures / cost | RUL failures / cost | Margin heuristic failures / cost |
|---|---:|---:|---:|---:|
| FD001 / 1 / 10 | 90 / 933.20 | 91 / 942.45 | 92 / 951.60 | 92 / 951.60 |
| FD001 / 3 / 4 | 83 / 864.50 | 83 / 864.50 | 83 / 864.50 | 83 / 864.50 |
| FD002 / 1 / 10 | 246 / 2587.75 | 247 / 2596.50 | 249 / 2617.00 | 249 / 2617.00 |
| FD002 / 3 / 4 | 203 / 2149.85 | 203 / 2149.85 | 203 / 2149.85 | 203 / 2149.85 |

The uncalibrated risk heuristic lost to FCFS in both congested settings and tied RUL priority throughout. High failure counts include unrequested engines beyond truncated telemetry. Earlier low-failure synthetic-forecast results cannot be used to establish scheduler reliability.

## MATLAB and full-life audit

All fixed evaluation engines and all available cycles >=20 were compared for RegimeLightGBM, GlobalLightGBM, age-only Ridge and MATLAB first-PC-plus-age Ridge. This is secondary, historically exposed evidence. It includes the terminal RUL=0 cycle; no endpoint was selected based on prediction error. Full precision per-engine metrics and population tables are saved.

| Dataset / model | Engines / rows | RMSE | Engines with any dangerous near-failure overestimate |
|---|---:|---:|---:|
| FD003 / RegimeLightGBM | 20 / 4,474 | 72.468205 | 0 / 20 |
| FD003 / GlobalLightGBM | 20 / 4,474 | 72.468205 | 0 / 20 |
| FD003 / AgeRidge | 20 / 4,474 | 88.093419 | 18 / 20 |
| FD003 / MATLAB PCA + age Ridge | 20 / 4,474 | 88.547784 | 18 / 20 |
| FD004 / RegimeLightGBM | 49 / 11,719 | 84.345571 | 10 / 49 |
| FD004 / GlobalLightGBM | 49 / 11,719 | 85.685022 | 26 / 49 |
| FD004 / AgeRidge | 49 / 11,719 | 97.583034 | 42 / 49 |
| FD004 / MATLAB PCA + age Ridge | 49 / 11,719 | 97.211094 | 31 / 49 |

Danger means prediction exceeds uncapped true RUL by >20 while true RUL <=30. Counts are engine-level any-event outcomes; repeated rows are not independent engines. At the original frozen endpoints, RegimeLightGBM had 0/4 dangerous FD003 near-failure engines and 0/5 FD004 engines. Their one-sided 95% upper binomial bounds are 52.71% and 45.07%. The full-life FD003 0/20 upper bound is still 13.91%. FD004 has dangerous full-life errors despite its zero endpoint events. This is not a breakthrough or general safety-superiority claim. Existing MATLAB outputs, fitted .mat models and execution logs are preserved locally; they have not been newly published to public GitHub.

## Acceptance disposition

| Gate | Disposition |
|---|---|
| Operational scheduling has no evaluator labels; label mutation/deletion leaves profiles and open-loop decisions unchanged | PASS |
| Saved-model causal prefix predictions; future-label columns rejected | PASS |
| Failure beyond telemetry, queued failure, failure during service and exact-time tie handling | PASS |
| Independent full-population action/cost scoring | PASS ? 16 runs / 2,872 episodes |
| Champion evaluation/tracking failures block promotion; no invented metrics | PASS |
| Durable release, hash verification, real-process restart and rollback | PASS ? local and Docker |
| Prior regressions and new integrity tests | PASS ? 100 tests |
| Historical Phase A/B/coverage preservation | PASS ? 452 files unchanged |
| Fresh scientific promotion acceptance | BLOCKED ? no untouched fresh cohort; no promotion performed |
| Calibrated risk superiority | NOT ESTABLISHED ? heuristic loses/ties |
| Four-subset active serving | PARTIAL ? FD001/FD002 serve; FD003/FD004 research/browsing only |
| Frontend build and HTTP-to-backend integration | PASS |
| Browser-to-backend interaction | NOT RUN ? browser service unavailable |
| Competition-grade reliability / all requested acceptance conditions together | NOT ACCEPTED |

A future promotion experiment needs genuinely new labelled trajectories and an engine-disjoint acceptance cohort frozen before candidate comparison, compatible saved preprocessing and a separate calibration plan. Repeatedly reusing the historical research labels cannot be presented as fresh acceptance. This is an explicit design limitation, not a substituted benchmark score.

## Evidence and reproduction

Evidence root (relative to the nested Python project): `artifacts/integrity_correction/`.

- `causal-scheduler-v1-run003/`: frozen protocol, source snapshot, full-precision predictions, model hashes, evaluator-only outcomes, all four-policy ledgers, full-life and endpoint population tables, per-engine coverage metrics and manifest.
- `experiment-state-v3/model_governance/`: immutable fitted releases used by the scheduling run, with SQLite provenance and hashes.
- `independent-score-run003.json`: independent acceptance result.
- `tests-final-v3.log`, `tests-final-v3.xml`: final source verification.
- `process-restart-v3/`: local runtime report, database, fitted challenger, MLflow SQLite tracking and server logs.
- `docker-runtime-v3/`: final Docker verification report; stopped container/volume names retained for inspection. Exported training/governance artifacts accompany the report.
- Earlier failed/partial verification attempts and scheduler runs001/002 remain preserved. Run001 used shared production/scorer accounting and was superseded by run002 with separate accounting. Run003 confirms identical results after removing the legacy unscored zero-cost path. Runtime attempts v1/v2 incorrectly expected the point policy to create a referral order for a finite stuck-sensor forecast; the final test explicitly exercises the quality-gate comparator for fault-order recovery.
- `docs/integrity-correction-2026-11-01/preservation.json`, `environment-parity.json`, `acceptance.json` and `evidence-manifest.json`: preservation, environment comparison and review index.

From the nested Python project in PowerShell, choose unused versioned output paths:

```powershell
$env:FLAIRGUARD_API_KEY = '<private operator key>'
$env:FLAIRGUARD_DB_PATH = Join-Path (Get-Location) 'artifacts/integrity_correction/reproduction-v1/platform.db'
python -m pytest -q
python scripts/16_integrity_study.py --output artifacts/integrity_correction/causal-scheduler-v1-run004 --engine-limit 300
python scripts/18_score_integrity.py artifacts/integrity_correction/causal-scheduler-v1-run004
python scripts/17_verify_runtime.py --output artifacts/integrity_correction/process-restart-v4 --port 8021
```

From the repository root:

```powershell
npm --prefix frontend run build
docker build -t flairguard-integrity:reproduce .
python FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/scripts/17_verify_runtime.py --output FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/integrity_correction/docker-runtime-v4 --port 8022 --image flairguard-integrity:reproduce
```

The scripts refuse to overwrite an existing experiment directory. Model/data artifacts must be present locally; they are not supplied by a bare public Git checkout. The serving numerical constraints are in `requirements-serving.lock.txt`. Docker runtime verification keeps its named storage and MLflow volumes and leaves its test container stopped; it does not alter an existing deployment.

Required MLflow tracking uses the documented [SQLite tracking backend](https://mlflow.org/docs/latest/ml/tracking/tutorials/local-database/). Tracking was actually exercised here; errors are not silently ignored. No leaderboard or competition submission was uploaded during this correction.

`git diff --check` reports two pre-existing blank-line-at-EOF changes (`mlops/__init__.py` and the scheduler test file); those user edits were preserved. No new functional failure was inferred from those whitespace warnings.
