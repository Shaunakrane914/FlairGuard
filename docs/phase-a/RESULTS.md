# Phase A completion report — 2026-10-31

**Foundation: PASS (A1–A8). Advanced-policy promotion: FAIL.** The corrected evaluation ran; it does not establish the Trust or Value research hypotheses. All figures below are measured from `fd001-v1-run002`, with display rounding only. Full-precision evidence remains saved locally.

The [architecture audit](../architecture-review-2026-10-31/FLAIRGUARD_ARCHITECTURE_REVIEW.md) and [competitive strategy](../FLAIRGUARD_COMPETITIVE_STRATEGY.md) were reconciled in [SPECIFICATION.md](SPECIFICATION.md). Implementation stayed within the existing Python package. There is no frontend, deep learning, MATLAB expansion or unrelated repository migration.

## Implemented changes

* `configs/phase_a_fd001_v1.json` freezes engine membership, fit-only folds, usage-age endpoints, candidate settings, anomaly reference population, corruption schedules, delays, costs and acceptance criteria. `evidence.py` validates the split/data hash and writes exclusive, versioned evidence.
* `phase_a.py` and `06_phase_a.py` save all six classical/baseline models, fit-only OOF predictions, model reload checks, environment/source snapshots, separate evaluator labels, full-precision predictions and a hashed manifest. Selection never uses calibration/final metrics.
* `quality.py` checks required channels, advances receipt watermarks on invalid samples, recovers after missing data/gaps and excludes inactive channels from exact flatline detection. Statistical support bounds are named as reference bounds. `anomaly.py` rejects invalid calibration input and handles duplicate/gapped/out-of-order persistence updates. Evaluation fits/calibrates/evaluates on separate engines using raw active sensors and actual raw noise/drift/stuck/missing injections.
* `storage.py` separates review from priority, persists atomic event/checkpoint/order changes, rejects conflicting and older unknown events, makes exact retries idempotent after closure, pins session context and preserves authorized service during lower-priority requests. Historical databases are refused. Proposed decisions, committed orders, inspection execution, maintenance execution and episode outcomes have distinct records. Completed ledgers are sealed before hashing.
* `replay.py` uses causal trailing features and durable state. Failure time is confined to the evaluator. Service at or after failure loses; human closure is never service. `policy_eval.py` charges only recorded executions/outcomes. `07_score_phase_a.py` independently reconstructs truth, metrics and costs using only Python's standard library. `08_verify_execution.py` checks saved-model restart/retry equivalence in new databases.
* The old05 evaluation entry point now routes to the isolated runner. Historical reports/results/databases are preserved. Existing metric/evaluation wording and leakage defects were corrected. Behavioral regressions and a scoped pytest configuration cover the new contracts.

Paths in this list are relative to `FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/`.

## Acceptance gates

| Gate | Result | Executed evidence |
|---|---|---|
| A1 Protocol/leakage boundary | PASS | Disjoint60/20/20; five fit-only folds; raw checksum checked; fit-only selection independently reproduced; official-test files excluded from the runner |
| A2 Artifact reproducibility | PASS | Six saved candidate models;20,631 prediction rows each; source/environment/config manifests; maximum reload discrepancy below1e-10; repeat isolated scoring identical without artifact changes |
| A3 Quality/anomaly corrections | PASS | Required-channel, recovery, gap, slow-change and restart tests; three detectors with independent fit/calibration/evaluation and saved synthetic-event/availability/persistence results |
| A4 Workflow integrity | PASS | Review-to-critical, urgency+invalidity, concurrency, retry-after-closure, conflict, ordering, rollback and context-pinning regressions |
| A5 Execution/cost identity | PASS | All400 episode costs/outcomes independently reproduced within1e-9;300 maintenance executions and66 inspections; service lead exactly5 cycles and inspection delay exactly2 in this run; boundary/closure regressions |
| A6 Causality/restart | PASS | Clean streaming/batch predictions identical across4,112 evaluation cycles; future-invariance and label-boundary regressions; one saved-model engine across five scenarios matches uninterrupted execution despite43 duplicate retries and five store/object restarts; separate-interpreter pending-order reopening also passes |
| A7 Historical preservation | PASS | All73 original non-source files match pre-change hashes;24 original Python baseline copies remain intact; existing user changes preserved |
| A8 Reporting | PASS | Actual commands, immutable run evidence, technical rerun disposition, acceptance evidence and negative/underpowered research findings recorded |

The final suite was **44 passed in7.33s**. It includes explicit agreement between executed simulated actions and independently scored costs. All26 current project module/script/test files parsed successfully. The scoped Git whitespace check passed. The pre-existing root `.gitignore` blank-line change was preserved.

## Measured pilot

Fit-only selection chose **LightGBM**, point-RUL threshold **20**, and fixed replacement age **140**. Four fit-engine endpoints fell after failure and remain visibly unavailable; selection uses the other56. Calibration and final endpoint populations each contain20 engines. No endpoints were substituted using true RUL.

The selected model's final endpoint MAE is25.7746 cycles and RMSE46.1931. Age-only Ridge RMSE is55.6767; constant baseline RMSE69.4034. All-candidate, all-cycle and per-engine metrics are in the independent report. These figures use the frozen usage-age endpoints and uncapped scoring truth with a125-cycle model/output cap; they are not comparable to historical official-test or target-conditioned snapshot scores. The selected model remains fixed even when another candidate has a slightly lower final metric.

**Trust: NOT ESTABLISHED; the observed useful-selection check fails.** Clean endpoint automation coverage is100%, so the matched random comparator is identical. Missing and stuck scenarios each accept17/20 endpoints. Their accepted MAE is28.6715, worse than matched random rejection (27.3319 and26.9249 respectively). Rejected endpoints have lower errors. A single random control is descriptive, not a significance test. The clean endpoint referral-budget check passes, but that alone does not establish useful Trust selection or bounded per-life workload.

The calibration residual quantile is67 cycles (20 independent calibration endpoints, rank19). Descriptive clean endpoint interval coverage is19/20. This broad interval is not a safety probability, confidence ranking, sequential guarantee or proof of conditional/selective coverage.

**Value: observed improvement target FAIL; population-level benefit/risk remains unconfirmed.** Totals below cover the same20 final engines per scenario, in hypothetical cost units.

| Scenario | Fixed age | Tuned point RUL | Point RUL + gate | Gate / point completed inspections |
|---|---:|---:|---:|---:|
| Clean |80.60|33.25|38.85|2 /0|
| Noise on sensor8 |80.60|33.25|38.85|2 /0|
| Drift on sensor8 |80.60|33.25|38.85|2 /0|
| Missing sensor8 |80.60|167.60|172.60|20 /20|
| Stuck sensor8 |80.60|33.25|164.80|20 /0|

Each intervention policy has zero observed failures in each scenario. Run-to-failure has20 failures and costs200.00 per scenario. The added gate costs more in every case, including16.84% more on clean data, without an observed failure advantage. Clean mean unused life is18.45 cycles for the gate versus13.25 for point RUL. Conservative review/replacement under early corruption discards substantial life. The gate is not promoted.

There are20 independent evaluation engines, not400 independent engines: policies/scenarios reuse their trajectories. Zero failures among20 does not establish the frozen5pp risk margin. Noise/drift ends early in life; unchanged action costs do not prove robustness to corruption near a maintenance decision. No costs or thresholds were revised after these findings.

**Anomaly evidence:** held-out assumed-nominal cycle flag fractions are2.5% (Z-score),9% (PCA) and2.25% (Isolation Forest). These are not physical false-alarm estimates. Missing-event score availability is0%; no anomaly sensitivity is fabricated for unscorable samples. Full strength sweeps and K1/3/5/8 episode/delay results are saved. No physical fault-accuracy or optimal-persistence claim follows.

## Evidence and commands

All paths below are local, under the existing ignored artifact directory. Nothing was pushed or submitted.

* [Accepted run manifest](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_a/fd001-v1-run002/manifest.json), [independent metrics/costs](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_a/fd001-v1-run002/independent_score.json):66 files, approximately179MiB including source snapshots, models, full-precision predictions and the ledger.
* [Acceptance evidence](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_a/validation-v1/acceptance.json), [44-test log](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_a/validation-v1/tests-03.log), [run transcript](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_a/validation-v1/run002.log), [batch/stream and delay checks](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_a/validation-v1/saved-run002-checks.json), [preservation inventory](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_a/validation-v1/preservation.json).
* [Saved-model execution verification](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_a/execution-v1-run002/execution_verification.json): new uninterrupted/restarted databases, separate from the accepted ledger.

Executed from the repository root with bytecode disabled and numerical threads limited to2:

```powershell
$project = 'FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:OMP_NUM_THREADS = '2'
$env:OPENBLAS_NUM_THREADS = '2'
python -B -m pytest -q -p no:cacheprovider
python -B "$project/scripts/06_phase_a.py" --run-dir "$project/artifacts/phase_a/fd001-v1-run002"
python -I -B "$project/scripts/07_score_phase_a.py" --run-dir "$project/artifacts/phase_a/fd001-v1-run002" --data-dir "$project/data/raw" --output "$project/artifacts/phase_a/validation-v1/independent-recheck-run002.json"
python -B "$project/scripts/08_verify_execution.py" --run-dir "$project/artifacts/phase_a/fd001-v1-run002" --output-dir "$project/artifacts/phase_a/execution-v1-run002"
python -B "$project/artifacts/phase_a/validation-v1/validate_saved_run.py" "$project/artifacts/phase_a/fd001-v1-run002" "$project/artifacts/phase_a/validation-v1/saved-run002-checks.json"
```

These output paths now exist and deliberately reject reuse. Use fresh paths for reproduction, as shown in [README.md](README.md). Exact core dependencies are pinned; fresh-environment installation and cross-platform numerical reproduction were not executed.

## Technical rerun and scientific limits

Run001 remains preserved but **fails A2**: its manifest included SQLite's mutable WAL/SHM coordination files, and a second audit detected a changed SHM hash. The correction closes reader handles and checkpoints/seals the database before hashing. A regression verifies repeated independent scoring preserves database bytes. Run002 uses the identical protocol and scientific settings; source changes address artifact handling and verification. The [disposition](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_a/validation-v1/run001-disposition.json) records the failure rather than erasing it. Intermediate failed test/audit logs also remain available.

FD001 contains run-to-failure trajectories, not intervention outcomes or measured inspection accuracy. It cannot identify repaired lifetime, real maintenance efficacy or fleet savings. The implemented causal replay is a bounded, retrospective stopping experiment with explicitly hypothetical costs and an uninformative inspection assumption; it ends at first service/failure. Claims about actual repair effects remain unsupported rather than being filled with simulated post-service life.

The final partition is protected from selection within this protocol, but historical exploration and the disclosed technical rerun prevent calling it a pristine external test. Full Trust budget curves, life-stage/regime confirmation, development-only power analysis, economic sensitivity, realistic inspection outcomes and broader data validation remain future experiments. Restart evidence covers persisted state and separate-process reopening; it does not constitute a power-loss durability certification.
