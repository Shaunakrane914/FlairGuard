# FlairGuard: MATLAB integration, frontend completion and presentation

Status: proposed execution plan. No implementation or deck edits are included in this planning step.

Starting point: Phase D on `fix/scientific-operational-integrity`, source checkpoint `28bb87cc9289b9cb465e0976b9b48390ad2f9193`. Preserve all accepted experiments and historical decks. Use new versioned output directories and reviewable commits during implementation. No push, merge or external submission is part of this plan.

The objective remains maintenance decision quality under unreliable telemetry, assessed through Trust, Value and Execution. MATLAB adds an accessible analysis capability. The frontend makes the operational workflow usable. The presentation communicates demonstrated capability and measured limitations.

## Stage 1: Integrate MATLAB into the application

### Intended result

An operator can launch an authorized MATLAB analysis, follow its status, and inspect genuine MATLAB/Python comparisons in FlairGuard. Ordinary Python serving remains available when MATLAB is absent. MATLAB analysis does not silently replace an operational champion.

### Work

1. Inspect installed MATLAB/toolbox/license capabilities and the existing saved `.mat` model. Preserve the Phase D FD003 similarity experiment as the initial verified comparator. Do not portray that single-subset comparator as an FD001–FD004 deployed predictor.
2. Define versioned contracts for analysis requests, observed telemetry prefixes, model/preprocessor identities, output predictions, timing, availability, metrics, provenance and errors. Separate observed-prefix prediction from retrospective evaluator-only scoring.
3. Add an authenticated asynchronous analysis-job API and a local MATLAB worker. Start with the already verified `matlab -batch` route; assess a persistent MATLAB Engine only if compatibility and measured startup/throughput justify it. Keep MATLAB execution out of synchronous HTTP requests and the standard Python container.
4. Persist queued/running/completed/failed/interrupted job states, artifact references and audit events. Use fixed allowlisted MATLAB functions, validated inputs, bounded runtime, cancellation and idempotent job handling. Never accept arbitrary MATLAB code or unrestricted filesystem paths from a request.
5. Save immutable run directories containing model/input hashes, preprocessing lineage, actual MATLAB version/toolbox details, logs, full-precision predictions and execution times. Expose sealed Phase D MATLAB evidence through a read-only, hash-verified API even without a current MATLAB license.
6. Compare MATLAB with the Python baseline on identical engines, observed prefixes, query cadence and maintenance constraints. Report both common-valid-row errors and each method's availability. Record RMSE, MAE, asymmetric NASA score, dangerous overestimation, latency and executed maintenance costs. Measure comparable Python timing before making speed claims.
7. Implement explicit unavailable, license-error, timeout, malformed-output and interrupted-worker states. An unavailable MATLAB runtime must produce an honest status rather than substituted Python results labeled MATLAB.

### Deliverables

- MATLAB adapter/worker and versioned request/result schemas.
- Persistent authenticated job API, read-only result/provenance endpoints and setup instructions.
- One genuine end-to-end MATLAB job with matched Python comparison and sealed evidence.
- Regression coverage for job state, authentication, malformed inputs, restart and unavailable-runtime behavior.

### Acceptance

- A real API-created job invokes MATLAB and returns traceable predictions from the saved/fitted MATLAB model.
- Repeated/restarted requests cannot duplicate a committed result or report an interrupted job as successful.
- No future observations or evaluator labels enter a prediction job.
- Independent scoring reproduces any reported maintenance cost.
- Python serving works with MATLAB disabled; champion releases remain unchanged.
- Numerical losses and missing-input coverage differences remain visible. Integration success does not require MATLAB to beat Python.

## Stage 2: Complete the operator frontend

### Intended result

A consistent, responsive application supports fleet inspection, replay, maintenance planning/orders, MATLAB comparison and evidence review. The interface makes observation quality and execution state clear at each decision.

### Work

1. Audit every existing view against its real API and remove obsolete claims, placeholder metrics and confusing navigation. Define shared typography, spacing, colors, chart styles, forms, tables and keyboard/focus behavior before redesigning individual pages.
2. Create a coherent application shell with primary navigation and visible dataset, telemetry mode, model version and service readiness. Move operator credentials into an appropriate session/settings workflow. Preserve authenticated administration and avoid claims of enterprise identity management that have not been implemented.
3. Complete these workflows:
   - **Fleet:** actual observed status, searchable/filterable assets and clear selection into diagnostics.
   - **Engine diagnostics:** readable telemetry, RUL history, missingness/staleness, quality reasons and model provenance.
   - **Replay:** clear step/play/pause/reset/fault controls, cycle position, recovery status and committed-prefix export.
   - **Maintenance:** proposed decisions, committed orders and executed simulated service displayed as distinct states. Acknowledgment and closure do not imply physical repair.
   - **Planning:** real resource constraints, queue/service timeline, utilization and outcomes from actual scheduler execution. If a page displays a sealed benchmark, identify it as a benchmark; do not imply that it controls live depot resources.
   - **Research and MATLAB:** actual job progress, Python/MATLAB forecast and availability comparison, cost/safety tradeoffs, run selection, provenance and ledger export.
   - **Model governance:** genuine retraining status, persisted history, champion/challenger identity and explicit scientific promotion blockers.
4. Separate retrospective truth overlays from causal replay. Show true RUL only in explicitly labeled evaluator/research views. FD003/FD004 active-serving controls remain unavailable until separately implemented and validated.
5. Implement loading, empty-data, permission, API-error, runtime-unavailable and interrupted-job states. Maintain selected engine/dataset/session through navigation and refresh. Prevent stale requests or repeated clicks from changing the wrong session.
6. Test desktop, tablet and mobile layouts. Use accessible labels, readable contrast, usable tables and charts, keyboard navigation and focus states. Prefer useful telemetry plots and explanations over decorative graphics.
7. Extend genuine Playwright coverage to include the MATLAB job workflow, errors, session persistence and the complete operator journey. Capture new screenshots, traces, console/API errors and final build evidence.

### Deliverables

- Complete React/TypeScript frontend using shared components and real APIs.
- Integrated MATLAB analysis/comparison experience.
- Updated API contracts for any required narrow backend additions.
- Executed browser tests, responsive screenshots and a repeatable demonstration script.

### Acceptance

- Fleet selection, telemetry inspection, fault injection, decision/order review, refresh and backend restart work together in the real browser.
- MATLAB job/results remain distinguishable from Python serving and from historical results.
- Displayed forecasts, costs and action counts reconcile with saved API/ledger evidence.
- No blocking browser errors, broken core controls, misleading success states or horizontal page overflow at the tested sizes.
- Production build and affected regressions pass. Rerun container verification if runtime contracts/deployment paths change.

## Stage 3: Complete the TELIPORT PPT

### Intended result

A finished editable presentation explains the problem, system, MATLAB contribution, working operator flow and measured evidence. Its claims match the delivered application.

### Work

1. Inspect the supplied TELIPORT template and submission instructions. Preserve the required slide count, team fields, branding and format. Because qualification was previously prioritized, finish the required submission-format deck first. A longer technical companion is secondary and should be produced only when required for the judging/demo format.
2. Audit the existing six-slide and single-slide submissions. Replace obsolete claims about data partitions, untouched test data, self-healing, automatic promotion, latency and planned functionality with current evidence. Preserve original deck files.
3. Build the narrative around the audience's decision:
   - The maintenance problem under unreliable telemetry.
   - The implemented architecture and MATLAB's precise role.
   - The operator journey, illustrated with final application screenshots.
   - Trust: telemetry failures, recovery availability and remaining dangerous errors.
   - Value: executed maintenance costs and safety tradeoffs against simple baselines.
   - Execution: persisted orders, causal replay, actual browser/container restart verification.
   - Demonstrated scope, limitations and next validation step.
   Compress this narrative into the official format rather than exceeding its limits.
4. Use final Stage 1/2 results and screenshots. Keep native text, charts and required diagrams editable. Add source/run references and concise speaker notes. Separate hypothetical normalized costs from real financial savings and repeated engine episodes from distinct source engines.
5. Explain MATLAB as a genuine integrated comparator/analysis capability. Retain its negative or mixed numerical results. Do not imply that integration establishes predictive or industrial superiority.
6. Render every slide and inspect text fit, legibility, alignment, charts, branding and image quality. Check all numbers against the evidence and remove unsupported claims. Export the editable PPTX and a PDF preview, retaining the original files and reproducible authoring source.

### Deliverables

- Completed official-format PPTX and rendered PDF preview.
- Updated team information where already available; unresolved required fields flagged explicitly rather than invented.
- Final demo screenshots and concise presentation/demo notes.
- A claim-to-evidence checklist and versioned authoring source.

### Acceptance

- Required template/slide limits are met and every required field is complete or explicitly identified as missing.
- Every numerical claim is traceable to an executed result with its population and units.
- No slide claims fresh promotion, general advanced-policy superiority, physical repair or field validation without supporting evidence.
- Every slide has been visually inspected and remains editable where required.
- The presentation matches the application's final behavior and can support a repeatable demonstration.

## Execution order and completion report

Execute Stage 1 before completing Stage 2, then freeze evidence/screenshots for Stage 3. A frontend design audit and PPT content inventory can begin earlier, but final comparison screens depend on MATLAB contracts and final slides depend on the finished product.

At each stage, record source changes, reproduction commands, executed checks, versioned evidence and a PASS/FAIL/BLOCKED/NOT RUN report. Keep prior acceptance results intact. Any newly discovered scientific or licensing limitation must remain visible rather than being hidden to complete a demonstration.
