# FD002 completion report

**Engineering/evidence gates B1–B7: PASS. Trust superiority: NOT ESTABLISHED. Incremental Value: FAIL.** Accepted run: `fd002-v1-run002`. Models, selectors, experiments and action records were implemented and executed; the advanced policy is not promoted.

The [specification](SPECIFICATION.md) froze the design before fitting. The existing Phase A source and historical evidence remain unchanged. This increment adds regime-aware classical models, independently trained error ranking, decision-aware deferral, stronger controls and uncertainty analysis. It does not add a frontend, deep learning, MATLAB integration or deployment.

## What is now implemented

New modules under the existing project are `flairguard/regimes.py`, `decision_experiments.py` and `phase_b.py`. New entry points are `scripts/09_phase_b.py`, `10_score_phase_b.py` and the optional scientific exporter `11_plot_phase_b.py`. The exact protocol is `configs/phase_b_fd002_v1.json`; behavioral regressions are in `tests/test_fd002_experiments.py`.

Operating regimes are fitted from settings on predictor-fit engines only. Each raw sample is normalized against its regime reference before trailing features are calculated. The global-normalization ablation uses the same model architecture/features. Sensor corruption is applied to raw measurements in local reference SD units, with both drift signs, severity pairing, missing blocks, stuck values and correlated noise. Actual settings and failure times remain unchanged.

Five engine-disjoint roles contain100 predictor-fit,30 selector-fit,30 policy-development,20 interval-calibration and80 final engines. Five folds inside predictor-fit select the predictor. A separate small model predicts log absolute error using observational features; it is not a probability or interval-based confidence score. Development engines set referral thresholds and tune policies. The reserved sensor4 diagnostic is excluded from development.

Six policies execute through the existing work-order store: run-to-failure, fixed age, tuned point RUL, broad quality gate, decision-aware quality gate and decision-aware learned gate. Every executed episode exactly matches the development scheduler. Research batches use in-memory transactional stores, then save sealed SQLite backups; they do not claim online durability before snapshot.

## Acceptance evidence

| Gate | Status | Evidence |
|---|---|---|
| B1 Isolation/preservation | PASS | Five disjoint roles; fit-only fold preprocessing; source/data/protocol hashes; all309 pre-existing files unchanged; no official-test evaluation |
| B2 Causality | PASS | Prefix/future-invariance, normalize-before-rolling, missing-history recovery and label-boundary tests;20 runner prefix checks plus70 additional saved-bundle checks around late corruption/recovery boundaries |
| B3 Artifacts | PASS | Four serialized predictors/normalizers, learned selector and complete bundle; reload checks;53,759 full-precision prediction rows per candidate; role/cutoff populations; frozen choices before final policy execution |
| B4 Trust evidence | PASS; hypothesis unconfirmed | Executed5/10/20% threshold/ranking curves,1000 random controls per cell, six-regime/life-stage breakdowns and2000 engine-cluster bootstrap draws |
| B5 Value evidence | PASS; improvement target failed | Independently tuned comparator, matched quality/learned decision ablation, power assessment, paired cost interval/harm bound,27 cost combinations and fresh lead-time replays |
| B6 Execution | PASS |5,760 episode outcomes;4,840 maintenance executions and745 inspections; independent scalar cost identity within1e-9; positive declared delays; no duplicate cost rows; stable sealed ledgers; fast/store parity for every episode |
| B7 Reporting | PASS | Reproduction commands, claim register, preserved technical failure, scientific figures and unsupported claims explicitly identified |

**67 tests passed in9.57s**, including all44 Phase A regressions. All33 current project Python files parsed successfully. The independent scorer passed again in isolated Python mode and reproduced the original report exactly. [Acceptance evidence](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_b/validation-v1/acceptance.json) records the final checks and fingerprints.

## Predictor results

The frozen fit-only choice is **RegimeLightGBM**. OOF endpoint RMSE is45.8761 versus46.7332 for global normalization. Both use fixed LightGBM settings, engine-balanced fitting and a125-cycle training/output cap with uncapped scoring truth.

| Candidate | Final endpoint MAE | Final endpoint RMSE | Final all-cycle RMSE |
|---|---:|---:|---:|
| RegimeLightGBM |30.4881|48.8844|51.6568|
| GlobalLightGBM |32.2812|50.3747|52.5201|
| Age-only Ridge |40.4757|56.8133|59.5937|
| Constant |49.1620|67.1594|74.6065|

The regime model's lower final RMSE is an observed split-specific result, not proof of population superiority or an official NASA leaderboard score. Its all-cycle mean NASA penalty is slightly worse than the global model (38,013.24 versus37,510.56), so no blanket metric-superiority claim follows. All-cycle predictions include initial warm-up diagnostics; policies require20 consecutive finite observations.

There are63 available final usage endpoints;17 engines failed before their preset cutoff and remain reported unavailable. All80 still enter Value. Predictor-fit/development/calibration available endpoints are87/23/17 respectively. No easier snapshots replace unavailable cases.

## Trust: useful direction, insufficient confirmation

The primary learned selector's accepted-minus-expected-random MAE is **−2.2147 cycles**, with an engine-cluster95% interval **[−7.6928, +1.0344]**. The interval includes no improvement, so the primary Trust claim is not established. Other budgets are diagnostics, not substitutes for the frozen primary10% comparison.

Clean fixed-threshold referrals are4/63 (**6.35%**), meeting the10% budget. Clean accepted MAE is28.2797 versus30.4881 for all finite endpoints. The quality heuristic instead accepts worse errors:33.2496 MAE while rejecting relatively easy predictions. The learned ranker shows a better direction, with uncertainty retained rather than selecting a favorable random draw.

Pooled primary endpoint low-RUL coverage is96.30%, but only **six independent engines** supply low-RUL endpoints. This is weak evidence about decision-critical operation. Secondary full-life diagnostics therefore retain every alive cycle from usage20 onward in the original unintervened histories, with per-engine and six-regime summaries. Policy execution still stops at first service/failure. These diagnostics are supplementary and do not change the primary verdict:

* Clean last30-cycle availability/acceptance is100%; MAE6.3699 cycles.
* Under the missing block it drops to **66.5%**. Three engines have no available prediction anywhere in that30-cycle band. Finite-only row MAE6.5079 (engine-macro7.2110 among engines with predictions) does not describe those missing forecasts; all episodes remain in Value.
* The finite learned rejections never enter the declared action neighborhood (`point RUL <=30`) in any final scenario. This ranker does not demonstrate additional protection near a service decision.

Calibration has17 available independent endpoints; the90% residual half-width is84.8538 cycles. Accepted clean endpoint coverage is54/59, descriptively. These broad intervals are not safety probabilities, conditional-regime guarantees or an error ranking.

## Value: the added learner changes no outcomes

Primary means average the nine primary scenarios within each engine, then average80 engines. Failure counts below are720 correlated engine-scenario episodes per policy, not720 independent engines.

| Policy | Mean hypothetical cost | Failure episodes | Completed inspections |
|---|---:|---:|---:|
| Run-to-failure |10.0000|720|0|
| Tuned fixed age |4.6638|45|0|
| Tuned point RUL |1.9412|5|58|
| Broad quality gate |2.2485|11|192|
| Decision-aware quality gate |2.0683|11|181|
| Decision-aware learned gate |1.9412|5|58|

Development selects point threshold20 and bounded stale horizon20. The learned gate inherits threshold20 and independently selects the same horizon. Its observed outcome cycle, inspections and cost match point RUL for **every one of800 final engine-scenario pairs**, including the reserved diagnostic.

The primary cost improvement is **0%**, below the5% target. The empirical paired cost interval is[0,0] because these observed outcomes are identical; it does not establish future population equivalence. Development also has zero observed paired variance, so cost power is explicitly **NOT ESTIMABLE**, not perfect power.

There are no incrementally harmed engines relative to point RUL. The conservative one-sided95% upper bound is3.6754%, within the frozen5% incremental margin under the stated independent-engine assumptions. That is not an absolute safety claim: **five engines fail in the missing-telemetry case** under both policies. At lead10 the missing-case failures increase to10/80; at lead1 they are1/80. Those lead-time outcomes were re-executed, not manufactured by rescaling costs.

All27 fixed-action economic combinations keep learned and point costs equal. Decision-aware quality deferral reduces the broad gate's cost, but remains worse than the tuned point baseline and retains additional failures. Complexity has not earned an operational advantage here.

## Design limits and next research decision

Absolute-RUL error ranking and maintenance decision risk are different objectives. Here every finite learned rejection is outside the action neighborhood, so better-looking accepted errors yield no changed maintenance outcome. Rejected point RUL also cannot justify safety simply by appearing far from service: an overoptimistic forecast may hide urgency. The decision-aware policy is an experimental heuristic, not a safety argument.

The next justified complexity is a **decision-horizon loss/risk target and a causal telemetry-recovery experiment**, with realistic delay/workload assumptions. Those require a newly frozen development/validation protocol. The final80 in this report are now exposed and must not become tuning data for a claimed fresh confirmation. Adding another model family or UI would not resolve the measured limitation.

FD002 does not identify repair effectiveness, post-service life or inspection accuracy. These remain hypothetical stopping experiments. Natural regime performance is measured; held-out-condition generalization is not. The fixed14-sensor feature set and capped target are baselines, not demonstrated optima. Fresh-environment installation, cross-platform identity and online deployment were not tested.

## Saved evidence and reproduction

The accepted run contains97 files, approximately2.22GiB, under the already ignored local artifact directory. Models, raw/clipped predictions, full causal streams, evaluator labels, choices, all10 scenario ledgers, sensitivity outcomes and independent results are retained. Nothing was committed, pushed, uploaded or deployed.

* [Run manifest](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_b/fd002-v1-run002/manifest.json) and [independent report](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_b/fd002-v1-run002/independent_score.json).
* [Tests](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_b/validation-v1/tests-02.log), [run transcript](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_b/validation-v1/run002.log), [late-boundary checks](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_b/validation-v1/additional-causality.json), [full-life diagnostics](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_b/validation-v1/full-life-summary.csv).
* [Scientific figure PNG](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_b/figures-v3-run002/fd002_trust_value.png), [SVG](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_b/figures-v3-run002/fd002_trust_value.svg), [figure provenance](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_b/figures-v3-run002/figure_manifest.json). Figure source is saved beside the exports. Earlier visual versions remain preserved.
* [Reproduction commands](README.md), [claim register](CLAIM_REGISTER.md), [frozen experiment specification](SPECIFICATION.md).

Run001 was stopped during partial final replay after reviewing a development planning defect: zero observed paired variance had incorrectly been treated as perfect power. The correction changes planning/reporting and adds a regression; model settings, policy grids, memberships, stresses and costs are unchanged. No final research metric was used to retune them. The [failed-run disposition](../../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_b/validation-v1/run001-disposition.json), partial outputs and failed status remain saved. Run002 is the complete accepted evidence version.
