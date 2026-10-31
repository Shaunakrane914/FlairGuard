# FlairGuard AI: stronger competitive strategy and proof requirements

**Date:** 31 October 2026. **Scope:** strategy refinement only, as requested. No application fixes, training runs, repository migration, public commits or deployment are authorized by this document.

This is the short decision document to use alongside the [technical architecture review](architecture-review-2026-10-31/FLAIRGUARD_ARCHITECTURE_REVIEW.md). It narrows the research priorities and strengthens the evidence gates; it does not replace the detailed audit or claim that any planned result has been achieved.

## 1. The competitive objective

Build FlairGuard around this question:

**When sensor evidence becomes unreliable, can the system preserve useful maintenance decisions, control human workload and prove that its actions actually occurred?**

Proposed positioning:

> FlairGuard predicts remaining life, checks whether the available evidence supports using that prediction, and turns justified decisions into traceable maintenance work orders. Its behavior is tested against simpler policies under declared operating and sensor-quality conditions.

This is an engineering hypothesis to demonstrate. It is not an established safety guarantee or a claim of scientific novelty. Strong predictions, reliable decisions and correct execution must all be measured; an attractive architecture and a high review score establish none of them.

Correctness repairs are the entry requirement. The competitive contribution should be a focused, reproducible demonstration of decision quality under imperfect telemetry. A generic RUL dashboard, MLflow installation, MATLAB logo or large model list does not establish that contribution.

## 2. What changes from the original strategy

| Earlier direction | Stronger decision |
|---|---|
| Several promising differentiators pursued together | One central decision-reliability question, supported by three experiments |
| Calibrated intervals treated as a possible confidence signal | Separate calibration from error ranking; test whether a selector actually identifies unreliable predictions |
| Sophisticated maintenance policy as the desired destination | Tuned simple RUL policy remains the comparator and may remain the final deployed policy |
| Four-subset coverage as a broad target | Establish FD001 and FD002 depth first; FD003/FD004 remain the next coverage extension |
| Small internal holdout with multiple ambitious superiority gates | Assess statistical power before claiming improvement; more corrupted rows do not create more independent engines |
| Independent MATLAB model as a prominent differentiator | Optional falsifiable engineering experiment; a negative result or deferral is acceptable |
| Large specification as the main handoff | A small experiment register, claim register and evidence package govern development |

The original architecture remains appropriate for the product. The research story needs stronger prioritization and more precise claims.

## 3. Literature: useful methods are already established

The research search changes what we can honestly call distinctive:

| Existing work | Verified scope | Implication for FlairGuard |
|---|---|---|
| Javanmardi and Hüllermeier, *Conformal Prediction Intervals for Remaining Useful Lifetime Estimation* (2022) | Describes conformalizing CNN and gradient-boosting RUL predictors on C-MAPSS. [Primary abstract](https://arxiv.org/abs/2212.14612). | “We added conformal intervals to gradient boosting” is not a novel research claim. |
| de Pater, Reijns and Mitici, *Alarm-based predictive maintenance scheduling for aircraft engines with imperfect RUL prognostics* (2022) | Integrates evolving imperfect forecasts, alarm rules and maintenance scheduling. [University publication record](https://research.tudelft.nl/en/publications/alarm-based-predictive-maintenance-scheduling-for-aircraft-engine/). | Thresholds, persistence, safety factors and scheduling already have substantial precedent. Use them as strong comparison ideas. |
| Jiang, Zhao and Wang, *Risk-Controlled Selective Prediction for Regression DNN Models* (2020) | Studies regression rejection using prediction risk versus coverage. [Primary publication abstract](https://ieeexplore.ieee.org/document/9207676/). | Refusing uncertain predictions must be evaluated as a trade-off, not treated as automatically safer. |
| Shah and colleagues, *Selective Regression Under Fairness Criteria* (ICML 2022) | Shows that overall selection benefits need not improve every subgroup. [Author-hosted paper](https://sia.mit.edu/wp-content/uploads/2022/08/2022-shah-bu-lee-das-panda-sattigeri-wornell-icml.pdf). | Check operating-regime and life-stage outcomes; aggregate accepted error can hide a failing subgroup. |
| *Regression with Cost-based Rejection* (NeurIPS 2023) | Explicitly treats rejecting a prediction as incurring a cost. [Primary paper](https://papers.nips.cc/paper_files/paper/2023/file/8ddcba644f602835a52b962d9a119eea-Paper-Conference.pdf). | Human review cannot be a free escape from difficult engines. |

These sources support the research direction, not FlairGuard performance. No published numeric score is imported as a directly comparable baseline. The search is targeted, not an exhaustive novelty review. One later search result also describes conformalized selective regression; its publisher page was inaccessible through the reader, so its detailed guarantees are not used here.

The defensible competition distinction is the quality of the implemented evidence and the coherence of the decision/workflow demonstration. A new scientific method would require an additional literature review and experimental contribution.

## 4. Three experiments that determine whether we are better

### Experiment 1: does the validity gate identify consequential prediction errors?

**Hypothesis:** a quality- and operating-support gate reduces consequential errors among automatically used predictions, while retaining useful automation and controlling referrals.

Hold the RUL predictor fixed. Compare:

1. Predictor with required schema checks and otherwise unconditional use.
2. The same predictor with transparent sensor-quality and operating-support rules.
3. A learned error-ranking or adaptive-interval selector only if the transparent rules leave a measurable gap.

Required comparators include random rejection at matched coverage and a simple conservative threshold strategy. An evaluator-only oracle can bound achievable selection performance, but is never a deployable comparator. Compare policies on the same input histories, not separately selected “easy” engines.

Report accepted MAE and asymmetric error, automation coverage, rejected-case error, referral episodes, review duration and performance by operating regime and life stage. Also report complete policy outcomes including rejected cases. Two different quantities must be named clearly: **automation coverage** is the fraction handled automatically; **interval coverage** is the fraction of true RUL values inside reported intervals.

A proposed initial selection budget is at most 10% referrals on the clean endpoint population, with a 5/10/20% budget curve. Freeze the budget and selector thresholds on development data. This endpoint budget does not establish a bounded per-life operational workload; the replay experiment separately measures referral episodes and their costs.

**Reject the hypothesis** if reduced accepted error merely comes from deferring nearly every difficult or near-failure engine, if random rejection performs comparably, or if full outcomes deteriorate after review cost/delay. Do not advertise accepted-subset performance as all-fleet performance.

### Experiment 2: does the decision rule earn its operational cost?

**Hypothesis:** under declared measurement corruption and maintenance lead times, the proposed gate/fallback policy improves the cost/failure/workload frontier relative to a tuned simple RUL policy.

Use a small policy ladder:

| Policy | Role |
|---|---|
| Tuned fixed-age maintenance | Strong age-only operational comparator |
| Tuned point-RUL threshold | Primary comparator; not frozen at the old arbitrary 25-cycle value |
| Point-RUL threshold plus the validity gate and explicit fallback | Main FlairGuard candidate |
| Calibrated lower-bound scheduling | Conditional challenger if interval behavior supports its use |

First compare policies using the **same saved predictor** to isolate policy value. Only then compare different predictors. A larger safety margin and earlier maintenance may explain a result without any unique benefit from the gate; include a more conservative simple threshold tuned to the same failure/workload target.

A rejected prediction must lead to a specified outcome: bounded use of stale evidence, a review request with delay, conservative maintenance or another declared fallback. It cannot disappear from scoring. Last-valid estimates are marked stale; any countdown/fallback horizon is an assumption tested in replay, not newly calibrated confidence. A human acknowledgement is not a perfect inspection. If inspection outcomes are simulated, label their assumed accuracy and cost and include an uninformative-inspection case.

Service requires a committed order and declared execution time. Count failure if service completes at or after the failure cycle, using the same convention for every policy. Record proposed action, committed action, execution, outcome and cost as separate events. End an episode after first failure or service; do not invent the repaired engine's subsequent life.

Primary outputs: cost per engine-life, failures, unused life, reviews, service lead time and unresolved cases. Show Pareto frontiers over predeclared costs/lead times and clean versus corrupted conditions. Freeze a reference economic scenario before evaluation; label all costs hypothetical. Show zero-corruption conditions, where additional policy complexity may properly lose.

**Promotion target:** at least 5% cost reduction against the tuned comparator in the frozen reference scenario, with uncertainty supporting improvement, plus a separately justified failure-risk noninferiority criterion. The exact risk margin and statistical power must be settled before the study. This is a research target, not an achieved result. If the sample cannot support the criterion, call the result inconclusive; do not weaken the margin after inspecting outcomes.

**Reject the advanced policy** if it increases cost without a demonstrated risk/workload benefit, depends on unusually favorable inspection assumptions, or wins only after choosing costs post hoc. Deploying the verified simple policy is a valid final outcome.

### Experiment 3: does the action survive real software failures?

**Hypothesis:** a replay produces the same scientific decisions and executed actions despite duplicates, process restarts and declared event-order handling.

Test review-to-critical escalation, an identical event retried after closure, concurrent requests, two subsets sharing engine ID1, a missing block followed by recovery, changing-but-slow sensor values, out-of-order input and interruption at transaction boundaries.

Required invariants:

* One committed outcome per accepted event key; identical retry returns that result.
* No human-review status can erase urgent priority or silently block a required action update.
* No service event without its committed order and valid execution transition.
* Restart preserves the event watermark, model/policy version and reconstructable feature/persistence state.
* Cost totals reconcile exactly with executed-action records.

Compare uninterrupted and restarted runs using normalized scientific outputs, excluding wall-clock timestamps. Fault injection in the software process is labeled separately from synthetic sensor faults. This experiment proves workflow integrity under tested conditions, not physical safety or superior ML accuracy.

## 5. Strengthen the protocol before trusting those experiments

### Calibration is not a reliability ranking

Basic split conformal residual intervals have essentially constant width `2q` before domain clipping. They do not distinguish a well-supported individual prediction from a poor one. Clipping the lower endpoint at zero can make near-failure intervals look narrower for a purely mathematical reason.

Start with explicit input-quality/support evidence for rejection. If adaptive intervals or an error-ranking model are later introduced, train them with appropriately out-of-fold residuals inside development data, calibrate separately and test their ranking value. Do not present model disagreement, interval width or an OOD score as a calibrated probability of being wrong.

Standard marginal interval coverage also does not automatically hold after selecting only “trusted” predictions, under new sensor corruption, or at the adaptive time when a maintenance action triggers. Measure those populations separately. If only marginal clean-endpoint coverage is established, state exactly that.

### Fix the independent unit and sampling population

An engine is the independent evaluation unit for the proposed generalization study. Thousands of prefixes, corruption seeds or repeated folds do not create thousands of new engines. Keep every engine's clean/corrupted scenarios together when splitting and estimating paired uncertainty. Report training/selection variability separately; overlapping training folds limit simple independence interpretations.

The architecture's proposed 60/20/20 split gives FD001 only20 outer-evaluation engines. That is suitable for a pilot and defect detection, not automatically enough to establish a small cost gain or rare-failure improvement. First perform a development-only power/precision assessment and freeze the final sampling and acceptance plan.

If more use of the finite training pool is needed, a preregistered nested engine-level cross-validation protocol can provide out-of-sample predictions across more engines. All model, selector and policy tuning must remain inside each outer training partition. Any interval calibration excludes that outer engine. Report dependence and fold variability honestly; rotating outer folds does not manufacture a large new untouched fleet.

Internal results guide the method; a sealed later evaluation gives final confirmation. Existing FD001 official test results remain exposed diagnostic evidence. A newly created holdout cannot undo historical exposure. Do not use official test endpoints to choose policy, corruption severity, selector or ensemble weights.

Specify prefix cutoffs before examining errors. A rule that samples only “interesting” RUL bands changes the task. If preset cutoffs exceed an engine's observed lifetime, record the resulting unavailable/early-failure episode according to the protocol rather than silently replacing it with an easier sample. Full-life policy replay and endpoint regression are separate evaluations.

### Use defensible corruptions

Perturb held-out raw channels and recompute features causally. Record sensor set, seed, onset, strength, duration and whether the injected event is censored by the available history. Use modest-to-severe standardized sweeps, both signs of bias/drift, single-channel and correlated measurement errors, quantization and missing blocks. Do not perturb cycle IDs or rolling means independently and call it a sensor experiment.

Sensor corruption changes the measurement, not the engine's true failure time. A novel operating regime is tested with actual held-out setting/sensor combinations, not arbitrary settings edits with physically unrelated sensor values. A health-deviation score cannot be labeled true fault onset when C-MAPSS lacks that event label.

## 6. Scope: where engineering effort goes

| Priority | Deliverable | Why it belongs |
|---|---|---|
| Required foundation | Fix quality, transactional orders, idempotency and simulator truth; serialize models and freeze experiments | Otherwise every later claim can be invalidated by known defects |
| Core evidence | FD001 plus FD002, one strong classical predictor, transparent validity gate and tuned policy baselines | FD002 directly tests operating-condition handling; FD001 alone cannot |
| Core product | Real engine replay, uncertainty/validity explanation, committed work orders, model evidence, monitoring and labeled retraining | Meets the case-study workflow and demonstrates the central contribution |
| Next coverage | FD003/FD004 with the same declared protocol and appropriate heterogeneous-degradation treatment | Broadens evidence after the first mechanisms are understood |
| Conditional research | One HI/similarity comparator in MATLAB/Python; one compact sequence model if residual analysis justifies it | Each must answer a specific unresolved modeling question |
| Defer | Large ensembles, several deep architectures, elaborate inspection optimization, real CMMS integrations, synthetic turbine plant | More assumptions and implementation burden than the current evidence warrants |

Model shortlist: age-only/dummy, Ridge, HistGradientBoosting and LightGBM. Retain existing Random Forest results as a baseline; expand tuning only for a diagnosed reason. A stronger strategy does not predetermine that boosting, MATLAB, deep learning or the advanced policy must win.

MATLAB's proposed research question is narrow: **does a fit-only, regime-aware health indicator plus similarity estimation contribute complementary held-out error reduction or useful interpretable degradation evidence?** Compare the actual method against Python on identical prefixes. Language duplication alone is not independent scientific validation, and disagreement is not calibrated uncertainty. Keep the open-source production path fully reproducible.

## 7. The judge demonstration should test the central claim

Use one coherent sequence rather than unrelated feature screens:

1. Open a held-out engine with data/model/partition identity visible. Replay its actual available history and show a genuine forecast.
2. Show a declared sensor-corruption experiment alongside the unchanged clean control. The system exposes degraded evidence, its selected fallback and the review workload it creates.
3. Advance to a justified maintenance condition. Show the proposed decision, the committed order and execution evidence. Demonstrate that an existing review does not block critical escalation.
4. Repeat an event and restart replay. Show that the action ledger and economic outcome reconcile, without duplicate service.
5. Open the full-engine research result. Compare the tuned simple policy with FlairGuard at matched risk/cost/workload; show losses and inconclusive findings as well as improvements.
6. Demonstrate monitoring and a real newly available labeled historical batch triggering a challenger job and gate result. Preserve the distinction between unlabeled telemetry, censored service observations and true failure labels.

Call sensor corruption a measurement robustness experiment and service a retrospective simulated operational outcome. Stop official test replay at its last observed cycle. No controls that imply throttle optimization, repaired trajectories or proven lifespan extension.

The eventual pitch can make a specific earned claim such as “under this declared corruption and lead-time scenario, the validity gate improved these full policy outcomes at this referral cost.” Until measured, use “we test whether.” A generic claim that the system is safer than competitors remains unsupported.

## 8. Deliverable package and decision gates

Keep the next handoff small and executable:

| Artifact | Required content |
|---|---|
| Frozen protocol | Engine IDs, populations/cutoffs, fit/calibration roles, hypotheses, tuning budget, cost scenarios, primary objective and failure criteria |
| Run manifest | Source/data/environment/config hashes, versions, membership and access history |
| Prediction evidence | Full-precision keyed clean/corrupted predictions, validity/interval status, truth isolated in evaluation outputs |
| Action evidence | Proposed/committed/executed events, order/model/policy IDs, actual event cycles, review/delay/cost components |
| Small results report | Error versus automation coverage; interval coverage/width; cost/failure/workload frontier; regime/life-stage results; reproducibility failures |
| Claim register | Each statement marked hypothesis, verified, unsupported or withdrawn, with its exact supporting artifact |

**Gate0 - Correctness:** every known audit defect has a behavioral regression case and the end-to-end action path agrees with persistence. No research-superiority claim yet.

**Gate1 - Predictive validity:** credible group-disjoint results and useful quality/error behavior on FD001/FD002. Failure of a method narrows or removes it; it does not trigger test-guided cherry-picking.

**Gate2 - Operational value:** an advanced policy earns a measured improvement/trade-off after all episodes and review costs are included. Otherwise use the tuned simple policy and explain why.

**Gate3 - Product evidence:** real serving, monitoring, work orders, labeled retraining and restart behavior reproduce from pinned artifacts. Website polish follows this contract.

The single next strategy action is to freeze the hypotheses and primary evaluation protocol for Experiment1 and Experiment2. After approval, PhaseA implementation should produce the corresponding evidence package. There is no reason to write another broad architecture or choose a new flagship model first.

## 9. Current repository observations and boundaries

Read-only inspection now finds local Git commit `8216f66` on `main`, with `origin/main` present. This is newer repository state than the original audit, which correctly recorded no Git repository at its inspection time. The current source still contains the verified rank collision, missing-key/flatline/gap defects and simulator decision-versus-action mismatch. These were source checks in this strategy turn, not a fresh training reproduction.

The supplied second review broadly agrees with the audit, but its architecture rating is subjective and its benchmark statements reuse prior evidence. It is not an independent performance replication. One hygiene statement needs precision: the nested project already ignores `artifacts/` and its own `data/raw/`, but legacy data and the generated database are tracked elsewhere/in Git. Adding ignore rules cannot untrack existing files. Preserve historical evidence and make any cleanup a separate, reviewable change; no deletion/history rewrite is proposed as competitive research.

The public [FlairGuard repository](https://github.com/Shaunakrane914/FlairGuard) was accessed read-only. A pre-existing local `.gitignore` modification was left untouched. The original architecture, code, tests, models/results, datasets, SQLite database and presentations are unchanged in this strategy refinement. The competition submission-format question remains a separate unresolved administrative requirement.
