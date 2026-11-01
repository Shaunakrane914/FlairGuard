# FlairGuard AI — TELIPORT S4 Qualification Presentation Notes

**Case Study 1:** Connected Fleet Predictive Maintenance  
**Deliverable Version:** Qualification 2026-11-01 (Single-Slide Official Portal Format)  
**File Formats:** Editable PPTX (`FlairGuard_Qualification.pptx`), Rendered PDF Preview (`FlairGuard_Qualification.pdf`), High-Resolution Image (`FlairGuard_Qualification.png`), and Playwright Browser Demonstration Screenshots (`screenshots/`).

---

## 1. Slide Title & Metadata

- **Project Title:** **FlairGuard AI — A Verified Connected-Fleet Reliability Platform**
- **Project Subtitle:** *Causal RUL prediction, telemetry-fault recovery and auditable maintenance decisions under constrained service capacity.*
- **Template Compliance:** Built strictly on the official **TELIPORT Season 4** template with original Tata Elxsi branding, dimensions (16:9 widescreen, 12,192,000 × 6,858,000 EMU), and typography (Calibri design font).
- **Identification Line:** `Team: FlairGuard | Case Study: 1`

---

## 2. Architecture Summary

**NASA C-MAPSS → Regime-Aware Prognostics → Telemetry Quality & Recovery → Deterministic Maintenance Decisions → Persistent Work Orders & Audit**

*FD001/FD002 operational serving; FD003/FD004 retrospective research coverage · MATLAB toolbox comparison integrated.*

### Component Workflow:
1. **NASA C-MAPSS:** 21 sensor channels, 3 operating settings; strictly past-only rolling feature windows (lengths 5 and 20).
2. **Regime Prognostics:** Multi-model ensemble (LightGBM / HistGradientBoosting / Ridge) with operating condition clustering and regime-aware normalization.
3. **Quality & Recovery:** Real-time sensor missingness, freeze, and staleness detection; persistence tracking and model abstention; 6 telemetry-recovery methods evaluated across 8 controlled conditions.
4. **Deterministic Decisions:** Deterministic RUL thresholds and data quality gating; escalation to human operator review for edge-case faults and conflicting signals.
5. **Work Orders & Audit:** Priority-ranked maintenance dispatch and deduplication; ACID-compliant SQLite audit trail for all emitted work orders; cross-process restart recovery.

---

## 3. The Three Pillars: Trust, Value, Execution

### Pillar 1: TRUST
> **Engine-disjoint training and causal inference; decision-horizon risk evaluation; six telemetry-recovery methods tested across eight controlled conditions.**
- Scalers and normalization parameters fitted exclusively on training engines; test trajectories are never observed during feature engineering.
- All rolling aggregates reject future rows (zero lookahead).
- Explicit abstention when data quality falls below operational thresholds.
- Retraining on historical research labels correctly blocks automatic promotion, enforcing the requirement for untouched acceptance cohorts.

### Pillar 2: VALUE
> **FD002 trigger-outage scenario: 0/80 modeled failures with regime imputation versus 14/80 with bounded countdown.**  
> *Scenario-specific retrospective result; no universal superiority claim.*
- In simulated multi-cycle sensor dropouts on complex multi-regime engines (FD002), regime-conditional imputation maintained safe triage and eliminated premature unpredicted failures.
- Constrained depot scheduler evaluates real depot bay capacity and turnaround durations rather than assuming infinite servicing availability.
- Concrete economic accounting compares planned maintenance cost against unscheduled engine failure penalties and queue delay costs.

### Pillar 3: EXECUTION
> **Working FastAPI + React operator platform, authenticated work-order workflows, restart-safe replay, model-version pinning, real MLflow training and rollback verification.**  
> **Real Chromium browser workflow and Docker restart checks completed.**
- 114+ passing backend unit/integration tests and automated property regressions.
- Durable state management: active sessions, work order statuses (`ACKNOWLEDGED`, `COMMITTED`), and model release pins survive server crashes and container restarts.
- End-to-end Playwright browser tests pass across desktop (1440 px) and mobile (390 px) viewports with zero unhandled exceptions or console errors.

---

## 4. Evidence Footer & Empirical Boundaries

> **114 passing tests · 332 primary policy runs · 17,822 scored engine episodes from 169 distinct source engines · Independent event-ledger verification · MATLAB toolbox comparison integrated**  
> *NASA C-MAPSS retrospective simulation; costs are hypothetical. Scientific model promotion requires fresh acceptance data.*

- **MATLAB Integration Role:** Connected as an asynchronous background worker (`matlab -batch`) executing similarity-based RUL estimation. Serves as a comparative research benchmark with sealed evidence; Python serving operates completely independently.
- **Population Integrity:** 332 policy runs across 169 distinct turbofan engines; repeated policy episodes are not treated as independent engines.
- **Honest Limitations:** Maintenance cost models are stylized and scenario-dependent. Industrial production deployment requires physical field validation.

---

## 5. Captured Application Screenshots (in `screenshots/`)

| Screenshot File | Demonstrated Operator Workflow |
|---|---|
| `01-fleet.png` | Fleet Overview with live KPI counters, asset health indicators, and dataset selector |
| `02-fault-and-real-order.png` | Scenario Lab with causal telemetry replay, injected sensor fault, and active work order emission |
| `02b-missing-telemetry.png` | Degraded telemetry handling: missing sensor indicators, model abstention, and quality flags |
| `03-genuine-training-blocked-promotion.png` | Model Governance: genuine Challenger training, automated evaluation gate, and blocked promotion alert |
| `04-research-ledger.png` | Reliability Research: executed-action audit ledger with per-cycle cost accounting |
| `05-mobile-evidence.png` | Responsive mobile inspection: zero horizontal scroll overflow on 390px viewport |
| `06-matlab-real-job.png` | MATLAB Analysis Center: completed asynchronous job progress, matched prefix error table, and export |
