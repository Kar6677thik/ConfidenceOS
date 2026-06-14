# ConfidenceOS HMI Compiler Pipeline Plan

## Summary

Build ConfidenceOS around a real **HMI Compiler** rather than more isolated ABB features. Studio becomes the engineering-time compiler workspace:

`Raw Tags → Asset Graph → Template Binding → Validation → Screen Generation → Publish Readiness → Runtime`

Runtime consumes the compiled manifest and proves every screen, faceplate, situation workspace, role view, and stress-mode operating basis was generated from metadata, templates, policies, live confidence state, and validation receipts.

This plan preserves existing confidence, advisory, verification, handover, assumptions, WebSocket, and read-only integration APIs. The implementation deepens the current `model_graph`, `template_library`, `studio_service`, and `screen_generator` modules instead of rewriting the app.

## Key Changes

### 1. HMI Compiler Backend

Add a deterministic compiler service that produces one build artifact with stage status, warnings, receipts, generated manifests, and publish guardrails.

Core build output:

```json
{
  "build_id": "hmi-build-0007",
  "status": "PASS_WITH_WARNINGS",
  "can_publish": true,
  "stages": [
    { "id": "import", "status": "PASS" },
    { "id": "mapping", "status": "WARNING" },
    { "id": "template_binding", "status": "PASS" },
    { "id": "validation", "status": "WARNING" },
    { "id": "screen_generation", "status": "PASS" },
    { "id": "publish_readiness", "status": "PASS" }
  ],
  "validation": {
    "info": [],
    "warnings": [],
    "blocking": []
  },
  "generated_manifest": {},
  "publish_diff": {},
  "receipts": []
}
```

Backend additions:

- Add `backend/hmi_compiler.py`.
- Add `backend/imported_tags_demo.json` with dirty imported tags, clean canonical bindings, ambiguous tags, unmapped tags, and one blocking tag.
- Add `backend/template_tests.py` for deterministic template tests.
- Extend `studio_state.json` to track `last_build_id`, `last_build`, `approved_bindings`, `approved_template_assignments`, and `published_build_id`.

Public API additions:

- `GET /api/studio/build`
- `POST /api/studio/build/run`
- `GET /api/studio/template-tests`
- `GET /api/studio/mapping-court`
- `GET /api/studio/mapping-court/{raw_tag}`
- Extend `POST /api/studio/publish` so it publishes only the latest build and fails if `blocking` validation exists.

### 2. Asset Model And Signal Binding

Make the asset graph the source of truth, not the hand-built screen list.

Enhance the model shape to support:

- `assets`: plant, area, unit, module, equipment, device, inferred variable, decision.
- `signals`: raw tag, canonical tag, sensor type, engineering unit, range, source provider, equipment binding, confidence criticality.
- `relationships`: `measured_by`, `feeds`, `drains`, `controlled_by`, `validates`, `backup_measurement`, `mass_balance_group`, `affects_decision`, `trusted_substitute_for`.
- `bindings`: raw imported tag to canonical signal with confidence, evidence, counter-evidence, approval status.

Dirty import behavior:

- `U15_LT_5100.PV` maps to `LT-5100 / V-5100 / level`.
- `15-FI-2010` maps to `FI-2010 / V-5100 / inflow`.
- `FO2020_RATE` maps to `FO-2020 / V-5100 / outflow`.
- `ZT6100.POS` maps to `ZT-6100 / XV-6100 / valve position`.
- `BAD_TAG_123` remains unmapped and non-publishable until marked ignored or assigned.
- `UNUSED_SPARE_AI_09` is ignored with an INFO receipt, not blocking.

Mapping Court response per tag:

```json
{
  "raw_tag": "U15_LT_5100.PV",
  "proposed_canonical_tag": "LT-5100",
  "proposed_asset_id": "V-5100",
  "proposed_role": "primary_level",
  "suggestion_type": "deterministic_rule",
  "approval_required": true,
  "evidence": [],
  "counter_evidence": [],
  "verdict": "APPROVE_WITH_VERIFICATION_GUARDRAIL"
}
```

UI must label this honestly as: `AI suggests when available; deterministic rule active; engineer approval required`.

### 3. Template System And Validation

Turn templates into publish-governed engineering artifacts.

Template metadata should include:

- `template_id`, `version`, `label`, `asset_types`.
- `required_signal_roles`.
- `optional_signal_roles`.
- `generated_sections`.
- `role_visibility`.
- `context_behavior`.
- `operating_basis_rules`.
- `decision_freeze_rules`.
- `handover_debt_rules`.
- `receipt_fields`.
- `template_tests`.

Validation levels:

- `INFO`: does not affect publish.
- `WARNING`: publish allowed, visible in Studio and Runtime receipts.
- `BLOCKING`: publish refused.

Initial blocking rules:

- Vessel template missing primary level.
- Vessel template missing both inflow and outflow.
- Safety-critical sensor has no Maintenance role visibility.
- Critical context suppresses evidence ledger.
- Dirty raw tag is mapped to a critical asset without engineer approval.

Initial warning rules:

- Independent high-level reference missing.
- Manual verification workflow required.
- Flow-pair group missing confidence substitute wording.
- Valve template has position feedback but no command signal.

Template tests:

- Vessel: low level confidence plus FI/FO contradiction generates decision freeze.
- Vessel: missing flow pair emits validation warning.
- Vessel: startup context promotes mass-balance evidence.
- Abnormal situation: collapsed alarms produce one operating question.
- Valve: missing command signal warns but does not block demo publish.

### 4. Generated Manifest Architecture

Replace shallow manifest fields with receipts and compiler provenance.

Every generated screen, faceplate, situation, role section, and stress-mode panel must include:

```json
{
  "generated_id": "faceplate:V-5100:vessel:Operator",
  "build_id": "hmi-build-0007",
  "asset_id": "V-5100",
  "template_id": "vessel",
  "template_version": "1.0",
  "source_tags": ["LT-5100", "FI-2010", "FO-2020"],
  "role_policy": "Operator",
  "context_policy": "MASS_BALANCE_DIVERGENCE",
  "validation_status": "PASS_WITH_WARNINGS",
  "receipt": {
    "generated_because": [],
    "warnings": [],
    "source_files": [
      "asset_model.json",
      "equipment_templates.json",
      "role_policies.json",
      "context_policies.json"
    ]
  }
}
```

Generated manifest sections:

- `navigation`: trust map levels, not just static tree.
- `screens`: plant overview, unit runtime, equipment detail, signal detail, situation workspace.
- `faceplates`: generated from template binding.
- `situations`: abnormal situations with alarm collapse receipt.
- `operating_basis_ledger`: current basis lines with owner, evidence, status, expiry.
- `role_views`: Operator, Maintenance, Engineer, Manager/Auditor.
- `stress_mode`: single safe move layout.
- `receipts`: indexed generation receipts for quick lookup.

Runtime must render receipts as first-class “Screen Receipt” panels, not raw JSON dumps.

### 5. Runtime Behavior

Make Runtime operational, not decorative.

Operator stress mode shows only:

- Abnormal situation.
- Single safe move.
- Do not trust.
- Trusted substitute.
- Decision freeze.
- Exit condition.
- Alarm collapse receipt.
- Decision-time score.

Trust Quarantine:

- Add `trust_state` to confidence-derived Runtime data: `TRUSTED`, `DEGRADED`, `QUARANTINED`, `SUBSTITUTED`, `UNAVAILABLE`.
- Quarantined LT-5100 is forbidden for feed increase and handover acceptance.
- FI/FO implied level becomes trusted substitute when mass-balance conditions allow it.

Alarm collapse receipt:

```json
{
  "raw_signal_count": 5,
  "suppressed_alarm_count": 4,
  "operator_question": "Can the operator trust level before increasing feed?",
  "collapse_reason": "All signals affect the same operating basis.",
  "raw_signals": []
}
```

Decision-time score:

```json
{
  "traditional_steps": 6,
  "confidenceos_steps": 2,
  "decision_compression": "6 -> 2",
  "required_operator_actions": 1
}
```

Role views:

- Operator: single safe move and operating basis.
- Maintenance: verification task, calibration context, confidence debt.
- Engineer: signal binding, template receipt, assumptions, score sensitivity.
- Manager/Auditor: unresolved handover debt, decision freeze, timeline evidence.

### 6. Studio UI

Studio must feel like a compiler workspace.

Primary panels:

- HMI Compiler Pipeline with pass/warn/fail stages.
- Dirty Tag Import Gauntlet with mapped, ambiguous, unmapped, ignored, blocking counts.
- Mapping Court with evidence, counter-evidence, verdict, approval action.
- Template Binding table.
- Template Test Suite.
- Publish Preview Diff.
- Publish Guardrails.
- Generated Runtime Preview.
- Screen Receipts.

Publish flow:

1. Import dirty tags.
2. Run signal binding suggestions.
3. Approve or ignore unresolved mappings.
4. Run HMI build.
5. Inspect validation warnings and blocking issues.
6. Run template tests.
7. Generate publish preview.
8. Publish latest build to Runtime.

The publish button is disabled unless `can_publish=true`.

## Test Plan

Backend tests:

- Dirty tag import returns mapped, ambiguous, unmapped, ignored, and blocking buckets.
- Mapping Court produces evidence, counter-evidence, verdict, and approval-required fields.
- HMI compiler returns all six stages with stable statuses.
- Blocking validation prevents publish.
- Warning validation allows publish and appears in manifest receipts.
- Template tests return deterministic pass/fail rows.
- Generated manifests include `build_id`, `template_id`, `source_tags`, `validation_status`, and receipts on screens, faceplates, situations, and role views.
- Trust Quarantine marks LT-5100 as quarantined when level confidence plus mass-balance contradiction is active.
- Alarm collapse receipt preserves raw signals under one operator question.
- Decision-time score returns deterministic step counts.

Frontend tests/build checks:

- `npm.cmd run build` passes.
- Studio shows compiler pipeline and dirty import counts.
- Approving a mapping changes build status.
- Publish is blocked when blocking validation exists.
- Runtime renders latest published build receipt.
- Role switch materially changes operating content.
- WARNING/CRITICAL context renders single-safe-move stress mode.
- No visible stale copy: Dashboard, Predictive Failure, Fleet Risk, AI decides, Replaces HMI.

Integration checks:

- Existing APIs still pass.
- `GET /api/screens/generated` remains compatible but now returns richer manifests.
- `POST /api/studio/publish` remains available but publishes only compiler output.
- WebSocket live loop remains unchanged except Runtime consumes added trust/build metadata.

## Assumptions And Defaults

- Keep file-backed JSON state; no database migration.
- Keep deterministic compiler logic as authoritative. AI may only generate explanations or suggestions when available; engineer approval is always required.
- Do not add new frontend libraries.
- Do not remove legacy support routes until Runtime and Studio pass build/integration tests.
- Publish guardrails are strict for `BLOCKING`, permissive for `WARNING`.
- ConfidenceOS remains a read-only trust-aware HMI layer beside existing DCS/HMI; it never writes tags, setpoints, alarm acknowledgements, controller modes, or interlock states.
