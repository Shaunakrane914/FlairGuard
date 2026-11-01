# Phase D results: reliability intelligence and execution

Phase D is implemented and executed on `fix/scientific-operational-integrity`, starting from clean checkpoint `326829629bf7957d69c20d2e9ff85e3b513cb89e`. The engineering acceptance gates pass. A general advanced-policy advantage is **not established**, and scientific model promotion remains **BLOCKED** because there is no fresh labeled acceptance cohort. FD003/FD004 remain research/browsing subsets, without active serving.

The competitive objective remains maintenance decision quality under unreliable telemetry, evaluated through Trust, Value and Execution. These results concern retrospective NASA trajectories and hypothetical maintenance resources/costs. They do not establish aircraft safety, physical repair effects or industrial field validation.

## Executed evidence

Paths below are relative to `FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_d/`.

| Evidence | Result | Saved directory |
|---|---|---|
| Initial software baseline | 100 passed | `baseline-v1` |
| Complete regression suite | 114 passed, zero failures/errors/skips | `software-final-v1` |
| Primary full-life experiment | 332 unique policy runs; 17,822 terminal engine episodes | `reliability-v1-run002` |
| Independent primary reconstruction | PASS, raw failure timelines and artifact hashes checked | `verification-v1/independent_recheck.json` |
| Supplemental reconstruction | PASS, 1,644 runs / 81,060 episodes | `verification-v1/supplements.json` |
| Resource-aware empirical fleet pilot | 100 draws; 1,600 runs / 78,400 episodes | `fleet-bootstrap-v1-run001` |
| All-engine diagnostics and threshold frontier | 40 extra runs / 2,580 episodes | `diagnostics-v1-run001` |
| Real MATLAB toolbox comparator | 4 matched fleet runs / 80 episodes | `matlab-similarity-v1-run001` |
| Chromium operator E2E | 1 integrated workflow passed; no browser/console errors or API 5xx | `browser-release-v3` |
| Local and Docker lifecycle verification | Both PASS, actual process/container restarts | `process-release-v3`, `docker-release-v3` |
| Provisioned runtime payload | 598 verified files, original models/data and research evidence | `runtime-payload-v1` |

These are **169 distinct primary source engines** (20/80/20/49), not 98,882 independent observations. The latter number counts repeated engine episodes across all primary and supplemental policy executions. Supplemental draws/scenarios reuse those engines. Full-precision CSVs, fitted models, OOF lineage, SQLite and JSON action ledgers, per-engine costs and corruption hashes are retained. Identical D1/D3 clean comparator runs are reused only after checking input/context hashes and are counted once.

The final `release-v1` seal indexes 3,204 evidence files and records all source hashes. [EVIDENCE.json](EVIDENCE.json) binds the principal manifests and executed reports by SHA256. A [standalone evidence figure](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_d/figures-v2/phase-d-evidence.png) is saved with an SVG counterpart for export.

## Population and causal execution

The [frozen specification](SPECIFICATION.md) and [actual protocol](protocol-v1.json) contain engine identities and data/model hashes. Saved-model lineage was inspected: FD001/002/003/004 fit populations contain 60/100/60/**151** engines, respectively; their evaluation populations contain 20/80/20/49 and exclude every corresponding predictor and preprocessing fit engine. All evaluation populations have historical exposure. Development engines select thresholds before evaluation. FD004 risk training uses three engine-disjoint OOF predictor fits; 25 different development engines calibrate risk and the other 24 select dispatch thresholds.

`FleetController` receives current observations, past state, declared resources and current failure notifications. The evaluator owns future failure times and true RUL. Regression tests reject forbidden future-label fields and demonstrate that future labels cannot change an operational decision. Predictions exclude the terminal failure row. The independent standard-library scorer reconstructs proposals, unique commitments, starts, reviews, completions, failures, capacity use and costs directly from ledgers; it also derives failure clocks again from original NASA training files.

A global tick maps to local cycle plus the declared offset. Engines age while queued or serviced. This is an explicit hypothetical threat clock. Failure wins completion ties; positive lead and service durations apply; engines leave at first completion/failure. No post-repair trajectory is invented. Reference/congested/staggered settings vary fleet size, bay capacity, technician capacity, duration, lead and offsets. Review has capacity one, takes two ticks and supplies no oracle diagnosis.

Reference normalized costs are failure 10, completed service 1, wasted life 0.05/cycle, order-to-start delay 0.1/cycle, committed-order downtime 0.05/cycle and completed inspection 0.2. `queue_wait` includes compulsory lead time, and `maintenance_delay` is the same total order-to-start delay. Downtime begins at commitment. Economic sensitivity tables reprice fixed executed actions and do not claim a reoptimized policy for every cost setting.

The offline benchmark writes its complete SQLite/JSON evidence when a run is sealed. Its controller has a tested JSON checkpoint roundtrip, but this is not a claim of transactional per-tick benchmark crash recovery. The separate operational API uses its existing durable work-order/model stores and is verified through real restarts.

## Value: full-life policies

Clean reference-condition results below are mean normalized cost per engine / number of failures. The [complete eight-policy table](full-life-reference-results.md) includes every subset; other resource settings and execution metrics are in the saved tables.

| Policy | FD001 (20) | FD002 (80) | FD003 (20) | FD004 (49) |
|---|---:|---:|---:|---:|
| No maintenance | 10.0000 / 20 | 10.0000 / 80 | 10.0000 / 20 | 10.0000 / 49 |
| Fixed interval | 7.0475 / 9 | 10.0894 / 11 | 7.5775 / 6 | 10.1378 / 1 |
| FCFS | 2.0125 / 0 | 2.2588 / 0 | 2.0900 / 0 | 2.4939 / 0 |
| Tuned point RUL | 2.0125 / 0 | 2.3675 / 1 | 2.0900 / 0 | 2.4939 / 0 |
| Bounded lookahead | 2.0125 / 0 | 2.5813 / 3 | 2.0900 / 0 | 2.4939 / 0 |

FCFS beats lookahead and point priority on FD002 in this setting. Bounded lookahead minimizes a predicted tardiness objective over permutations of at most six queued orders; it is not a globally optimal fleet scheduler. The tuned conservative search selected the same threshold (20 cycles) as the point policy. This collapse is retained. A separate full frozen 10/20/30/40/50 threshold frontier reports failures versus discarded life without selecting a replacement after inspecting evaluation labels.

`per_engine_outcomes.csv` reports completed actions, terminal failure phase, order wait, maintenance delay, discarded life, downtime, review workload, decision lateness and component costs. `diagnostics-v1-run001/utilization_and_failure_phases.csv` adds bay/technician utilization and failure timing. Capacity saturation causes substantial failures even where clean reference conditions appear favorable; those runs remain in the report/API.

## Trust: decision-horizon risk

The target is failure within 15 operating cycles. This is a decision-horizon classifier, not a validated probability of a particular queue's eventual failure. Logistic, boosted and empirical residual-CDF candidates use causal forecasts/quality histories and separate isotonic calibration. Simple conservative, slope and staleness rules are also evaluated. Diagnostic alarm budgets are selected on development scores, with achieved evaluation alarm rates reported; they are not artificially forced to match after seeing evaluation outcomes.

For clean FD004 at the development-selected nominal 10% alarm budget:

| Candidate | Row sensitivity | False-positive rate | Actual alarm fraction | Brier score |
|---|---:|---:|---:|---:|
| Logistic | 0.9279 | 0.0271 | 0.0838 | 0.01760 |
| Boosted | 0.9374 | 0.0284 | 0.0857 | 0.01725 |
| Residual CDF | 0.9429 | 0.0347 | 0.0919 | 0.01824 |

Saved metrics include precision, average precision, calibration bins, per-engine detection and lead time. The original fields named `referral_rate` and `automation_coverage` mean hypothetical diagnostic threshold-mask fractions. Risk dispatch directly commits maintenance; these fields must not be read as actual human workload. Completed reviews and inspection costs come from execution ledgers.

Across all eight FD004 telemetry scenarios and both principal capacity settings, averaging repeated conditions within each engine, the observed mean cost differences against tuned point RUL are:

| Candidate | Cost difference per engine | Additional harmed engine identities across conditions | Earned advantage |
|---|---:|---:|---|
| Logistic | +0.48903 | 6 | No |
| Boosted | -0.03967 | 6 | No |
| Residual CDF | +0.02207 | 4 | No |

The frozen advantage criterion required at least 5% cost improvement, a negative upper paired-bootstrap bound, and no incrementally failed engines. Every candidate fails the improvement and/or harm conditions. No threshold or criterion was relaxed. Shared bays couple engines: the original `interval_95` fields reweight already-executed engine costs with queues fixed. They are **conditional sensitivity ranges**, not confidence intervals for a new resource-constrained fleet. Their inferential limitation is stated in the API, UI, plot and specification; no candidate is certified using these ranges.

A separately frozen **100-draw resource-aware empirical bootstrap pilot** samples 49 full trajectories with replacement, assigns duplicate trajectories distinct asset IDs and re-executes both policies on each identical sampled fleet. It recomputes queues for clean/packet40 and reference/congested settings, without retraining or retuning:

| Candidate | Mean cost difference | Empirical 95% percentile range | Mean failure-count difference per 49-engine fleet-condition |
|---|---:|---|---:|
| Logistic | +1.98852 | [1.16685, 2.82096] | -2.6625 |
| Boosted | +0.01688 | [-0.11337, 0.11006] | +0.0925 |
| Residual CDF | 0 | [0, 0] | 0 |

Logistic offers a quantified safety–cost tradeoff in this bounded pilot: about 2.66 fewer failures per fleet-condition at 1.99 extra cost units per engine. This selected two-scenario pilot does not replace the eight-scenario primary comparison. Its finite Monte Carlo budget and empirical historical cohort limit inference. Residual equality here is not evidence of population equivalence. The simple accepted operational policy remains in place.

The FD004 diagnostic retains dangerous overestimation on **10/49 engines**. Dangerous rows begin with true RUL 27–30 and extend down to 12 in some engines, span multiple observed regimes, and have maximum consecutive runs from one to eight cycles. They are not restricted to the final reading. All 49 engines receive diagnostics, including earlier causal warning and the three largest fit-normalized sensor-history contributions. These are descriptive correlates, not causal fault attribution. The threshold frontier quantifies the premature-service/failure tradeoff of conservative mitigation on the same exposed population.

## Trust: missing telemetry

Six strategies run on identical FD002/FD004 histories: abstention, bounded last-valid countdown, five-cycle forward fill, training-derived regime imputation, a fitted missingness-aware predictor and decision-aware review fallback. Eight deterministic scenarios include isolated/multiple channels, short/prolonged complete outages, causal trigger loss, delayed packets, recovery and regime-transition loss. Original/modified hashes, seeds, onsets, durations and channels are saved. Delayed packets are rejected using their original timestamps, not treated as current data.

Selected reference-condition comparisons below are failures / mean cost, with complete results and forecast availability in the saved evidence:

| Scenario | Subset | Abstain | Bounded countdown | Regime imputation | Missingness-aware | Review fallback |
|---|---|---:|---:|---:|---:|---:|
| 20-cycle packet loss | FD002 | 32 / 5.7181 | 25 / 4.9894 | 30 / 5.5131 | 11 / 3.6000 | 25 / 4.9894 |
| 40-cycle packet loss | FD002 | 18 / 3.8931 | 8 / 3.0219 | 16 / 3.7413 | 10 / 3.2338 | 4 / 3.1356 |
| Causal-trigger outage | FD002 | 60 / 8.0013 | 14 / 4.0031 | 0 / 2.2181 | 3 / 2.6731 | 14 / 4.0031 |
| 40-cycle packet loss | FD004 | 14 / 4.7867 | 10 / 4.1459 | 14 / 4.7867 | 8 / 3.8684 | 7 / 5.2184 |
| Causal-trigger outage | FD004 | 36 / 7.9469 | 2 / 2.9714 | 0 / 2.5102 | 1 / 2.5837 | 2 / 2.9714 |

Benefits depend on the outage. The missingness-aware predictor increases FD002 packet40 availability from 87.29% (abstain) to 96.27%, yet has more failures than bounded countdown in that setting. It changes both predictor and recovery and therefore does not isolate the causal effect of imputation. Regime imputation helps the causal-trigger condition but fails to improve the FD004 packet40 result. Review fallback can lower failures at higher cost. No method is declared universally safe or silently made the champion. The matched per-engine decision-change table records delayed requests, suppressed commitments, failure differences and cost differences.

## Execution, browser and model governance

The React application now reads real benchmark results/ledgers, model release history, observed telemetry, model pins, namespaces and quality status. Unknown assets are not labeled nominal. Session recovery survives refresh/backend restart; missing inputs return unavailable forecasts as JSON null; current replay exports contain only the committed observed prefix. Concurrent stepping is serialized. Administrative transitions remain authenticated and are not described as physical repairs. FD003/FD004 replay controls are disabled because active serving is unavailable.

The final Playwright test used genuine Chromium, FastAPI and saved models without response mocks. It opened the fleet, selected engine 15, inspected telemetry, started/stepped a replay, injected a stuck fault, observed quality and a real work order, acknowledged it, refreshed, restarted the backend and recovered the replay/order/model pin. It then injected missing telemetry, fitted a real Ridge challenger, observed blocked promotion, inspected release history and benchmark provenance/ledger, and checked a 390×844 responsive layout. Screenshots and a trace are saved. Browser/API defects found during earlier attempts were fixed, and failed evidence directories remain available.

Local-process and Docker tests use clean isolated databases and a read-only, hash-verified payload. They execute real saved-model inference, training/MLflow recording, authentication/origin rejection, persistent activation of a genuinely fitted challenger **only in an isolated lifecycle test**, rollback, model-version restoration, pinned replay, fault/order recovery, reset and second restart. Their scientific training endpoint remains blocked. The final image is `flairguard-phase-d:release-v3`, ID `sha256:22e02d9c1776be52f118278496b425a20749e40f6b5f92849072560e7131e27a`. Stopped test-container storage and MLflow records are exported with dependency/image inventories.

GitHub Actions checks were added and the data-free invariant selection was executed locally (6 passed). Remote Actions and public cloud deployment are **NOT RUN**. A bare public checkout does not contain NASA data or all saved weights; the provisioning command requires the verified local source artifacts. Docker installs Python constraints and `npm ci` from the lockfile; installed package inventories record the actual environments. This is an executed local/container deployment verification, not a public deployment claim.

## Optional MATLAB research

MATLAB R2026b and Predictive Maintenance Toolbox function/license availability were checked, then `pairwiseSimilarityModel` was genuinely fitted and saved. FD003 uses the same 60 fit and 20 evaluation engines, fixed sensor-11 health-indicator preprocessing, 20-cycle query cadence and bounded causal carry-forward. Both models see the same query interface; missing-input availability differs and is reported.

On 235 clean scheduled prefixes, MATLAB RMSE/MAE are 92.0018/66.5693 versus Python 75.1356/45.5216; dangerous-engine counts are 7 versus 0. MATLAB's asymmetric NASA mean score is slightly lower (15,520,739 versus 15,592,001), so a blanket Python win across all metrics would be inaccurate. Clean fleet cost/failures are 7.6300/8 for MATLAB versus 2.0575/0 for Python; under sensor loss they are 7.7450/8 versus 4.0650/5. Missing-case error metrics in `metrics.json` condition on each model's own available predictions and must be read together with coverage, not as an identical-row comparison. MATLAB fit took 0.7651 seconds and per-query times are saved; comparable Python latency was not instrumented, so no speed advantage is claimed. The installed trial/license status is recorded in `matlab.log`. The deployed application has no MATLAB dependency.

## Acceptance and limits

The machine-readable [acceptance report](acceptance.json), [claim register](CLAIM_REGISTER.md) and [reproduction commands](README.md) separate engineering completion from scientific promotion and external deployment. The final seal rechecks all 760 pre-existing artifact hashes. Prior Phase A/B, truncated-trajectory and correction evidence remains unchanged, including previous negative findings. Primary run001 stopped at a duplicate-comparator sealing check; it is preserved with a disposition file and was rerun without changing scientific settings.

Remaining research needs are fresh labeled confirmation, real maintenance/repair response data, wider resource-aware sampling and prospective calibration/decision validation. These limitations do not prevent the implemented benchmark and operator workflow from being reviewed, but they do prevent claims of industrial effectiveness or a newly validated champion.
