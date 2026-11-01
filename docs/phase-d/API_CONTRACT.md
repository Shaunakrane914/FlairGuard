# Phase D API and operator contract

Existing authenticated administrative routes remain in place. No new write endpoint runs a research experiment or changes a champion.

| Route | Contract |
|---|---|
| `GET /api/v1/reliability/summary` | Hash-bound accepted run, explicit retrospective scope, protocol/lineage, all condition/policy results, conditional fixed-cost reweighting ranges and FD004 diagnostic. `uncertainty_scope` states that shared queues are held fixed, so these are not new-fleet confidence intervals. Missing or changed required evidence is 503. |
| `GET /api/v1/reliability/ledger?run_id=...` | Complete benchmark proposal/commit/review/start/completion/failure events and evaluator-only outcomes. This is labeled research, separate from live inference. Invalid path-like identities are rejected. |
| `GET /api/v1/replay/{id}/export` | Current committed observed prefix, pinned model/release, current namespace and orders. No future telemetry is returned. |
| `GET /api/v1/models/history` | Durable SQLite release/operation history and artifact hashes. |
| `POST /api/v1/predict` | Explicit null/missing required sensors produce an unavailable forecast with quality reason; no substituted RUL. |
| `POST /api/v1/replay/{id}/step` | Serialized per session, causal inference and committed decisions. Missing values are null on the wire; the ledger preserves explicit nonfinite provenance. |
| `POST /api/v1/work-orders/{id}/transition?namespace=...` | Authenticated administrative workflow; acknowledgement/closure are not physical repair or simulated maintenance execution. |

Engine listings now expose `split`, `last_observed_cycle`, `last_predicted_rul`, `last_prediction_usable`, `current_status` and `active_work_order_id`. Unobserved assets are UNKNOWN, not certified nominal. The frontend uses these real fields rather than assumed names. Dataset conditions/fault-mode counts are numeric, and the NASA schema has 21 sensor channels.

The browser keeps the operator key only in session storage, restores replay identities after refresh, reconnects to persisted sessions, and carries the actual namespace into maintenance views. It disables stepping before a session is ready and serializes playback requests. The server pins the original model through restart/promotion, preserves fault/reset state and returns honest degraded-input evidence.

The research tab reads actual sealed benchmark artifacts. It does not apply the experimental classifiers or missingness-aware model to accepted operational sessions. FD003/FD004 remain research/browsing coverage; their active serving capability is explicitly false. No public/cloud deployment or comprehensive industrial security certification is claimed. The configured operator key and origin guards remain required for mutations.
