# Phase D frozen experiment specification

The code checkpoint is `326829629bf7957d69c20d2e9ff85e3b513cb89e` on `fix/scientific-operational-integrity`; the initial worktree was clean. The baseline suite ran and passed 100 tests before changes. This phase uses the competitive objective of maintenance decision quality under unreliable telemetry, separated into prediction, scheduling and execution evidence.

The complete versioned specification, source/data hashes and engine identities are in [protocol-v1.json](protocol-v1.json), frozen before the new fits and comparisons. All populations are historically exposed and the study is retrospective/developmental. No pristine final confirmation or automatic model promotion is claimed.

| Subset | Predictor/preprocessing fit | Evaluation | Development used for policy tuning |
|---|---:|---:|---:|
| FD001 | 60 | 20 | 20 previously used calibration engines |
| FD002 | 100 | 80 | 30 historical policy-development engines |
| FD003 | 60 | 20 | 20 historical development engines |
| FD004 | **151** | 49 | 24 development engines; a different 25 calibrate risk |

FD004's actual saved preprocessing lineage contains 151 engines, not the rounded 150 suggested by some earlier summaries. The code inspects the serialized lineage. No evaluation engine fitted its predictor or preprocessing. FD004's three OOF predictors fit only the other original fit engines; each risk-training engine receives predictions from a predictor/normalizer that excluded it. OOF corruption histories are kept in separate rolling-feature groups.

D1 compares no maintenance, tuned fixed age, FCFS, EDF, tuned point RUL, a conservative threshold search, the existing zero-margin heuristic and bounded rolling lookahead. All thresholds are selected on development engines. Every condition fixes the same observations, failure timeline and resource assumptions for every policy. The conservative search was allowed to collapse to the simple threshold; the complete frozen threshold frontier is separately reported without choosing a new winner.

D2 predicts failure within the next 15 operating cycles using only current/history forecasts, availability, staleness, missingness, forecast slope/volatility and observed regime changes. Logistic regression, boosted classification and an empirical residual-CDF estimate are fitted on OOF forecasts and calibrated using different development engines. Conservative, slope and staleness rules remain diagnostic comparators. No Gaussian distribution is assumed. Calibration and alarm metrics are empirical and do not establish a deployment or stopping-time probability guarantee.

Risk thresholds use the separate policy-development engines. Diagnostic 5/10/20% alarm budgets are calibrated on development scores; achieved evaluation rates are reported, including ties and drift. The saved `referral_rate`/`automation_coverage` fields describe hypothetical threshold-mask selection, not executed human workload. Risk dispatch directly schedules maintenance. Actual review requests, completed reviews and their costs come only from the event ledger.

D3 compares abstention, bounded last-valid countdown, forward fill, regime-reference imputation, a fitted missingness-aware model and decision-aware review fallback on FD002/FD004. Staleness is chosen from 0/5/20 on development outages. Forward fill lasts at most five samples. The missingness-aware predictor is fitted only on predictor-fit engines with fixed usage-time corruptions and explicit masks. This is a complete model-plus-recovery comparison, not a claim that imputation alone caused every difference; the new predictor also differs from the accepted champion.

Eight deterministic conditions are predeclared: clean; one missing reading; multiple short missing sensors; complete packet loss for 20 and 40 cycles; an outage starting after the causal forecast first crosses 40; delayed packets; and missing sensors at a naturally observed regime change. Seeds, onset, duration, channels and original/modified hashes are retained. Delayed packets retain their old timestamps and are rejected from current-cycle state; they are not relabeled as fresh measurements. No NASA files are modified.

D4 re-executes reference, congested and staggered/technician-limited conditions. Additional economic grids re-score fixed executed actions and are explicitly not reoptimization. Paired uncertainty resamples engines, first averaging that engine's repeated scenarios/conditions. More scenario rows do not create more independent engines.

Global tick equals individual cycle plus a fixed, declared offset. Engines age through queueing and service: a conservative hypothetical threat-clock assumption, not a physical grounded-aircraft model. Completion occurs after positive lead and service durations; failure wins ties. Engines leave at first completed service or failure. One uninformative reviewer takes two ticks and authorizes conservative replacement; no true RUL is revealed by review. Technician capacity and bay occupancy are explicit. No post-repair trajectory is invented.

Reference costs are failure10, completed service1, discarded life0.05/cycle, order-to-start delay0.1/cycle, committed-order downtime0.05/cycle and completed review0.2. Units are hypothetical. The saved `queue_wait` includes compulsory mobilization lead; it is the full order-to-start wait, not exclusively capacity queueing. `maintenance_delay` records that same total delay. Downtime begins at order commitment under this declared model. Review requests and completed reviews are distinct.

Acceptance separates engineering completion from scientific advantage. Exact population/lineage, causal inputs, executable resource/timing constraints, independent costs and preserved history are required engineering gates. A risk candidate needs at least 5% paired cost improvement, an engine-bootstrap upper difference below zero and no incrementally failed engines to earn a developmental advantage. No criterion is relaxed after observing results. Even a developmental advantage would not supply fresh scientific promotion eligibility.
