# FD002 claim register

Evidence version: `fd002-v1-run002`. [Detailed results](RESULTS.md) and [frozen protocol](SPECIFICATION.md) govern interpretation.

| Claim | Status | Evidence / boundary |
|---|---|---|
| FD002 preprocessing accounts for fitted operating regimes before rolling aggregation | VERIFIED implementation | Fit-only normalization, prefix invariance and normalize-before-rolling tests; serialized normalizers |
| Regime normalization has lower held-out endpoint RMSE in this split | VERIFIED measurement |48.8844 versus50.3747; not a population-superiority or official-test claim; all-cycle NASA penalty is slightly worse |
| The learned selector outperforms matched random rejection | NOT ESTABLISHED | Primary MAE delta−2.2147, engine-bootstrap95% interval[−7.6928,+1.0344] |
| The learned gate improves maintenance Value | FAILED observed target |0% cost improvement; all800 final engine-scenario outcome signatures match tuned point RUL |
| Quality/referral checks automatically make the policy safer | UNSUPPORTED / counterevidence | Broad and decision-aware quality policies have11 primary failure episodes versus5 for point RUL |
| Missing telemetry is handled without important decision loss | FALSE in these experiments | Missing-case failure5/80; only66.5% full-life low-RUL prediction availability |
| Proposed, committed and executed actions reconcile | VERIFIED within experiment |5,760 episodes,5,585 executions, independent costs and delays, exact fast/store parity |
| Thousands of repeated episodes provide thousands of independent fleet samples | FALSE |80 final engine clusters; only63 available endpoint engines and six with low-RUL endpoints |
| Zero observed policy differences establish perfect economic power | WITHDRAWN and corrected | Development paired variance zero is NOT ESTIMABLE; regression prevents the earlier planning defect |
| Calibrated intervals are per-engine safety probabilities | UNSUPPORTED |17 effective calibration endpoints; marginal clean-endpoint scope only |
| Phase B has verified online serving crash durability | NOT IMPLEMENTED | Offline in-memory research ledgers become durable at backup; Phase A durable store behavior remains separately tested |
| The experiments prove real repair effects or real fleet savings | UNSUPPORTED | FD002 supplies run-to-failure measurements; costs/inspection behavior are hypothetical; no repaired life is fabricated |
| More work is needed before an advanced policy is promoted | REQUIRED | New decision-specific target and telemetry-recovery protocol; no tuning on the now-exposed final80 |
