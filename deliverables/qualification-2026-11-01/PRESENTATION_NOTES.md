# FlairGuard AI — TELIPORT S4 Qualification Presentation Notes

**Case Study 1:** Connected Fleet Predictive Maintenance  
**Deliverable Version:** Qualification 2026-11-01 (Single-Slide Official Portal Format)  
**File Formats:** Editable PPTX (`FlairGuard_Qualification.pptx`), Rendered PDF Preview (`FlairGuard_Qualification.pdf`), High-Resolution Image (`FlairGuard_Qualification.png`), and Playwright Browser Demonstration Screenshots (`screenshots/`).

---

## 1. Slide Layout & Metadata

- **Template Compliance:** Built strictly on the official **TELIPORT Season 4** template with original Tata Elxsi branding, dimensions (16:9 widescreen, 12,192,000 × 6,858,000 EMU), and typography (Calibri design font).
- **Candidate Fields:** Left blank for team entry as requested:
  `Team: __________________    Members: __________________    College: __________________    Team ID: __________`
- **Slide Title:** **FlairGuard AI**
- **Core Problem Statement:** *Maintenance decisions when telemetry is missing, unreliable or constrained by service capacity.*

---

## 2. End-to-End Architecture (Causal Observations to Auditable Maintenance Actions)

The 5-node flow chart illustrates how telemetry flows causally into physical depot actions without lookahead leakage:

1. **Telemetry + Features**
   - 21 sensor channels, 3 operational settings.
   - Strictly past-only rolling feature windows (window lengths 5 and 20).
   - Sensor imputation is derived exclusively from training-fit distributions by operating regime.
2. **RUL + Anomaly Models**
   - Multi-model ensemble: LightGBM / HistGradientBoosting / Ridge regression.
   - Operating condition clustering and regime-aware normalization.
   - Zero lookahead: trajectory evaluation respects causal prefix boundaries.
3. **Telemetry Trust & Signal Integrity**
   - Real-time sensor missingness, freeze, and staleness detection.
   - Persistence tracking and model abstention when data quality falls below threshold.
   - Degraded-telemetry recovery: prevents premature failure triggers from isolated sensor dropouts.
4. **Rule-Based Triage**
   - Deterministic RUL thresholds and data quality gating.
   - Escalation to human operator review for edge-case faults and conflicting signals.
   - No black-box autonomous overrides on ambiguous telemetry.
5. **Orders + Execution**
   - Priority-ranked maintenance dispatch and deduplication.
   - ACID-compliant SQLite audit trail for all emitted work orders.
   - Cross-process durable recovery: sessions and active work orders survive application and backend restarts.

---

## 3. MATLAB Research Integration

- **Role:** Asynchronous background analysis worker running authenticated jobs via MATLAB R2026b (`matlab -batch`).
- **Algorithm:** Similarity-based Remaining Useful Life (RUL) estimation using historical degradation libraries.
- **Scientific Integrity:**
  - Evaluated on identical test engines and identical available prefixes as the Python models.
  - Integration serves as a rigorous comparative research benchmark, **not** an operational claim of superiority over Python.
  - Python serving remains fully functional and decoupled even when the MATLAB runtime is offline or unlicensed.
- **Artifacts:** Full execution logs, input SHA-256 hashes, and output tables sealed in `artifacts/integration_release/matlab-api-v2/`.

---

## 4. The Three Pillars: Trust, Value, Execution

### Pillar 1: TRUST (Scientific & Methodological Rigor)
- **Engine-Disjoint Splits:** Normalization parameters and scalers are fitted exclusively on training engines; test trajectories are never observed during feature engineering.
- **Causal History Guardrails:** All rolling aggregates reject future rows.
- **Explicit Signal Missingness:** When sensors drop, models abstain rather than inventing synthetic sensor readings.
- **Blocked Promotion Gate:** Retraining on historical research labels correctly flags that fresh acceptance labels are required before scientific champion promotion can occur.

### Pillar 2: VALUE (Operational Fleet Reliability)
- **Sensor Outage Mitigation:** Under an induced FD002 sensor outage scenario, regime-aware imputation produced **0/80 modeled fleet failures**, compared to **14/80 modeled failures** with a naive bounded countdown.
- **Constrained Depot Scheduling:** Evaluates maintenance dispatch under realistic depot bay limits and turnaround times rather than assuming infinite servicing capacity.
- **Actionable Economic Tradeoffs:** Direct comparison of maintenance costs (planned service vs. unscheduled engine failure penalties vs. queue wait times).

### Pillar 3: EXECUTION (Production-Grade Software Engineering)
- **FastAPI Backend + React Frontend:** 119/119 backend integration and unit tests passing.
- **Durable State Management:** Sessions, work order statuses (`ACKNOWLEDGED`, `COMMITTED`), and model release pins survive server crashes and container restarts.
- **Browser-Verified Workflows:** 100% passing Playwright end-to-end tests across desktop and mobile viewports with zero unhandled exceptions or console errors.

---

## 5. Scope & Empirical Boundaries

- **Data Origin:** Retrospective study based on the NASA C-MAPSS turbofan degradation benchmark (FD001–FD004).
- **Population Coverage:** 332 full-life policy runs independently scored across 169 source engines.
- **Honest Limitations:** Maintenance cost models are stylized and scenario-dependent. Advanced dispatch policies and candidate models require field validation and fresh acceptance cohorts before industrial production deployment.

---

## 6. Official Speaker Notes (Embedded in PPTX)

```text
Sources: docs/phase-d/RESULTS.md; artifacts/phase_d/reliability-v1-run002/summary.json, FD002/causal_trigger/reference, regime_impute versus bounded_last, point policy, 80 engines. Failure counts are modeled, not field safety outcomes. Primary cohort has 169 distinct source engines; repeated policy episodes are not independent engines. MATLAB evidence: artifacts/integration_release/matlab-api-v2/report.json and its sealed job outputs, plus final genuine Chromium job workflow. MATLAB/Python serving roles remain distinct. Scientific promotion remains blocked without fresh acceptance labels. All team fields intentionally blank at user request. Architecture uses causal windows 5 and 20, fit-derived regime scaling, quality gates, deterministic thresholds and durable work orders; no LLM is involved. FD001/FD002 serve; FD003/FD004 are retrospective research/browsing. Required qualification format is one slide, as specified by the user.
```

---

## 7. Captured Application Screenshots (in `screenshots/`)

| Screenshot File | Demonstrated Operator Workflow |
|---|---|
| `01-fleet.png` | Fleet Overview with live KPI counters, asset health indicators, and dataset selector |
| `02-fault-and-real-order.png` | Scenario Lab with causal telemetry replay, injected sensor fault, and active work order emission |
| `02b-missing-telemetry.png` | Degraded telemetry handling: missing sensor indicators, model abstention, and quality flags |
| `03-genuine-training-blocked-promotion.png` | Model Governance: genuine Challenger training, automated evaluation gate, and blocked promotion alert |
| `04-research-ledger.png` | Reliability Research: executed-action audit ledger with per-cycle cost accounting |
| `05-mobile-evidence.png` | Responsive mobile inspection: zero horizontal scroll overflow on 390px viewport |
| `06-matlab-real-job.png` | MATLAB Analysis Center: completed asynchronous job progress, matched prefix error table, and export |
