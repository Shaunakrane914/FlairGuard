# Phase A: Evidence and Execution Foundation

Status: implementation specification frozen before the corrected FD001 run. Research results are not implied by this specification. The architecture review supplies the module responsibilities; the competitive strategy supplies the Trust/Value/Execution objective. This phase is FD001 only and retains the existing package location.

## Reconciliation and boundaries

* Use the architecture's 60 fit / 20 calibration / 20 final-evaluation split. The exact seeded engine IDs, five fit-only validation folds, cutoffs, candidate settings, delays, costs and scenarios are in `configs/phase_a_fd001_v1.json` under the existing project. All new runs copy this protocol and hash it before training.
* Fit-only OOF endpoint RMSE selects among four existing classical candidates plus age-only Ridge and a constant baseline. Fixed settings and tie order are declared; there is no search on calibration/final data. Use uncapped scoring truth; fit/output cap125 remains explicit. Training rows have inherited uniform weights; do not claim balanced fitting. Report macro-engine errors separately.
* Fit-only OOF full-cycle predictions tune basic RUL thresholds and fixed ages against the same hypothetical cost function and positive five-cycle service lead time. The gate candidate inherits the selected point threshold; it is not tuned on final outcomes.
* Calibration engines set anomaly thresholds and a clean single-endpoint conformal residual quantile. Early-reference sensor statistics use fit engines only. Calibration/evaluation do not overlap. No interval width/confidence ranking, learned error selector, deep learning, MATLAB expansion, frontend, MLflow server or repository migration is added.
* The original FD001 official test has already been exposed historically. Phase A does not read it. The new final training-pool partition is a prospective guard for this run, not a historically pristine external test.
* Cutoffs are sampled from a fixed usage-age grid using engine ID/seed, never RUL. Engines failing before a cutoff are reported unavailable, never replaced by easier snapshots. Complete-cycle regression and maintenance replay remain separate populations.
* The final20-engine pilot is too small to certify rare-failure risk or small policy gains. Freeze a five-percentage-point simulated failure-rate noninferiority margin for future Value confirmation, with development-only power/precision assessment required before claiming success. Even zero failures in20 engines has an approximately13.9% one-sided95% upper bound under independent identical-engine assumptions. Do not promote automatically from this pilot.

## Behavioral contracts

Telemetry inference accepts cycle plus declared24 raw channels, no target/failure-time fields. Trailing5/20 features use past/current data only, rounded to10 decimal places consistently for training/replay. Missing inputs are not imputed in Phase A: point inference is unavailable until a finite consecutive prefix rebuilds. A minimum20-sample history is required for operational use; point estimates during initial warm-up may be saved but are not trusted. Missing/gap receipt watermarks and quality buffers are separate, so later valid input can recover.

Flatline checks use explicit absolute tolerance with zero relative tolerance on the FD001 active channels. Constant simulation channels are excluded. Learned bounds are statistical reference support, never physical limits. Deviations and instrumentation checks do not provide physical fault labels.

Work-order priority and review flag are separate. A review-only order can become critical maintenance. One primary active order per asset/session is enforced in SQLite. Each cycle's raw-input hash, proposal, prediction evidence, committed result and reconstructable latest checkpoint are written in one transaction. Identical known events return their original result even after closure; conflicting content and older unknown events are rejected. A stale checkpoint cannot commit a new cycle. Session context pins model bundle, protocol and policy.

The ledger distinguishes proposals, committed order changes, simulated inspection execution, simulated maintenance execution and final episode outcome. Human closure never counts as service. The executor waits positive lead time. Failure at a cycle takes precedence over service due at that cycle; `service >= T` is failure. The evaluator alone knows T. No post-service repaired life is fabricated.

Review fallback is an explicit synthetic assumption: after two cycles an uninformative inspection completes and authorizes conservative replacement with the same five-cycle lead time. No oracle diagnostic information or true RUL is revealed. Completed inspection costs0.2; a request alone is not charged as a completed inspection. Planned service costs1 plus0.05 per remaining unused cycle; failure costs10 including replacement, with no additional downtime term. These are hypothetical units, not estimated fleet economics.

The point comparator can use last-valid RUL decremented by elapsed cycles for at most five cycles during unavailable input, explicitly marked as a bounded stale-evidence assumption; then it also refers to review. The gate additionally refuses measurements failing support/quality/history checks. The same predictor and schedules are used by both policies. Anomaly scores are retained as diagnostic evidence; they do not independently order an overhaul in Phase A.

Historical databases are refused rather than silently migrated. New outputs live under the existing ignored `artifacts/phase_a/<new-run-id>/`. Old data, result files, reports, databases and presentations stay in place. The former05 evaluation entry point routes to the new runner and cannot delete the old database.

## Experiment register

| Experiment | Metrics and baselines | Frozen pilot checks / confirmation threshold | Failure conditions |
|---|---|---|---|
| Trust | Fixed-predictor accepted/rejected MAE, RMSE and NASA penalty; automation coverage; descriptive interval coverage; quality/referral episodes. Compare unfiltered finite predictions and seeded random rejection at matched accepted count. | Report5/10/20% referral-budget research curve in the future full study; pilot clean-endpoint referral target <=10%. A confirmatory selector must lower paired engine loss against matched random rejection with a95% interval excluding no improvement, retain acceptable low-RUL coverage and not worsen full operational outcomes. | Deferring hard engines hides errors, random rejection performs comparably, intervals treated as a confidence ranking, or aggregate success conceals life-stage failure. Pilot results alone do not pass the research hypothesis. |
| Value | Tuned age policy, tuned point-RUL policy, same predictor+gate; run-to-failure sanity comparator. Cost, failures, unused life, completed inspections, unresolved review and executed lead time per engine-life. | Pilot reference costs/delays are frozen in protocol. Confirmation target >=5% cost improvement with paired95% uncertainty supporting improvement and failure-rate noninferiority within5pp; power assessment and broader sensitivity required. | More cost without justified benefit, instant/free service, missing rejected episodes, hypothetical perfect inspection, changed costs after seeing results, or sample too small. Underpowered results are INCONCLUSIVE. |
| Execution | Event/order/execution uniqueness; transactional rollback; restart checkpoint equality; conflict/order handling; independently recomputed action costs. | Zero invariant violations; scalar cost agreement within1e-9; model reload agreement within1e-10; normalized scientific replay outputs identical despite retries/restart. | Any phantom or duplicate service, blocked critical update, lost checkpoint, label entering inference, unauthorized state mutation, or cost mismatch. |

The Phase A run executes a bounded Trust/Value pilot and foundation checks. It prepares but does not substitute for the full confirmatory study, FD002 regime testing, capacity-constrained scheduling, adaptive-interval comparison or calibrated inspection research.

## Anomaly protocol

Z-score, PCA and Isolation Forest fit the14 active raw sensors from assumed-nominal first20 cycles of fit engines. They calibrate on separate calibration engines and report flag rates on final engines. Cycle, settings and separately perturbed rolling features are excluded. The nominal assumption is not a true healthy-event label.

Noise and drift are applied to raw sensor8 in fit-reference SD units at0.5/1/3 strengths. Drift is an actual cycle-dependent ramp; stuck and missing cases have explicit onset/duration. Scores unavailable for missing measurements stay unavailable rather than inventing anomaly confidence. Report availability and detection on scored synthetic event cycles separately. K1/3/5/8 sensitivity reports episode counts and event delay on independent final reference sequences; K3 is fixed a priori, not claimed optimal. Later-life deviations cannot be counted as known physical false alarms.

## Acceptance gates for Phase A

| Gate | Pass requirement |
|---|---|
| A1 Protocol and leakage boundary | Valid disjoint60/20/20 membership, fit-only folds/selection, source checksum, fixed cutoff population, no official-test access |
| A2 Artifact reproducibility | Per-cycle/per-engine predictions for every fitted candidate, raw/clipped outputs, full precision, separate truth, fitted model bundles, complete environment/source/config manifests, load parity |
| A3 Quality/anomaly corrections | Required-channel/recovery/flatline tests; sensor-only independent anomaly calibration/evaluation and declared raw perturbations actually executed |
| A4 Workflow integrity | Critical escalation, exact retry after closure, concurrency, conflict/out-of-order, atomic rollback and namespace pinning tested |
| A5 Execution/cost identity | No service inferred from proposed severity/closure; positive delays, failure-boundary precedence, independently reconstructed costs for every evaluation episode |
| A6 Causal replay and restart | Prefix/batch and future-invariance tests; saved-model real-engine uninterrupted/restarted/retried replay agrees |
| A7 Historical preservation | Non-source historical artifacts match pre-change hashes; modified source has baseline copies; existing user changes preserved |
| A8 Reporting | Actual commands/tests/output references, pass/fail/inconclusive distinctions and unsupported scientific claims identified |

Research Trust/Value success is a separate status from these foundation gates. A complete foundation with negative research results is acceptable; a phantom-action simulator with good-looking metrics fails.
