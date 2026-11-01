# Corrected claim register ? 1 November 2026

| Claim | Current evidence and permitted wording |
|---|---|
| Real causal scheduling inputs | Supported: saved FD001/FD002 predictors; labels can be changed or removed without changing profiles or open-loop dispatch. |
| Correct constrained execution | Supported for the declared synchronous, ageing-through-service simulator: 16 runs / 2,872 engine episodes independently scored. No real repair-effect claim. |
| Risk-aware scheduling is better | Unsupported. The uncalibrated margin heuristic ties RUL priority and loses to FCFS under the tested bottlenecks. |
| All four subsets actively serve | False. FD001/FD002 serve; FD003/FD004 are browsing/research coverage only. |
| MATLAB integration is implemented | Supported locally: fitted .mat files, predictions and execution logs exist. Public GitHub-alone reproduction remains incomplete. |
| Zero dangerous errors implies safety | Unsupported. FD004 full-life RegimeLightGBM has dangerous overestimates on 10/49 evaluation engines despite 0/5 near-failure endpoint events. |
| Retraining is real | Supported: genuine FD001 Ridge and FD002 LightGBM fits, exact common development populations, uncapped truth, persisted predictions and required MLflow runs. |
| Scientific automatic promotion is demonstrated | Unsupported. Fresh labelled batch/acceptance cohort is absent; normal promotion stays blocked. FD001 also misses the 2% numerical hurdle and FD002 worsens RMSE. |
| Durable governance | Supported as an isolated engineering lifecycle test: prediction changes, real process/container restart, durable rollback, artifact hash verification and replay pinning. The test activation is not scientific approval. |
| Fabricated fallback evidence removed | Corrected in audited serving/governance paths: unknown scores remain unavailable; missing/corrupt required evidence fails visibly. |
| Production security is proven | Unsupported. Operator authentication and origin guards pass scoped tests; no comprehensive security certification is claimed. |
| Browser integration is verified | Not run. The browser tool returned no surfaces and rejected in-app browser creation. Frontend build and real HTTP integration passed. |
| Competition-grade reliability | Not established. See the unresolved gates in acceptance.json and REPORT.md. |

All claims are bounded by the saved protocols, populations and source snapshots in the new evidence directories. Historical Phase A/B research conclusions are unchanged.
