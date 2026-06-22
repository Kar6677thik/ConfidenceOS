# ConfidenceOS

ConfidenceOS is a prototype read-only, trust-aware HMI compiler and Runtime for industrial control-system interfaces. It was built for the ABB accelerator theme "Next-gen control system interface", where the challenge is to reduce alarm fatigue, improve operator decision-making, and reduce HMI engineering effort.

The project explores one central idea:

```text
Raw alarms tell operators what changed.
ConfidenceOS tells operators what can still be trusted.
```

ConfidenceOS does not replace a DCS, PLC, SIS, historian, alarm system, or certified HMI. It sits beside existing systems as a read-only decision-support layer. It does not write tag values, setpoints, controller modes, pump starts, valve commands, or alarm acknowledgements.

## Current Prototype Status

This repository is a hackathon prototype with a working simulator-backed backend, generated Runtime manifests, Studio compiler workflow, role-based frontend, and operational handover views. Some integration paths are intentionally demo-scoped:

- OPC UA is represented as a read-only integration boundary, not a production connector.
- AI-assisted features are optional. Deterministic rules remain authoritative. If no valid LLM provider/model is configured, the system falls back to deterministic explanations.
- SQLite is used for prototype persistence.
- The simulator is designed to exercise confidence, mass balance, alarm collapse, and handover workflows. It is not a high-fidelity process simulator.
- Compliance outputs are prototype evidence reports, not legal plant records.

## Product Overview

ConfidenceOS has three primary workspaces:

### Studio

Studio is the engineering workspace for the HMI compiler.

It supports:

- dirty tag import
- deterministic tag mapping
- Mapping Court with evidence, counter-evidence, verdict, and approval requirement
- reusable template binding
- validation guardrails
- template tests
- generated Runtime preview
- publish guardrails
- generated screen receipts

The compiler pipeline is:

```text
Raw Tags -> Asset Graph -> Template Binding -> Validation -> Screen Generation -> Publish Readiness -> Runtime
```

### Runtime

Runtime is the generated trust-aware HMI surface.

It renders:

- semantic trust map navigation
- generated process mimic
- generated equipment faceplates
- trust states
- operating basis ledger
- abnormal situation workspace
- alarm collapse receipts
- operator action contract
- role-specific views
- screen receipts and provenance

During abnormal conditions, Runtime enters pressure mode and reduces the operator view to the essential operating basis:

1. abnormal situation
2. single safe move
3. do not trust
4. trusted substitute
5. decision freeze
6. exit condition
7. evidence

### Shift Channel

Shift Channel carries operational continuity across handover.

It shows:

- unresolved trust debt
- active verification tasks
- decision freezes
- operator notes
- operational event ledger references
- handover blockers

## Core Concepts

### Confidence Score

Each sensor receives a deterministic confidence score. The score is a governed trust rubric, not a calibrated probability.

The scoring engine uses:

- calibration evidence
- stability evidence
- cross-sensor evidence
- physical plausibility evidence

The backend exposes confidence explanations with formula, sub-scores, dominant factor, strongest evidence, counter-evidence, verdict, recommended action, and related assumptions.

### Trust States

Runtime is led by trust state instead of only displaying a percentage.

| Trust state | Meaning |
| --- | --- |
| `TRUSTED` | Signal can be used as normal operating evidence. |
| `DEGRADED` | Signal needs cross-checks before use as an operating basis. |
| `QUARANTINED` | Signal remains visible but cannot be used as the basis for blocked decisions. |
| `SUBSTITUTED` | A substitute or inferred measurement is being used as trusted supporting evidence. |
| `UNAVAILABLE` | No valid live sample is available. |

### Alarm Collapse

ConfidenceOS collapses related low-level warnings into a single abnormal situation. For example:

```text
low level confidence + mass-balance divergence + startup context
-> Inventory accumulation with unreliable level indication
```

The resulting situation includes affected sensors, evidence, counter-evidence, an operator question, and an action contract.

### Operator Action Contract

Advisory incidents include an action contract:

- `do_not_use`
- `trusted_substitutes`
- `first_safe_action`
- `blocked_decisions`
- `exit_conditions`

This is intended to make operator guidance explicit and auditable.

### Verification Workflow

Manual verification is represented as a task lifecycle:

```text
REQUESTED -> ASSIGNED -> FIELD_CHECK_DONE -> ACCEPTED -> EXPIRED
```

Verification tasks do not override confidence by themselves. They provide temporary field-verification evidence and handover traceability.

### Engineering Assumptions

Engineering assumptions are stored in `backend/assumptions.json`. Each assumption includes value, unit, source, owner role, confidence impact, review requirement, approval status, review dates, and MOC reference.

The assumption register is visible in the Engineer and Compliance surfaces.

## Asset Models And Templates

The prototype includes two asset models:

| Asset model | File | Purpose |
| --- | --- | --- |
| Texas City Demo Vessel | `backend/asset_model.json` | Main vessel/mass-balance abnormal situation |
| Pump Station Demo | `backend/asset_model_pump_station.json` | Second model proving compiler reuse |

Reusable templates include:

- vessel
- pump
- valve
- flow pair
- abnormal situation

Templates are validated by guardrails and template tests before publish.

## Simulation Lab

Engineers and Managers can open the Simulation Lab from the bottom status bar.

Simulation Lab supports:

- file-based scenarios
- compound multi-inject scenarios
- single-sensor failure injection
- guided demo tours
- scenario lifecycle controls
- simulator reset

Supported injection types include:

- calibration drift
- stuck/frozen reading
- specific-gravity mismatch
- command-state decoupling

Scenario actions configure the software simulator only. ConfidenceOS does not write plant controls.

## AI-Assisted Features

ConfidenceOS has optional LLM-assisted features:

- mapping explanations
- arbitrary tag-list suggestions
- template suggestions
- root-cause explanations
- handover brief polishing
- grounded operator explanation

These features are advisory only. They do not publish mappings, override validation, modify confidence scores, or authorize operator actions. Engineer approval is required for mapping and template decisions.

If the LLM provider is not configured, or if the configured provider/model fails, the app uses deterministic fallback text.

## Main Demo Flow

1. Open `/studio`.
2. Select an asset model.
3. Run deterministic mapping.
4. Review Mapping Court.
5. Approve valid mappings or ignore dirty tags with an engineering reason.
6. Run the HMI compiler build.
7. Review validation warnings and publish guardrails.
8. Publish the generated Runtime.
9. Open `/runtime`.
10. Trigger an abnormal situation from Simulation Lab or Runtime simulation controls.
11. Show Trust Quarantine and the collapsed abnormal situation.
12. Show pressure mode: single safe move, do-not-trust, trusted substitute, decision freeze, exit condition.
13. Switch roles:
    - Operator: operating basis and immediate safe action.
    - Maintenance: verification task and device-health context.
    - Engineer: receipts, assumptions, score sensitivity, validation warnings.
    - Manager/Auditor: handover debt, timeline, and operational ledger.
14. Open `/handover` and show unresolved handover debt.

## Repository Structure

```text
confidenceOS/
  backend/
    main.py                         FastAPI app and primary API routes
    routers/
      demo.py                       Simulation Lab and scenario APIs
      studio.py                     Studio, model, template, Runtime manifest APIs
    confidence.py                   Confidence scoring engine
    mass_balance.py                 Flow-to-level and residual checks
    advisory.py                     Incident detection, alarm collapse, action contracts
    mode_inference.py               Deterministic mode inference
    decision_integrity.py           Trust graph, confidence debt, handover debt
    hmi_compiler.py                 Compiler pipeline and Mapping Court support
    studio_service.py               Studio state, build, publish, reset
    screen_generator.py             Generated Runtime manifests and receipts
    template_library.py             Template loading and validation
    template_tests.py               Demo template test suite
    verification_service.py         Verification task lifecycle
    shift_channel.py                Shift Channel payloads and notes
    operational_ledger.py           Operational event ledger
    assumptions.py                  Assumption register and confidence explanations
    tag_provider.py                 Read-only tag provider abstraction
    asset_model.json                Texas City demo vessel model
    asset_model_pump_station.json   Pump station demo model

  frontend/
    src/
      App.jsx                       Routes and application shell
      store.js                      Zustand state and WebSocket handling
      components/
        RuntimePlatform.jsx         Generated Runtime UI
        StudioWorkspace.jsx         HMI Compiler Studio UI
        ShiftChannel.jsx            Handover and continuity UI
        AbnormalityLab.jsx          Simulation Lab
        EvidenceStack.jsx           Evidence ledger
        IncidentQueue.jsx           Incident/action-contract rendering
        IncidentTimeline.jsx        Timeline events
        studio/                     Studio subcomponents
      views/                        Secondary support views

  AboutProject/                     Project documentation and screenshots
  markdown/                         Audit and planning notes
  QUICKSTART.md                     Short judge/demo path
  docker-compose.yml                Containerized deployment
```

## API Overview

### Health And Auth

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/login` | Login and receive JWT |
| `GET` | `/api/auth/me` | Current authenticated user |
| `GET` | `/api/health` | Backend readiness and module status |
| `GET` | `/api/reliability` | Runtime reliability telemetry |

### Live Data And Confidence

| Method | Route | Purpose |
| --- | --- | --- |
| `WS` | `/ws/sensors` | Live sensor, confidence, mass-balance stream |
| `GET` | `/api/sensors/latest` | Latest sensor readings |
| `GET` | `/api/confidence` | Current confidence results |
| `GET` | `/api/confidence/explain/{sensor_id}` | Deterministic confidence explanation |
| `GET` | `/api/mass-balance/state` | Current mass-balance state |
| `GET` | `/api/mode` | Current inferred mode |

### Studio And Compiler

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/studio/build` | Current compiler build artifact |
| `POST` | `/api/studio/build/run` | Run compiler build |
| `GET` | `/api/studio/mapping-court` | Mapping Court rows |
| `POST` | `/api/studio/mapping-court/approve` | Approve mapping |
| `POST` | `/api/studio/mapping-court/ignore` | Ignore dirty tag with reason |
| `POST` | `/api/studio/mapping-court/manual-map` | Manually bind raw tag |
| `GET` | `/api/studio/template-tests` | Template test results |
| `POST` | `/api/studio/publish` | Publish latest passing build |
| `POST` | `/api/studio/reset` | Reset Studio demo state |

### Generated Runtime

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/screens/generated` | Generated Runtime manifest |
| `GET` | `/api/runtime/navigation` | Semantic asset navigation |
| `GET` | `/api/runtime/situations` | Current Runtime situations |
| `GET` | `/api/runtime/equipment/{equipment_id}` | Generated equipment faceplate |

### Simulation And Demo

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/api/scenario/load` | Load a scenario file |
| `POST` | `/api/sim/inject` | Inject one simulator failure |
| `POST` | `/api/sim/clear` | Clear simulator failures |
| `POST` | `/api/simulation/start-abnormal-situation` | Start abnormal training path |
| `POST` | `/api/simulation/advance` | Advance scenario phase |
| `GET` | `/api/simulation/state` | Current simulator state |

### Handover And Compliance

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/verification-tasks` | Verification tasks |
| `POST` | `/api/verification-tasks/state` | Transition verification task |
| `GET` | `/api/shift-channel` | Shift Channel payload |
| `POST` | `/api/shift-channel/note` | Add shift note |
| `GET` | `/api/operational-ledger` | Operational event ledger |
| `POST` | `/api/compliance/generate` | Generate compliance evidence payload |
| `GET` | `/api/assumptions` | Assumption register and governance |

## Roles And Demo Credentials

Demo users are seeded at backend startup if the users table is empty.

| Role | Username | Password |
| --- | --- | --- |
| Operator | `operator` | `ConfidenceOS-Op-2025` |
| Maintenance | `maint` | `ConfidenceOS-Maint-2025` |
| Engineer | `engineer` | `ConfidenceOS-Eng-2025` |
| Manager | `manager` | `ConfidenceOS-Mgr-2025` |
| Auditor | `auditor` | `ConfidenceOS-Aud-2025` |

For any shared or deployed environment, set `CONFIDENCEOS_JWT_SECRET` to a persistent secret so existing tokens remain valid across restarts.

## Local Development

### Prerequisites

- Python 3.12
- Node.js 20 or newer
- npm

### Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

Backend health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/api/health
```

### Frontend

```powershell
cd frontend
npm install
npm.cmd run dev -- --host 127.0.0.1
```

The Vite development server defaults to:

```text
http://127.0.0.1:5174
```

The frontend proxies `/api` and `/ws` requests to the backend on port `8001`.

### Environment

Copy `.env.example` to `.env` and fill in values as needed.

Important settings:

```text
CONFIDENCEOS_JWT_SECRET=...
LLM_PROVIDER=openai_compatible
OPENAI_COMPATIBLE_API_KEY=...
OPENAI_COMPATIBLE_BASE_URL=https://aicredits.in/v1
OPENAI_COMPATIBLE_MODEL=...
DATABASE_URL=sqlite:///...
```

LLM configuration is optional. Without it, AI-assisted features use deterministic fallback behavior.

## Docker

The repository includes `docker-compose.yml`.

```powershell
copy .env.example .env
docker compose up --build
```

Default ports:

- backend: `8001`
- frontend: `5174` or the configured `FRONTEND_PORT`

The backend container includes a healthcheck against `/api/health`.

## Testing

Backend tests are located in `backend/test_*.py`. Frontend tests use Vitest.

Typical commands:

```powershell
cd backend
python -m pytest
```

```powershell
cd frontend
npm.cmd run build
npm.cmd run test
```

At minimum before a demo, verify:

1. backend import/startup succeeds
2. `/api/health` responds
3. frontend build succeeds
4. Studio can publish a generated Runtime
5. Runtime loads the latest manifest
6. Simulation Lab can trigger an abnormal situation
7. Operator pressure mode shows the operating basis and action contract
8. Shift Channel shows handover debt and verification tasks

## Documentation

Additional project documentation is available in:

- `QUICKSTART.md`
- `AboutProject/ConfidenceOS_Project_Documentation.md`
- `AboutProject/ConfidenceOS_Project_Documentation_ABB.pdf`
- `markdown/`

## Known Limitations

- The simulator is useful for exercising UI and trust workflows, but it is not a validated process model.
- Confidence scoring is deterministic and explainable, but it is not a certified safety calculation.
- AI output is advisory and may be unavailable depending on provider credentials and model access.
- OPC UA is a placeholder/read-only integration boundary in the default demo.
- SQLite is appropriate for this prototype, not for production historian-scale workloads.
- Some secondary support views are intentionally less central than Studio, Runtime, and Shift Channel.
- This project should not be connected to real plant control loops without a proper industrial safety, cybersecurity, and validation program.

## Project Positioning

ConfidenceOS is strongest when presented as:

```text
A read-only trust-aware HMI compiler and Runtime.
```

It demonstrates how future HMIs could be generated from metadata and templates, then adapt their display around confidence, operating context, and role-specific decisions.

