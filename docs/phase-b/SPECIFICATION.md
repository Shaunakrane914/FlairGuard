# Phase B: FD002 regimes and stronger Trust/Value experiments

Frozen before fitting or examining final errors. Protocol: `configs/phase_b_fd002_v1.json` in the existing project. Phase A remains historical evidence; its gate failed promotion. This phase develops classical regime-aware prediction, supervised error ranking and decision-aware deferral. No frontend, deep learning, MATLAB expansion, real fleet-economics claim or post-service life simulation is included.

## Data and roles

NASA describes FD002 as260 training engines under six operating conditions and one fault mode. The three settings substantially affect measurements; they are observations, not fault labels. [NASA source](https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data).

Use only `train_FD002.txt`. Official test inputs/labels are excluded. Exact seeded engine memberships are frozen in five disjoint roles:100 predictor fit,30 selector fit,30 policy development,20 interval calibration,80 final evaluation. The final80 are never used to choose models, error predictors, thresholds, fallback horizons, corruption severity or costs. This is a newly guarded internal experiment on public data, not a claim of historical blindness.

Five engine folds inside predictor-fit select among RegimeLightGBM, GlobalLightGBM, age-only Ridge and a constant. All preprocessing is refitted inside each fold. Settings-only standardized KMeans uses six clusters, assigned canonical center order. Early30-cycle fit observations provide assumed-nominal sensor mean/SD references. Global versus local normalization is an ablation with the same predictor/features; rolling means are computed after per-sample normalization. Native settings and regime indicators remain available. Engine-balanced sample weights, fixed candidate settings and a125-cycle training/output cap are declared. Score uncapped true RUL. Model selection minimizes fit-only OOF usage-endpoint RMSE, with protocol-order ties.

Usage endpoints are independently sampled per engine from40/80/120/160/200 cycles using frozen seeds. Failed-before-cutoff cases remain unavailable. Full-life decision replay retains every engine. Neither endpoints nor corruption onsets are positioned using true RUL.

## Trust

A small LightGBM error regressor learns `log1p(abs(point prediction - uncapped RUL))` using selector-fit engines only, with a frozen predictor. It receives age, point prediction, global/regime disagreement, normalized support, normalized temporal innovation, setting distance, history availability, missingness, flatline indicator and regime. It never receives a target, engine ID, future measurements, interval width or true failure time as input. An error score is not a probability or certified confidence.

Selector fitting uses clean and nine declared development cases except the reserved sensor4 diagnostic. Evaluate two selectors: learned error and the transparent normalized-support/flatline heuristic. The same fixed predictor is used throughout. On policy-development clean endpoints, freeze thresholds targeting5/10/20% rejection. The primary operating point is learned selection at10%; the primary statistical comparison pools the nine primary scenarios with engine-level clustering. Missing/incomplete histories are mandatory deferrals and remain visible, rather than receiving fabricated finite scores.

Report fixed-threshold accepted/rejected MAE, RMSE, NASA penalty, actual automation coverage, unavailable cases and global interval coverage. Report low-RUL(<=30), middle(31–125), long-RUL(>125) and six-regime breakdowns. Also report exact-budget batch ranking curves, explicitly distinguished from deployable frozen thresholds. Compare1000 seeded random rejections at matched finite accepted count and the analytical expected random MAE. The expected random control equals the mean loss of the finite population; repeated draws are not independent engines.

Primary Trust passes only if the engine-cluster bootstrap95% upper bound of accepted MAE minus expected-random MAE is below zero, clean fixed-threshold referrals are<=10%, and low-RUL automation coverage is>=80%. Insufficient cases/empty accepted groups fail confirmation. Other budgets/strata/transfer scenarios are diagnostic; no winner is selected from them. No hypothesis is rescued by dropping rejected engines from Value evaluation.

Clean independent calibration endpoints set a single90% marginal residual interval. Publish effective count, rank and width. Regime/life-stage coverage is descriptive. No conditional, selective or sequential coverage guarantee is claimed.

## Value and execution

Reference assumptions retain Phase A units: planned1, failure10, unused cycle0.05, completed inspection0.2; lead5 cycles; uninformative inspection after2 cycles authorizes conservative replacement. Failure at service cycle takes precedence. End each episode at first service/failure. Human workflow status never substitutes for execution.

Tune point thresholds10/20/30/40/50 and bounded stale horizons0/5/10/20 on policy-development full-life primary scenarios, including corruption. Tune fixed ages80 through220 in20-cycle steps. The learned gate inherits the tuned point threshold and searches only the same stale horizons. It defers near an action threshold (buffer10), avoiding Phase A's automatic early replacement whenever a far-from-action prediction is rejected. The bounded fallback and urgency/review distinction are explicit assumptions, not hidden diagnostic knowledge.

Final comparators: run-to-failure, tuned fixed age, tuned point RUL, broad quality gate, decision-aware quality gate and decision-aware learned gate. The decision-aware quality ablation uses the learned policy's parameters, changing only the selector. This distinguishes error learning from the fallback/action change. A simpler policy may win.

The fast scheduler is used only to screen development candidates. Selected final policies execute through the existing transactional WorkOrderStore; every final episode must exactly match the fast schedule. Batch research stores operate in memory and are backed up and sealed into immutable SQLite artifacts. They are durable only after snapshot; the existing durable serving path is unchanged. This phase does not claim online crash durability for its in-memory experiment runner.

Recompute costs independently from executed ledger events. Primary Value averages the nine primary scenarios within engine, then pairs learned minus tuned-point cost across80 engines. Require>=5% reference mean cost reduction and a paired engine bootstrap95% upper cost-difference bound below zero. For failure noninferiority, conservatively count engines with any primary scenario where learned fails and point does not; the exact one-sided95% binomial upper bound on this paired-harm probability must be<=5%. This bounds rather than credits compensating successes. An engine counts once, regardless of how many correlated scenarios are run.

Before final evaluation, estimate the cost effect detectable at80 engines from development paired variance; record the approximate normal-theory power for a5% effect. Power below80% makes the planned cost claim underpowered even if a favorable point estimate appears. Zero harms at80 gives a3.68% upper bound under independent identical-engine assumptions; one or more harms may defeat the5% margin. Stratified regime claims remain limited by smaller effective counts.

Sensitivity: rescore fixed executed actions over failure5/10/20, unused0.01/0.05/0.1 and inspection0/0.2/1. Re-execute frozen point/learned policies for lead1/10; do not infer changed lead-time outcomes by merely changing a cost formula. These are sensitivity checks, not opportunities to select favorable economics.

## Measurement stress

Raw sensor8 noise at1/3 local reference SD, positive/negative3SD drift ramps,20-cycle missing blocks,60-cycle stuck measurements, correlated sensor8/13 noise and earlier noise are primary cases. Most begin at usage140 and continue60 cycles; early noise begins60. This extends beyond Phase A's short early corruption. Same per-engine random draws allow severity pairing. Settings, engine identity, cycle and failure time never change. Onset/duration and failure censoring are recorded. Sensor4 noise is a reserved channel-transfer diagnostic, excluded from selector training, model/policy selection and primary aggregates.

Natural regime transitions and regime-specific performance are evaluated. This is not a held-out-condition generalization experiment; no sixth setting is arbitrarily edited to fabricate one. A future leave-condition-out study needs a separately frozen complete preprocessing/training exclusion protocol.

## Gates and failure conditions

| Gate | Requirement |
|---|---|
| B1 Isolation | Five engine roles/folds; fit-only preprocessing; no official test; source/data/config fingerprints; original files preserved |
| B2 Causality | Prefix/future invariance; normalize before rolling; missing/rebuild correctness; targets rejected at feature boundary |
| B3 Artifacts | Saved fitted predictor/selector/normalizer, reload parity, full-precision predictions, frozen choices before final outputs, complete final populations |
| B4 Trust evidence | Executed budget/random/stratum comparisons and independent metrics; separately report primary Trust pass/fail/inconclusive |
| B5 Value evidence | Executed tuned comparators, matched ablation, power assessment, engine-paired uncertainty, explicit failure bound and real sensitivity replays |
| B6 Execution | Fast/durable outcome parity; independent cost identity; positive lead/review times; no phantom/duplicate service; stable sealed ledgers |
| B7 Reporting | Retain negative results, failed attempts and limitations; claim register; reproducibility commands and saved evidence |

A software gate passing does not mean a research hypothesis passes. Any final leakage, mismatched executed action, silently missing engine, test-guided tuning or regenerated historical artifact fails the foundation. No product promotion follows automatically.

Implementation references: [scikit-learn KMeans](https://scikit-learn.org/1.7/modules/generated/sklearn.cluster.KMeans.html), [grouped validation](https://scikit-learn.org/1.7/modules/cross_validation.html). Runtime APIs are checked against the installed pinned environment rather than assuming the current stable website version.
