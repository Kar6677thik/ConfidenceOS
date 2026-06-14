Brutally honest: **ABB judges may like the ambition, but they may not believe the product is real yet.** The latest code has a lot of the right nouns — Studio, Runtime, templates, asset model, role policies, shift channel, generated screens — but several parts still feel like **demo vocabulary wrapped around hardcoded data** rather than a control-system interface ABB engineers would trust.

## The biggest issue: it now risks looking “buzzword-complete but shallow”

You added the ABB-shaped shell, but much of it is still thin. The repo now has `RuntimePlatform`, `StudioWorkspace`, `ShiftChannel`, generated manifests, template libraries, and model graph APIs. That sounds strong. But when I look at the implementation, the “platform” is mostly a deterministic demo around **one vessel, six tags, and three default assignments**.

Your asset model is literally one Texas City demo plant, one unit, one module, one vessel, one valve, one flow pair, and six tags. That is fine for a demo, but dangerous if you pitch it as an HMI-generation platform. The model is named `confidenceos_demo_vessel_v2`, and the hierarchy is a single static plant/unit/module setup. The equipment/signal model is also fixed around `V-5100`, `LT-5100`, `FI-2010`, `FO-2020`, `PT-3100`, `TT-4100`, and `ZT-6100`.

That means ABB judges could say: **“This is not auto-generated HMI engineering. This is a hand-authored demo model with generated-looking UI.”**

## The Studio is the weakest part right now

Studio is supposed to prove engineering-time reduction. Right now, it mostly proves that you can press buttons.

The default template assignments are hardcoded to exactly three assets: `V-5100`, `XV-6100`, and `FG-2010`. The auto-map function returns three hardcoded suggestions for the same three assets, with static confidence values like `0.98`, `0.94`, and `0.96`. There is no real import parser, no noisy tag list, no ambiguous mapping case, no unmapped signals, no conflict resolution, no engineering approval trail beyond a boolean.

The frontend makes this look like “AI Suggests / Engineer Approves,” but the backend explicitly returns `ai_assisted: False`. The UI still labels the section “AI Suggests / Engineer Approves.” That mismatch is dangerous. An ABB judge may ask, “Where is the AI?” and the honest answer is: **there is no real AI-assisted configuration here, only deterministic canned mappings.**

Low-code is also shallow. The UI lets you click “Suggest Signal Binding,” “Generate Publish Preview,” “Publish To Runtime,” and “Reset Demo Default.” But a real low-code HMI engineering tool would let users edit signal metadata, ranges, units, equipment membership, role visibility, template parameters, validation rules, and publish diffs with audit history. Your low-code editing is mostly a template dropdown over existing assignments.

## The “generated screens” are not convincing enough

The backend screen generator does produce a manifest, but it still feels like a fixed layout with metadata sprinkled on top.

The manifest always includes two hardcoded screen definitions: `plant-overview` and `unit-15-runtime`. Faceplates are generated only for assets of type `process_vessel`, `valve`, or `flow_pair`, and the main situations list is just `live_state.get("incidents")` passed through.

So the generated-screen story is currently: **“We read a static JSON model and render a fixed React layout.”** That is not bad, but ABB may expect: “We imported a tag list, inferred hierarchy, bound templates, generated multiple screens, validated missing signals, and published a runtime configuration.”

Your system says that, but it does not deeply do it yet.

## Role-based UI is mostly cosmetic

The role policies look good on paper. Operator, Maintenance, Engineer, Manager, and Auditor each have primary questions and visible sections. But the actual runtime role panel mostly renders section names and says “N item(s) generated from role policy.”

That is not enough. ABB engineers will notice if switching roles does not actually change the workflow. A real maintenance view should feel like a work-order/diagnostics/calibration workspace. A real engineer view should feel like signal binding + validation + assumptions + template provenance. A real operator view should remove engineering noise and show action. Right now, the role model is structurally present but experientially thin.

The harsh version: **role-based UI currently looks like role-based labels, not role-based operations.**

## Context-aware UI is too binary

The context policies have good names: steady state, startup ramp, mass-balance divergence, instrumentation suspect, manual verification required, warning, critical. But the runtime mostly makes one big decision: if `stress_mode` is true, show the stress layout; otherwise show the normal layout.

That makes the feature feel shallow. ABB’s desired “context-aware UI” implies nuanced adaptation: startup verification, maintenance mode, handover mode, abnormal situation mode, degraded instrumentation mode, different promoted controls, different suppressed information, different operator tasks. Your backend has policy names for those, but the frontend does not fully operationalize them.

In other words: **you have context policy metadata, but not enough context behavior.**

## It still smells like a dashboard pretending to be an HMI

Runtime has semantic navigation, situation workspace, faceplates, role panel, validation status. That is better than the old dashboard. But the layout is still mostly panels, cards, sidebars, badges, JSON provenance, and grids. The “Google Maps for the plant” idea is not really implemented; the navigation is a nested tree, not semantic zoom.

The “Teams-like handover” is also quite thin. The shift channel builds pinned items from incidents/debt/tokens/timeline and allows notes. The frontend renders a pinned list and a thread with a note input. That is useful, but it is not yet a real collaborative shift workflow: no acknowledgement, ownership, resolution status, attachments, verification lifecycle, review, audit signature, or shift boundary ritual.

ABB judges may say: **“This borrows the words Maps and Teams, but not the interaction depth.”**

## The industrial credibility gaps are still visible

There are still code-level things that make it feel non-industrial.

CORS is wide open with credentials enabled. The plant tick loop still has one big outer exception handler, so a single unexpected exception can kill the loop and close the DB session. Studio and shift-channel state are file-backed JSON files in the backend directory, which is okay for a hackathon but weak for multi-user/audit/publish workflows.

The OPC UA provider is explicitly a placeholder that returns an empty list. Again, fine if positioned honestly, but not fine if the pitch implies practical industrial integration.

Also, `App.jsx` still has hardcoded `SENSOR_IDS` and `PLANT_IDS`. That undercuts the “metadata-driven” story. Even if the new Runtime uses metadata, old hardcoded constants are still visible in the codebase and some routes.

## The confidence math may still look arbitrary

Your core differentiator is confidence scoring. That is the strongest idea. But judges may still ask: “Why these weights? Why this threshold? Why this tolerance? How do you validate confidence against ground truth?”

The system has assumptions and explanation layers, which helps. But an ABB engineer will not be fully impressed by “confidence score = weighted sum of calibration, stability, cross-sensor, plausibility” unless you show at least one of these:

1. replay validation against known scenarios,
2. sensitivity analysis proving the verdict is robust,
3. calibration of confidence against false-positive/false-negative outcomes,
4. engineering ownership of every threshold,
5. clear separation between advisory confidence and control/safety logic.

You have some of this, but the score can still feel like an invented metric unless the demo aggressively shows **why the conclusion does not depend on a cute formula.**

## The ABB alignment checklist is useful, but it can backfire

The Studio has a static “ABB Desired-Solution Checklist” with every item marked represented. It is a good demo guide, but it can also feel like you are grading your own homework.

Judges may dislike seeing “13 represented” if the implementation behind those items is thin. It can trigger skepticism: “You say AI-assisted config is represented, but the backend says `ai_assisted: False`.” “You say low-code editing, but I can only change a dropdown.” “You say generated HMI screens, but the model has one vessel.”

Use the checklist carefully. It should be a supporting explainer, not the centerpiece.

## The product may feel over-expanded

The original ConfidenceOS idea was sharp: **the HMI knows what it does not know.** After the overhaul, there is a risk that the product becomes:

- Studio
- Runtime
- generated screens
- semantic navigation
- templates
- role policies
- context policies
- shift channel
- confidence debt
- verification tokens
- forensics
- compliance
- sandbox
- graph
- AI query

That is a lot. If the demo is not extremely disciplined, ABB judges may see a feature buffet instead of one undeniable workflow.

The strongest story is not “we implemented every requirement.” The strongest story is:

**Import tags → assign templates → generate trust-aware HMI → abnormal situation appears → operator gets operating basis → maintenance gets verification task → engineer sees provenance → handover preserves unresolved debt.**

Everything else should support that path or be hidden.

## The most generic-feeling parts

The parts that currently feel most generic or shallow are:

1. **Studio auto-map** — hardcoded suggestions, not real discovery.
2. **AI-assisted configuration** — mostly label-level; not actually AI unless added elsewhere.
3. **Role-based UI** — role sections exist, but the actual workflows are not deep.
4. **Modern UX** — still a grid/panel industrial dashboard, not a genuine Maps/Teams-inspired interaction model.
5. **Generated screens** — fixed manifest + static JSON model; not enough proof of real generation.
6. **Template library** — good file, but no deep parameterization or reusable engineering behavior.
7. **Shift channel** — useful, but currently just notes + pinned debt, not a full shift workflow.
8. **Integration story** — read-only posture is good, but OPC UA/CSV providers are placeholders.
9. **Metrics** — no measured engineering-time reduction, alarm-collapse count over time, or decision-time improvement.
10. **Industrial hardening** — CORS, loop failure, file persistence, audit trail, invalid IDs, and test coverage still weaken credibility.

## What would make ABB actually impressed

Do not add more features. Make three workflows brutally convincing.

First, make Studio real enough that it scares the other teams. Show a messy imported tag list with unmapped tags. Click auto-map. Show confidence-ranked suggestions. Show one missing required signal warning. Approve. Generate. Show a diff. Publish. Runtime changes. That would directly hit ABB’s engineering-time requirement.

Second, make Runtime feel like a decision machine, not a dashboard. In abnormal mode, it should show one situation, one operating basis, one decision freeze, one trusted substitute, one exit condition. No clutter. No “look at all my panels.”

Third, make role switching obviously operational. Operator sees actions. Maintenance sees verification/calibration tasks. Engineer sees mapping/assumptions/provenance. Manager sees unresolved debt. Auditor sees timeline and publish history. Not just different section names.

My blunt verdict: **you now have the skeleton of an ABB-aligned platform, but the muscles are still thin.** The judges might be impressed by the ambition and the narrative. They will not be fully impressed if they click around and realize that Studio, generation, AI-assist, role-based UI, and semantic navigation are mostly static demo layers. The core trust idea is still strong. The risk is that the overhaul makes the project look broader but less deep.

Yes. The move now is **not “add more ABB features.”** It is to make judges believe the system is _actually generated, actually role-aware, actually useful under pressure,_ and not just a polished demo around six hardcoded tags.

Right now, your weak spots are obvious: Studio auto-map is hardcoded to three assets, generated screens still include fixed screen IDs, the model is one demo vessel, role-based UI is mostly section labels, and “AI assisted” is mostly a promise.

Here are the ideas that would actually change that.

---

## 1. Build an “HMI Compiler,” not a Studio dashboard

This is the biggest unlock.

Instead of Studio looking like a configuration page, make it feel like a **compiler pipeline**:

```txt
Raw Tags → Asset Graph → Template Binding → Validation → Generated Runtime → Publish
```

Every stage should have pass/warn/fail output.

Example:

```txt
BUILD FAILED
V-5100 uses Vessel template
Required signals:
✓ level: LT-5100
✓ inflow: FI-2010
✓ outflow: FO-2020
⚠ independent high-level reference missing
⚠ manual verification workflow required
```

Why ABB would care: engineers understand build validation. This immediately makes “auto-generated HMI screens” feel real, not cosmetic.

Implementation:

- Rename Studio workflow internally to `hmi_build_pipeline`.
- Add `GET /api/studio/build`.
- Return stages: `import`, `mapping`, `template_binding`, `validation`, `screen_generation`, `publish_readiness`.
- Runtime screens should show `build_id`, `template_id`, `source_tags`, and `validation_status`.

Demo line:

> “ConfidenceOS does not let engineers publish a generated HMI until the equipment template passes its operating-basis checks.”

That is much stronger than “we have low-code.”

---

## 2. Add a dirty tag import gauntlet

Your current tag import is too clean. ABB engineers know real tag lists are ugly.

Create a fake imported tag file with messy names:

```txt
U15_LT_5100.PV
15-FI-2010
FO2020_RATE
ZT6100.POS
PT_3100_PROCESS
TEMP4100
BAD_TAG_123
UNUSED_SPARE_AI_09
```

Then show Studio resolving them into clean model bindings:

```txt
U15_LT_5100.PV → LT-5100 → V-5100 level → vessel template
FO2020_RATE → FO-2020 → V-5100 outflow → mass-balance group
BAD_TAG_123 → unmapped / requires engineer review
```

This would solve the “hardcoded model” problem fast. Right now your model is already clean and mapped, so generation looks fake. Realistic mess makes the auto-mapping feel valuable.

Implementation:

- Add `backend/imported_tags_demo.json`.
- Add unmapped tags.
- Change `studio_imported_signals()` so it returns raw imported tags plus proposed bindings.
- Show mapped, uncertain, and unmapped buckets in Studio.

High-impact UI labels:

```txt
AUTO-MAPPED: 6
AMBIGUOUS: 2
UNMAPPED: 3
BLOCKING: 1
```

ABB judges will instantly understand this.

---

## 3. Replace “AI suggests” with “Explainable Mapping Court”

Do not just say AI suggests. Make mapping suggestions defend themselves.

For each proposed mapping, show:

```txt
Proposed binding:
U15_LT_5100.PV → LT-5100 / Vessel Level

Evidence:
- Tag contains LT, common abbreviation for level transmitter
- Numeric suffix 5100 matches vessel V-5100
- Engineering units are ft
- Range 0–200 ft matches vessel-level template
- Related FI/FO tags exist in same unit

Counter-evidence:
- No redundant high-level switch found

Verdict:
Approve as primary level, but require manual verification workflow.
```

This makes AI-assisted configuration credible even if the first version is deterministic.

Current problem: backend returns `ai_assisted: False`, while the UI says “AI Suggests / Engineer Approves.” Fix it by making it honest:

```txt
Deterministic suggestion
AI explanation available
Engineer approval required
```

Later, if Claude exists, it can write the explanation. The logic remains deterministic.

---

## 4. Add “generation receipts” to every Runtime screen

Every generated UI element should have a small receipt:

```txt
Generated because:
- Asset: V-5100
- Template: vessel@1.0
- Signals: LT-5100, FI-2010, FO-2020
- Role policy: Operator
- Context policy: MASS_BALANCE_DIVERGENCE
- Validation: passed with 1 warning
- Build ID: hmi-build-0042
```

This solves the “fixed React layout pretending to be generated” problem.

The judge should be able to click any faceplate, situation card, or role view and see **why it exists**.

This is much better than just showing JSON provenance in a side panel. Make it a first-class industrial concept:

```txt
SCREEN RECEIPT
Generated from metadata. Not hand-built.
```

Demo line:

> “Every screen has a receipt. If the asset model changes, the generated screen changes, and the receipt proves why.”

---

## 5. Create a “template mutation demo”

ABB’s requirement includes reusable libraries and standardization. Right now your template library exists, but judges may not feel its power.

Add one killer demo:

1. In Studio, open the `Vessel / Tank Faceplate` template.
2. Toggle: “Require independent verification when level confidence < 50.”
3. Preview affected screens.
4. It shows:

```txt
Affected generated screens:
- V-5100 vessel faceplate
- Unit 15 Runtime
- Operator stress mode
- Maintenance verification view
- Handover debt policy
```

This proves reusable templates actually propagate behavior.

Do not build a full template editor. Build one or two safe toggles:

- require manual verification below LOW confidence
- show/hide confidence courtroom for Operator
- promote mass balance during startup
- require handover debt for unresolved decision freeze

That would impress ABB more than adding ten more static templates.

---

## 6. Make role switching operational, not visual

Right now role policies are good metadata, but the Runtime role panel mostly says section names and item counts. That is shallow.

Make the same abnormal situation transform into four genuinely different workspaces:

### Operator

```txt
Do not trust LT-5100.
Use FI-2010 + FO-2020 implied level.
First safe action: verify level before increasing feed.
Frozen decision: increase_feed.
Exit condition: manual verification token or LT confidence > 80%.
```

### Maintenance

```txt
Field task generated:
- Inspect LT-5100 impulse line
- Verify local level indication
- Calibration status: 47 days since calibration
- Token required: manual_level_check
```

### Engineer

```txt
Configuration impact:
- Vessel template generated decision freeze
- Mass-balance tolerance assumption used
- Confidence score dominated by cross-sensor contradiction
- Sensitivity: verdict unchanged if calibration weight is ignored
```

### Manager/Auditor

```txt
Shift risk:
- 1 unresolved operating-basis item
- 1 active decision freeze
- Handover acceptance blocked
- Timeline evidence preserved
```

Same incident. Four different jobs. That will feel role-based.

---

## 7. Add “Operator Single Safe Move”

Under stress, operators do not need a dashboard. They need the next safe move.

Make stress mode brutally minimal:

```txt
ABNORMAL SITUATION:
Inventory accumulation with unreliable level indication

SINGLE SAFE MOVE:
Verify level locally before increasing feed.

DO NOT:
Increase feed
Accept handover as normal
Use LT-5100 as primary level basis

USE:
FI-2010 + FO-2020 mass-balance implied level

EXIT WHEN:
Manual verification active OR LT-5100 confidence > 80%
```

Then add a timer:

```txt
Time since first contradiction: 04:32
Time decision freeze active: 03:58
```

This gives judges measurable faster decision-making.

Do not show six cards. Do not show charts. Do not show AI query. In stress mode, the product should look almost empty.

---

## 8. Add “Trust Quarantine”

This is more powerful than confidence scores.

When a sensor becomes suspect, it enters quarantine:

```txt
LT-5100
State: QUARANTINED
Reason: contradicted by mass balance
Allowed use: trend only
Forbidden use: feed increase decision, handover acceptance
Substitute: implied_level from FI/FO
Exit: field verification or confidence recovery
```

This turns confidence from a number into an operating rule.

ABB engineers would like this because it sounds like control-room governance. It does not control the plant; it governs what the operator is allowed to trust.

Implementation:

- Add `trust_state` to confidence results:
  - `TRUSTED`
  - `DEGRADED`
  - `QUARANTINED`
  - `SUBSTITUTED`
  - `UNAVAILABLE`

- Render this more prominently than raw confidence percentage.
- Action contracts should use trust state.

Demo line:

> “We are not alarming on LT-5100. We are quarantining it from safety-relevant decisions.”

That is excellent.

---

## 9. Add “Operating Basis Ledger”

Industrial operators do not act on raw signals. They act on an operating basis.

Create a ledger:

```txt
Current operating basis:
- Vessel inventory is increasing.
- Primary level indication is not trusted.
- Flow-derived level is the temporary basis.
- Feed increase is frozen.
- Field verification required before handover.
```

Each line has evidence and owner.

```txt
Basis line: Primary level indication is not trusted
Evidence: LT-5100 confidence 18%, FI/FO residual 12.4 ft
Owner: Operator
Status: active
Expires: when verification clears
```

This is better than “Evidence Stack” because it sounds operational.

The Runtime should be built around the operating basis, not around sensors.

---

## 10. Add “screen generation diff”

When Studio publishes, show exactly what changed:

```txt
Publish Preview Diff

Added:
+ Vessel faceplate for V-5100
+ Mass-balance section because FI/FO validate LT
+ Decision freeze rule for increase_feed
+ Maintenance verification task for LT-5100

Changed:
~ Operator stress layout now suppresses forecast chart
~ Manager view now includes handover debt ledger

Blocked:
! Cannot publish valve template for XV-6100: missing command signal
```

This solves three ABB requirements at once:

- model-based engineering,
- reusable templates,
- lower engineering effort.

Right now your diff only compares assignment changes against demo defaults. Make it a generated-HMI diff, not just a JSON assignment diff.

---

## 11. Add “template unit tests”

This is unconventional and very ABB-engineer-friendly.

Each template should have a tiny test:

```txt
Vessel template tests:
✓ If level confidence is LOW and FI/FO contradiction exists, generate decision freeze.
✓ If flow pair missing, show validation warning.
✓ If startup context active, promote mass balance.
✓ If verification token active, show temporary operating basis.
```

In Studio, show:

```txt
Template Test Suite
vessel: 4/4 passed
valve: 2/3 passed
flow_pair: 3/3 passed
```

This makes your template library feel engineered, not decorative.

Implementation:

- Add `backend/template_tests.py`.
- Add `/api/studio/template-tests`.
- Build tests from simple fixture states.
- Display pass/fail in Studio.

Demo line:

> “Before a generated HMI can be published, the equipment template has to pass decision-integrity tests.”

That is a serious systems-engineering line.

---

## 12. Add “unknown plant challenge”

If you only demo Texas City, judges may think everything is scripted.

Create a second tiny asset model, maybe:

```txt
Municipal Water Pump Station
- Tank T-100
- Pump P-101
- Inflow FIT-101
- Outflow FIT-102
- Level LIT-100
```

Then in Studio, allow switching imported model:

```txt
Demo Vessel
Pump Station
Gas Compressor
```

The system should generate different Runtime faceplates from the same templates.

Even if simple, this proves generality.

Do not build a huge second simulator. Just create enough metadata to show the generator is not locked to `V-5100`.

This directly attacks the “one hardcoded vessel” weakness.

---

## 13. Replace “semantic navigation tree” with a trust map

Your current semantic navigation is basically a tree. That is not “Google Maps.”

Make a simple map-like plant view:

```txt
[Plant]
  ↓
[Area]
  ↓
[Unit 15 ISOM]  WARNING
  ↓
[V-5100]  TRUST QUARANTINE
  ├─ LT-5100 quarantined
  ├─ FI-2010 trusted
  └─ FO-2020 trusted
```

Use zoom levels:

- Level 1: plants
- Level 2: units
- Level 3: equipment
- Level 4: signals/evidence

Clicking does not just navigate; it changes the level of detail.

High-impact twist: show only trust hotspots, not every tag.

```txt
3 hidden healthy assets
1 trust hotspot
1 frozen decision
```

This is much closer to Google Maps: you see where attention is needed, then zoom in.

---

## 14. Add “alarm collapse receipt”

Do not just say “collapsed from X signals.” Show the compression logic.

```txt
Collapsed Situation:
Inventory accumulation with unreliable level indication

Raw signals collapsed:
1. LT-5100 LOW confidence
2. FI/FO mass-balance residual
3. Startup ramp inferred
4. LT stale tendency
5. Feed increase decision depends on LT

Why one situation:
All five signals affect the same operating basis:
“Can the operator trust level before increasing feed?”
```

This solves reduced alarm fatigue better than just hiding alarms.

ABB judges care about alarm management. Show that the collapse is lossless and explainable.

Add:

- `raw_signal_count`
- `suppressed_alarm_count`
- `collapse_reason`
- `operator_question`
- `expand_all_raw_signals`

The killer phrase:

> “We do not suppress alarms. We preserve them under one operator question.”

---

## 15. Add “decision-time score,” not generic KPIs

Do not claim “faster decisions” vaguely. Measure it in the demo.

For each abnormal situation, compute:

```txt
Traditional HMI path:
- inspect LT
- inspect FI
- inspect FO
- inspect trends
- infer contradiction
- decide verification
Estimated steps: 6

ConfidenceOS path:
- read operating basis
- verify field level
Estimated steps: 2

Decision compression: 6 → 2 steps
```

This is not fake “hours saved.” It is a transparent interaction metric.

Also show:

```txt
raw warnings: 5
situations: 1
blocked decisions: 2
trusted substitutes: 2
required operator action: 1
```

ABB will understand that.

---

## 16. Add “publish guardrails”

Studio should refuse to publish unsafe generated HMIs.

Examples:

```txt
Cannot publish:
- Vessel template has no validated level substitute
- Safety-critical sensor has no role policy for Maintenance
- Context policy suppresses evidence in CRITICAL mode
```

This would make your low-code story credible. Low-code without guardrails is scary in industrial systems. Low-code with publish validation is valuable.

Implementation:

- Add validation levels:
  - `INFO`
  - `WARNING`
  - `BLOCKING`

- Publish fails on blocking.
- Show “Override requires Engineer role” if you want drama.

---

## 17. Add “policy replay before publish”

This is very strong.

When an engineer changes a context policy, Studio should replay the Texas City scenario and show what would have happened.

Example:

```txt
Policy change:
Suppress mass-balance chart in startup mode.

Replay result:
BLOCKED. During Texas City replay, mass-balance evidence was required to detect unreliable level indication.

Recommendation:
Do not suppress mass-balance during STARTUP_RAMP.
```

This is an advanced idea that feels like real engineering.

It proves:

- model-based engineering,
- safety validation,
- context-aware UI,
- forensics,
- lower risk configuration.

You already have forensics/replay. Connect it to Studio publish.

---

## 18. Add “field verification task lifecycle”

Verification tokens are good, but make them operational.

Current token:

```txt
created, valid_until, note
```

Better lifecycle:

```txt
REQUESTED → ASSIGNED → FIELD_CHECK_DONE → ACCEPTED → EXPIRED
```

Fields:

- requested_by
- assigned_to_role
- verification_method
- evidence_required
- expiry
- accepted_by
- handover_required

The operator should not create a token casually. The system should create a **verification task**, and the token is the result.

This makes Maintenance view much more real.

---

## 19. Add “control-room mode: no chat”

Hide the query panel during stress mode. Seriously.

ABB operators under pressure do not want to chat. They want the system to present the operating basis.

Keep “Grounded Operator Explanation” only as:

- normal mode explanation,
- engineer/auditor explanation,
- post-incident query.

In stress mode, the UI should say:

```txt
Chat disabled during active decision freeze.
Use operating-basis workflow.
```

That is an unconventional but strong safety design choice. It signals maturity.

---

## 20. Add “read-only integration contract”

Do not just say read-only. Generate a contract.

```txt
ConfidenceOS Integration Contract

Inputs:
- OPC UA subscription: read only
- Historian read: read only
- Asset model import: read only

Outputs:
- confidence metadata
- operating-basis advisory
- handover debt
- verification requests

Forbidden:
- write tag value
- acknowledge DCS alarm
- change setpoint
- change controller mode
- bypass interlock
```

This turns a placeholder integration into a credible architecture artifact.

ABB engineers may not expect actual OPC UA integration from a hackathon, but they will appreciate a safe integration boundary.

---

## Highest-impact build order

Do not implement all 20 equally. Build this sequence:

### First: make Studio undeniable

1. HMI Compiler pipeline
2. Dirty tag import gauntlet
3. Mapping Court
4. Screen generation receipts
5. Publish diff + guardrails

This fixes the biggest ABB-alignment weakness: engineering-time reduction.

### Second: make Runtime undeniable

6. Trust Quarantine
7. Operating Basis Ledger
8. Operator Single Safe Move
9. Alarm collapse receipt
10. Decision-time score

This fixes the operator-under-pressure weakness.

### Third: make roles real

11. Maintenance verification task lifecycle
12. Engineer policy replay before publish
13. Manager/Auditor handover acceptance ritual

This fixes the role-based UI weakness.

### Fourth: prove generality

14. Unknown plant challenge
15. Template mutation demo
16. Template unit tests

This fixes the “hardcoded demo” weakness.

---

## The one killer demo path

This is the demo I would build toward:

1. Open Studio.
2. Import dirty tag list.
3. Studio shows mapped / ambiguous / unmapped tags.
4. Open Mapping Court for `U15_LT_5100.PV`.
5. Approve vessel template.
6. Run HMI build.
7. Build fails once because independent verification is missing.
8. Engineer accepts template guardrail: “manual verification required if LT quarantined.”
9. Build passes.
10. Publish.
11. Runtime opens a trust map.
12. Startup begins.
13. LT-5100 looks normal but enters Trust Quarantine.
14. Five raw warnings collapse into one operating question.
15. Stress mode shows only Single Safe Move.
16. Maintenance receives verification task.
17. Manager sees handover blocked until verification.
18. Engineer opens generation receipt proving the UI came from metadata/templates.

Close with:

> “This is not a dashboard. It is a compiler for trust-aware HMIs. It reduces engineering time because screens are generated from metadata, and it improves decisions because abnormal situations collapse into an operating basis.”

That is the version that could genuinely impress ABB.
