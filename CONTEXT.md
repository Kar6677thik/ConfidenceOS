# ConfidenceOS System Context

This document is the current source of truth for the codebase. It describes what is implemented in code now, not the intended PRD unless the implementation exists.

## 1. System Overview

ConfidenceOS is a full-stack industrial HMI simulator. It runs synthetic plant sensor simulations in the backend, computes confidence and safety-related diagnostics, persists time-series and event data, and exposes a React dashboard for operators, engineers, managers, and auditors.

In real terms, the system simulates industrial plants with sensors such as level, flow, pressure, temperature, and valve position. It continuously generates readings, scores how trustworthy each sensor appears to be, detects mass-balance discrepancies, flags stale startup readings, and lets the UI present the resulting operational state.

Core purpose:

- Show operators which sensors can be trusted during live operation.
- Surface degraded confidence before values become obviously wrong.
- Demonstrate industrial workflows such as fleet overview, startup checks, handover generation, forensics replay, compliance reporting, causal graph exploration, prediction, and sandbox simulation.

Key concepts:

- **Plant**: A simulated industrial asset. The code defines three plants: `plant-a`, `plant-b`, and `plant-c`.
- **Sensor**: A simulated instrument such as `LT-5100`, `FI-2010`, `FO-2020`, `PT-3100`, `TT-4100`, or `ZT-6100`.
- **Reading**: A generated sensor value with unit, timestamp, type, and optional failure mode.
- **Confidence**: A 0-100 score and tier describing the trustworthiness of a sensor.
- **Sub-scores**: Calibration, stability, cross-sensor consistency, and physical plausibility.
- **Mass balance**: A simple flow-in/flow-out integration compared with measured tank level.
- **Startup mode**: A stricter operating mode with tighter mass-balance tolerance and stale-reading checks.
- **Anomaly**: A persisted event when confidence, mass balance, or stale-reading logic detects a problem.
- **Scenario**: A JSON file that injects failure modes into the simulator over time.
- **Fleet**: Summary across all configured plants.

## 2. Architecture

High-level architecture:

```text
React/Vite frontend
  -> REST calls for fleet, predictions, query, health, reports, etc.
  -> WebSocket stream for live dashboard state

FastAPI backend
  -> PlantManager owns per-plant simulator and analysis engines
  -> Background tick loops generate and process plant data
  -> SQLAlchemy persists readings, confidence logs, anomalies, handovers, envelopes

SQLite database
  -> Default local path: sqlite:///./confidenceos.db
  -> Docker path: sqlite:////app/data/confidenceos.db
```

Runtime model:

- FastAPI starts a background tick loop for every configured plant during application lifespan startup.
- Each plant loop runs roughly once per second.
- Every tick:
  - The simulator generates sensor readings.
  - The confidence engine scores each sensor.
  - The mass-balance engine updates implied vs measured level.
  - The startup manager checks stale readings if startup mode is active.
  - Readings are persisted.
  - Confidence is persisted every 5 ticks.
  - Anomalies are persisted with cooldowns.
- The frontend operator dashboard opens `/ws/sensors?plant_id=...` and receives cached latest state once per second.
- Other pages use REST endpoints.

Important architectural caveat:

- `PlantManager.get(plant_id)` silently falls back to `plant-a` when the requested plant ID is unknown. This can hide invalid routing or wrong-plant usage.

## 3. Backend Deep Dive

Backend entry point:

- `backend/main.py`
- Framework: FastAPI
- Database: SQLAlchemy ORM over SQLite
- Background processing: FastAPI lifespan task group using `asyncio.create_task`

### API Endpoints

| Method | Route | Purpose | Input | Output |
|---|---|---|---|---|
| WebSocket | `/ws/sensors` | Streams live plant state once per second. | Query: `plant_id` default `plant-a`. | Messages shaped as `{type, plant_id, timestamp, readings, confidence, mass_balance, mode, stale_flags, new_anomalies}`. `new_anomalies` is currently always an empty list. |
| GET | `/api/sensors/history/{sensor_id}` | Returns persisted reading history for one sensor. | Path: `sensor_id`. Query: `plant_id`, `hours`, `limit`. | `{sensor_id, plant_id, count, readings}` where readings include `value`, `unit`, `timestamp`, `failure_mode`. |
| GET | `/api/sensors/latest` | Returns latest in-memory readings for a plant. | Query: `plant_id`. | `{readings}` or `{readings: [], message}`. |
| GET | `/api/confidence/{sensor_id}` | Returns latest in-memory confidence for one sensor. | Path: `sensor_id`. Query: `plant_id`. | Confidence object or 404. |
| GET | `/api/confidence` | Returns latest in-memory confidence for all sensors in a plant. | Query: `plant_id`. | `{confidence}` or `{confidence: [], message}`. |
| GET | `/api/mass-balance/flags` | Returns current active mass-balance flags. | Query: `plant_id`. | `{flags, count}`. |
| GET | `/api/mass-balance/state` | Returns compact mass-balance state. | Query: `plant_id`. | `{state}` or `{state: null, message}`. |
| GET | `/api/sensors/{sensor_id}/health` | Returns calibration and anomaly history for a sensor. | Path: `sensor_id`. Query: `plant_id`. | `{sensor_id, plant_id, calibration, anomalies, drift_trend, maintenance}`. Calibration status is `current`, `due_soon`, or `expired`. |
| GET | `/api/anomalies` | Returns recent anomalies for a plant. | Query: `plant_id`, `hours`, `limit`. | `{anomalies, count}`. |
| GET | `/api/anomalies/{sensor_id}` | Returns recent anomalies for one sensor. | Path: `sensor_id`. Query: `plant_id`, `hours`, `limit`. | `{sensor_id, anomalies, count}`. |
| GET | `/api/mode` | Returns startup/normal mode state. | Query: `plant_id`. | Startup manager state with active flag, thresholds, stale flags, and acknowledgements. |
| POST | `/api/mode/startup` | Enables or disables startup mode. | Body: `{active: bool}`. Query: `plant_id`. | `{status, mode}`. |
| POST | `/api/mode/startup/acknowledge/{sensor_id}` | Acknowledges a stale sensor flag. | Path: `sensor_id`. Query: `plant_id`. | `{status: "acknowledged", sensor_id}` or 404. |
| POST | `/api/handover/generate` | Generates a shift handover brief. | Query: `plant_id`. Uses latest in-memory state. | Handover dict with `brief`, `source`, `model`, `generated_at`, and `system_state_summary`. Returns 400 if confidence is not populated yet. |
| GET | `/api/handover/latest` | Returns latest in-memory handover for a plant. | Query: `plant_id`. | Latest brief or `{brief: null, message}`. |
| POST | `/api/scenario/load` | Loads a simulator scenario and resets simulator/mass balance. | Query: `plant_id`, optional `scenario_path`. | `{status, plant_id, scenario}`. |
| POST | `/api/scenario/reset` | Clears simulator scenario and resets simulator/mass balance. | Query: `plant_id`. | `{status, plant_id}`. |
| GET | `/api/fleet` | Returns risk-ranked fleet summary. | None. | `{fleet, plant_count, timestamp}`. |
| GET | `/api/fleet/history` | Returns 15-minute-bucketed average confidence history per plant. | Query: `hours`. | `{hours, trend}` where each trend row has timestamp and plant IDs as keys. |
| GET | `/api/predictions/{plant_id}` | Returns confidence forecasts for all sensors with enough history. | Path: `plant_id`. | `{plant_id, predictions, timestamp}`. |
| GET | `/api/predictions/{plant_id}/{sensor_id}` | Returns confidence forecast for one sensor. | Path: `plant_id`, `sensor_id`. | Prediction object. |
| POST | `/api/query` | Answers a natural-language plant question. | Body: `{question, plant_id}`. | `{answer, sources, source, model, timestamp}` plus fallback-specific fields. |
| GET | `/api/graph/{plant_id}` | Returns causal graph state for a plant. | Path: `plant_id`. | `{plant_id, nodes, edges, root_cause, propagation_chain, narrative}`. |
| GET | `/api/adaptive-thresholds/{plant_id}` | Computes, persists, and applies learned envelopes from recent history. | Path: `plant_id`. Query: `hours`. | `{plant_id, hours, envelopes, count, generated_at}`. |
| GET | `/api/forensics/presets` | Lists replay presets. | None. | `{presets}`. |
| GET | `/api/forensics/presets/{preset_id}` | Returns a prebuilt replay preset. | Path: `preset_id`. | Only `texas-city` is implemented; other IDs return 404. |
| GET | `/api/forensics/{plant_id}` | Builds replay timeline from persisted readings and confidence logs. | Path: `plant_id`. Query: `hours`. | `{plant_id, hours, data_points, timeline, anomalies, annotations, confidence_trajectory, replay}`. |
| POST | `/api/compliance/generate` | Generates a structured compliance report and a simple PDF payload. | Body: `{plant_id, hours, report_type}`. | Report fields plus `report`, `pdf_base64`, and `pdf_filename`. |
| POST | `/api/sandbox/run` | Runs an isolated failure-mode simulation. | Body: `{plant_id, sensor_id, failure_mode, severity, duration_hours}`. | `{sensor_id, failure_mode, severity, duration_hours, sample_count, results}`. |
| GET | `/api/health` | Returns backend health and runtime status. | None. | `{status, version, uptime_seconds, tick_count, active_connections, plants, plant_loops, db_status, modules}`. |

### Backend Modules And Responsibilities

#### `backend/main.py`

- Owns FastAPI app creation, CORS, lifespan startup/shutdown, background tick loops, and all API routes.
- Starts one async plant loop per configured plant.
- Maintains WebSocket connection count and loop status.
- Uses in-memory plant state for live endpoints and persisted SQLite data for history endpoints.

#### `backend/plants.py`

- Defines plant configurations and the `PlantManager`.
- Constructs one `PlantInstance` per plant.
- Each plant instance owns:
  - `SensorSimulator`
  - `ConfidenceEngine`
  - `MassBalanceEngine`
  - `StartupManager`
  - `HandoverBriefGenerator`
  - latest readings/confidence/mass-balance caches
- Computes fleet risk from confidence, flags, mass-balance discrepancy, and calibration age.

Implemented plants:

| Plant ID | Name | Type | Location | Scenario |
|---|---|---|---|---|
| `plant-a` | Raffinate Splitter Unit | Refinery | Texas City | `scenario.json` |
| `plant-b` | North Sea Gas Compression | Gas Processing | Aberdeen | `scenario_b.json` |
| `plant-c` | Municipal Water Treatment | Melbourne | `scenario_c.json` |

#### `backend/simulator.py`

- Generates synthetic sensor readings.
- Default sensors:
  - `LT-5100`: level, ft
  - `FI-2010`: inflow, gpm
  - `FO-2020`: outflow, gpm
  - `PT-3100`: pressure, psi
  - `TT-4100`: temperature, deg F
  - `ZT-6100`: valve position, %
- Adds sinusoidal variation and Gaussian noise.
- Applies scenario-driven failures:
  - `calibration_drift`
  - `stuck_reading`
  - `sg_mismatch`
  - `command_state_decoupling`
- Scenario metadata mentions `cross_sensor_divergence`, but that failure type is not clearly implemented in `_apply_failure`.

#### `backend/confidence.py`

- Computes sensor confidence score and tier.
- Maintains per-sensor reading history in memory.
- Uses static calibration metadata and optional adaptive envelopes.
- Produces sub-scores and human-readable reasons.

#### `backend/mass_balance.py`

- Tracks flow-in, flow-out, and measured level in a rolling window.
- Estimates implied level from integrated net flow.
- Raises INFO/WARNING/CRITICAL flags based on discrepancy from measured level.

#### `backend/startup.py`

- Tracks startup mode.
- Tightens tier thresholds and mass-balance tolerance when startup mode is active.
- Detects stale readings when values remain unchanged longer than 480 seconds.
- Supports acknowledging stale flags per sensor.

#### `backend/handover.py`

- Generates shift handover briefs.
- Uses Anthropic Claude when `ANTHROPIC_API_KEY` is configured.
- Falls back to deterministic text generation when Claude is unavailable.
- Stores latest brief in memory and logs generated brief text to the database from `main.py`.

#### `backend/prediction.py`

- Builds confidence forecasts from persisted confidence history.
- Uses lightweight regression and heuristic model labeling.
- Requires at least 10 confidence samples.
- Returns time-to-LOW and time-to-CRITICAL estimates only when trend slope is meaningfully negative.

#### `backend/nlquery.py`

- Answers natural-language questions over current plant state.
- Uses Claude when configured.
- Falls back to deterministic rules for common question types.
- Sources are generated from sensor IDs found in the answer/context.

#### `backend/causal_graph.py`

- Defines static plant topologies.
- Marks nodes degraded or anomalous based on confidence tiers.
- Infers a simple root cause from anomalous nodes and upstream relationships.
- This is a heuristic graph, not learned causal inference.

#### `backend/adaptive_thresholds.py`

- Computes learned sensor envelopes from recent persisted readings.
- Excludes sensors with recent anomalies.
- Persists generated envelopes and applies them to the plant confidence engine when the endpoint is called.

#### Compliance and forensics logic in `backend/main.py`

- Forensics has two modes:
  - Synthetic `texas-city` replay preset.
  - Database-derived replay from recent readings/confidence logs.
- Compliance report generation returns structured JSON plus a minimal custom PDF encoded as base64.
- PDF generation is hand-built, not ReportLab or browser-rendered HTML.

### Database Structure

Database setup is in `backend/database.py`.

#### `sensor_readings`

Stores generated sensor readings.

Fields:

- `id`
- `plant_id`
- `sensor_id`
- `sensor_type`
- `value`
- `unit`
- `timestamp`
- `failure_mode`

#### `anomaly_logs`

Stores anomaly events.

Fields:

- `id`
- `plant_id`
- `sensor_id`
- `anomaly_type`
- `description`
- `severity`
- `timestamp`

#### `confidence_logs`

Stores periodic confidence snapshots.

Fields:

- `id`
- `plant_id`
- `sensor_id`
- `confidence_pct`
- `tier`
- `calibration_score`
- `stability_score`
- `cross_sensor_score`
- `plausibility_score`
- `timestamp`

Index:

- `idx_confidence_plant_sensor_time` on `plant_id`, `sensor_id`, `timestamp`

#### `flag_events`

Defined but not clearly used by the current runtime.

Fields:

- `id`
- `plant_id`
- `sensor_id`
- `flag_type`
- `severity`
- `message`
- `duration_seconds`
- `resolved`
- `acknowledged`
- `timestamp`

#### `shift_handover_logs`

Stores generated handover text.

Fields:

- `id`
- `plant_id`
- `brief_text`
- `source`
- `generated_at`

#### `adaptive_envelope_logs`

Stores learned physical plausibility envelopes.

Fields:

- `id`
- `plant_id`
- `sensor_id`
- `sensor_type`
- `learned_min`
- `learned_max`
- `mean_value`
- `std_dev`
- `sample_count`
- `generated_at`

### Background Processing

Each plant loop in `backend/main.py`:

1. Reads the plant's startup state.
2. Applies startup thresholds to confidence scoring.
3. Applies startup mass-balance tolerance multiplier.
4. Calls the simulator tick.
5. Computes confidence for all readings.
6. Updates mass-balance state.
7. Checks stale startup readings.
8. Logs anomalies with cooldown.
9. Persists sensor readings every tick.
10. Persists confidence snapshots every 5 ticks.
11. Updates loop health status.

If an unhandled exception escapes the loop body, the loop marks itself as error and exits. There is no restart mechanism in the current code.

## 4. Frontend Structure

Frontend stack:

- React 19
- Vite
- React Router
- Zustand
- Recharts
- Tailwind CSS v4 style utilities through CSS imports

Entry points:

- `frontend/src/main.jsx`: wraps `App` in `BrowserRouter`.
- `frontend/src/App.jsx`: defines the application shell and routes.
- `frontend/src/store.js`: global Zustand store and API/WebSocket actions.
- `frontend/src/index.css`: industrial visual system and global styles.

### Routes And Pages

Current routes:

| Route | Page | Purpose |
|---|---|---|
| `/` / `/integrity` | `FleetOverview` | Fleet risk overview and plant cards. |
| `/operator` | `OperatorDashboard` | Live HMI dashboard for selected plant with NAMUR statuses. |
| `/predictions` | `PredictiveTimeline` | Forecast view, action queue, and Confidence Debt priorities. |
| `/forensics` | `ForensicsReplay` | Replay preset or recent plant replay. |
| `/graph` | `CausalGraph` | Causal graph visualization and trust dependencies graph. |
| `/compliance` | `CompliancePortal` | Generate/download compliance reports. |
| `/sandbox` | `SandboxSimulator` | Run simulated failure modes. |
| `/engineer` | `EngineerDeepDive` | Engineer deep-dive envelope visualizer. |

### Global State

State lives in `frontend/src/store.js`.

Main state fields:

- Connection: `connected`, `_ws`, `_reconnectTimer`
- Selection: `plantId`, `role`, `selectedSensorId`
- Fleet: `fleetData`, `fleetLoading`
- Predictions: `predictions`, `predictionsLoading`
- Query: `queryHistory`, `queryLoading`
- Live dashboard data: `readings`, `confidence`, `massBalance`, `mode`, `staleFlags`, `newAnomalies`, `timestamp`
- Derived UI data: `averageConfidence`, `chartHistory`

Important frontend data behavior:

- WebSocket URL is built from `window.location.host`.
- REST calls use relative `/api/...` paths.
- `VITE_API_URL` and `VITE_WS_URL` exist in environment examples but are not used in the frontend code.
- `connect()` is called by the operator dashboard, not globally by the app shell.
- `setPlantId()` disconnects the current socket, clears live state, and reconnects shortly after.

### Key Components

#### `NavBar.jsx`

- Top navigation shell.
- Shows role selector, route links, live indicator, selected plant, health, and active alert count.
- Role selector changes visible navigation links only; it is not backend authorization.

#### `SensorCard.jsx`

- Displays one sensor reading and its confidence result.
- Shows sensor ID, value, unit, tier, sub-scores, reason text, and a small visual strip.
- Selection updates `selectedSensorId`.
- The sparkline-style strip is visual/static based on tier, not real historical sensor data.

#### `MassBalanceChart.jsx`

- Displays implied level, measured level, discrepancy, flags, and a Recharts line chart.
- Uses live `chartHistory` from the WebSocket flow or forensic timeline data when passed in.

#### `StartupBanner.jsx`

- Displays normal/startup mode controls.
- Lists stale startup flags.
- Calls `acknowledgeStale(sensor_id)` for stale readings.

#### `HealthTimeline.jsx`

- Fetches `/api/sensors/{sensorId}/health`.
- Shows calibration status, anomaly history, drift trend, and maintenance placeholder data.
- Maps backend calibration statuses:
  - `current` -> `OK`
  - `due_soon` -> `STALE`
  - `expired` -> `EXPIRED`

#### `HandoverBrief.jsx`

- Calls `POST /api/handover/generate`.
- Displays generated handover brief.
- Supports copy and print actions.

#### `QueryPanel.jsx`

- Sends natural-language questions through the Zustand `askQuestion` action.
- Displays answer history and source chips.
- Mounted in the operator right rail.

#### `FlagBar.jsx`

- Combines active mass-balance flags, non-HIGH confidence sensors, and stale startup flags into a compact alert strip.

### Page-Specific Behavior

#### Fleet Overview

- Calls `fetchFleet()` and `/api/fleet/history?hours=24`.
- Refreshes fleet data every 5 seconds.
- Plant card click calls `setPlantId(plant_id)` and navigates to `/operator`.

#### Operator Dashboard

- Opens live WebSocket on mount.
- Fetches predictions for the current plant.
- Renders sensor grid, mass balance, flags, query panel, forecast, health timeline, handover brief, and engineer detail when role is Engineer.

#### Predictions

- Uses predictions from Zustand.
- Fetches predictions for the selected plant if needed.
- Renders forecast cards and action queue.

#### Forensics

- Loads preset list and the `texas-city` preset.
- Provides play/pause, speed, scrubber, and counterfactual mode.
- Can load recent replay data from `/api/forensics/{plant_id}`.

#### Compliance

- Posts to `/api/compliance/generate`.
- Renders report sections and downloads the returned base64 PDF.

#### Graph

- Fetches `/api/graph/{plant_id}`.
- Renders a deterministic SVG graph layout.

#### Sandbox

- Posts to `/api/sandbox/run`.
- Renders result timeline and confidence changes from the returned samples.

## 5. Data Flow

### Live Sensor To Dashboard Flow

End-to-end live data flow:

1. FastAPI lifespan starts one background loop per plant.
2. The loop calls `SensorSimulator.tick()`.
3. The simulator emits readings for each configured sensor.
4. The loop converts reading dicts to `SensorReadingInput` objects.
5. `ConfidenceEngine.compute_confidence()` scores each sensor using:
   - calibration age
   - local stability history
   - cross-sensor checks
   - physical plausibility
6. `MassBalanceEngine.update()` compares integrated net flow with measured level.
7. `StartupManager.check_stale_readings()` flags unchanged values when startup mode is active.
8. The loop updates in-memory plant fields:
   - `latest_readings`
   - `latest_confidence`
   - `latest_mass_balance`
   - `latest_stale_flags`
   - `last_tick_at`
9. The loop writes readings to SQLite every tick.
10. The loop writes confidence logs every 5 ticks.
11. The loop writes anomaly logs when confidence, mass-balance, or stale conditions cross thresholds.
12. `OperatorDashboard` calls `connect()` on mount.
13. `store.js` opens `ws(s)://{window.location.host}/ws/sensors?plant_id={plantId}`.
14. The backend WebSocket route reads the selected plant's latest in-memory fields.
15. It sends `{type: "sensor_update", readings, confidence, mass_balance, mode, stale_flags, ...}` once per second.
16. The Zustand store receives the message and updates:
   - `readings`
   - `confidence`
   - `massBalance`
   - `mode`
   - `staleFlags`
   - `averageConfidence`
   - `chartHistory`
17. React components re-render from Zustand state.
18. `SensorCard`, `MassBalanceChart`, `StartupBanner`, `FlagBar`, and other panels present the updated state.

### REST Data Flows

#### Health Timeline

1. User selects a sensor card.
2. `selectedSensorId` is updated in Zustand.
3. `HealthTimeline` fetches `/api/sensors/{sensorId}/health?plant_id={plantId}`.
4. Backend combines calibration metadata, anomaly logs, and reading history.
5. Frontend maps calibration status labels and renders the panel.

#### Handover Brief

1. User clicks generate in `HandoverBrief`.
2. Frontend posts to `/api/handover/generate?plant_id={plantId}`.
3. Backend reads latest confidence, mass balance, anomalies, mode, and predictions.
4. Handover generator uses Claude or fallback text.
5. Backend logs the generated brief to `shift_handover_logs`.
6. Frontend displays returned `brief`.

#### Fleet Overview

1. Fleet page calls `/api/fleet`.
2. Backend computes per-plant risk from latest in-memory confidence, flags, mass balance, and calibration metadata.
3. Backend sorts plants by risk rank.
4. Frontend renders plant risk cards.
5. Selecting a plant updates Zustand `plantId` and opens `/operator`.

#### Prediction

1. Frontend requests `/api/predictions/{plantId}`.
2. Backend reads persisted `confidence_logs`.
3. Prediction engine fits trend models when there are at least 10 samples.
4. Frontend renders forecast cards and action queue.

#### Natural Language Query

1. User asks a question in `QueryPanel`.
2. Frontend posts `{question, plant_id}` to `/api/query`.
3. Backend assembles live state, confidence histories, fleet summary, anomalies, and predictions.
4. Claude answers if configured; otherwise deterministic fallback logic answers.
5. Frontend appends answer and sources to query history.

#### Forensics

1. Forensics page loads presets.
2. Preset mode fetches synthetic replay data from `/api/forensics/presets/texas-city`.
3. Recent replay mode fetches `/api/forensics/{plantId}?hours=...`.
4. Backend groups persisted readings by timestamp second and attaches confidence data when available.
5. Frontend plays through timeline frames.

## 6. Key Logic & Algorithms

### Confidence Scoring

Implemented in `backend/confidence.py`.

Final confidence score:

```text
confidence =
  calibration_score * 0.30 +
  stability_score * 0.20 +
  cross_sensor_score * 0.30 +
  physical_plausibility_score * 0.20
```

Tiers in normal mode:

- `HIGH`: score >= 80
- `MEDIUM`: score >= 50
- `LOW`: score >= 20
- `CRITICAL`: score < 20

Startup mode changes the medium threshold to 70 through `StartupManager.get_confidence_thresholds()`.

Sub-score details:

- **Calibration score**
  - Uses configured calibration age and interval.
  - Linearly decays as age approaches the calibration interval.
  - Returns low score when calibration is significantly overdue.
- **Stability score**
  - Maintains recent per-sensor history in memory.
  - Penalizes values that remain effectively unchanged longer than the stuck-reading threshold.
  - Penalizes large step changes compared with recent average.
- **Cross-sensor score**
  - Checks relationships such as level vs net flow, inflow vs outflow, and pressure vs level.
  - Some sensor types have little or no cross-sensor validation.
- **Physical plausibility score**
  - Uses static operating envelopes per sensor type.
  - Can use adaptive learned envelopes if they were computed and applied.

This confidence logic is heuristic. It is suitable for a simulator/demo, but it is not a validated industrial safety model.

### Mass-Balance Detection

Implemented in `backend/mass_balance.py`.

Core logic:

- Tracks a rolling window of readings.
- Integrates `flow_in - flow_out` over time.
- Converts integrated net flow to level change using hardcoded `FLOW_TO_LEVEL_RATE = 0.005`.
- Anchors implied level to the first measured level in the window.
- Compares implied level with measured `level`.

Flag thresholds:

- INFO when discrepancy exceeds tolerance.
- WARNING when discrepancy exceeds `2 * tolerance`.
- CRITICAL when discrepancy exceeds `4 * tolerance`.

Only the highest relevant flag is returned for the current state.

### Startup Stale Detection

Implemented in `backend/startup.py`.

Logic:

- Active only when startup mode is enabled.
- Tracks last value and timestamp per sensor.
- If a reading changes less than epsilon `0.01`, it is considered unchanged.
- If unchanged duration exceeds 480 seconds, a stale flag is produced.
- Acknowledged flags are tracked by sensor ID.

### Failure Prediction

Implemented in `backend/prediction.py`.

Current behavior:

- Reads confidence history from the database.
- Requires at least 10 samples.
- Fits a linear model using NumPy.
- Calculates R-squared and labels fit quality as `good`, `fair`, or `poor`.
- Adds heuristic model labels:
  - `step_change` if recent average dropped sharply from previous average.
  - `exponential` if log-transformed fit improves and trend is degrading.
  - otherwise `linear`.
- Predicts time-to-LOW and time-to-CRITICAL only when slope is negative enough.

This is a lightweight forecast, not a full predictive failure engine.

### Natural Language Query

Implemented in `backend/nlquery.py`.

Current behavior:

- With a valid Anthropic key, sends assembled context and the user's question to Claude.
- Without a key or on API failure, uses deterministic fallback rules.
- Fallback can answer about flags, mass balance, worst sensors, safety/risk, and predictions.
- Source extraction is simple and mainly based on sensor IDs in text.

### Causal Graph

Implemented in `backend/causal_graph.py`.

Current behavior:

- Uses static topology definitions per plant.
- Marks nodes by current confidence state.
- Picks likely root cause from anomalous sensors with no anomalous upstream predecessor.
- Builds a propagation chain through anomalous downstream nodes.

This is not using NetworkX and does not infer causality from data.

### Adaptive Thresholds

Implemented in `backend/adaptive_thresholds.py`.

Current behavior:

- Reads recent `sensor_readings`.
- Excludes sensors that had anomalies in the lookback period.
- Requires at least 10 samples.
- Computes mean, population standard deviation, and bounds at `mean +/- 3 * std_dev`.
- Persists results to `adaptive_envelope_logs`.
- Applies learned envelopes to the in-memory confidence engine when endpoint is called.

There is no scheduled learner. Learning is triggered by API usage.

### Sandbox Simulation

Implemented in `backend/main.py` using simulator and engine classes.

Current behavior:

- Creates isolated simulator and analysis engines.
- Applies one failure mode to one sensor.
- Runs sampled ticks over requested duration.
- Returns reading, confidence, mass balance, flags, and all confidence results per sample.

Supported failure modes:

- `calibration_drift`
- `stuck_reading`
- `sg_mismatch`
- `command_state_decoupling`

## 7. Current Limitations

Product and architecture limitations:

- No authentication or backend authorization exists.
- Role selection is frontend-only and only filters navigation emphasis.
- Unknown plant IDs silently fall back to `plant-a`.
- WebSocket live state is opened only by the operator dashboard, not globally.
- `new_anomalies` in the WebSocket payload is always empty.
- `FlagEvent` database model exists but is not clearly written by runtime logic.
- Background plant loops do not restart after unhandled exceptions.
- `POST /api/handover/generate` can return 400 immediately after startup if confidence state has not warmed up.
- Scenario loading accepts an optional path and loads from filesystem if present; this is flexible but risky if exposed beyond local/demo use.

Algorithmic limitations:

- Confidence scoring is heuristic and static-weighted.
- Mass-balance conversion uses hardcoded constants.
- Prediction is lightweight regression over confidence history.
- Causal graph is static topology plus heuristics.
- Adaptive thresholds are on-demand, not scheduled or governed.
- Forensics preset is synthetic and deterministic.
- Recent forensics replay depends on persisted data alignment and may have sparse confidence frames.
- Compliance PDF is a minimal custom PDF, not a full report renderer.

Frontend limitations:

- Frontend does not use `VITE_API_URL` or `VITE_WS_URL`.
- Sensor card sparkline strip is not actual historical data.
- Some pages depend on backend warmup and persisted history; early startup can show sparse or empty states.
- Role-based views are presentation-level, not separate security or API contracts.

Implementation gaps and placeholders:

- Maintenance work orders in health endpoint are placeholder empty data.
- Some PRD-level features are simplified implementations rather than complete industrial workflows.
- No explicit shared schema package exists between frontend and backend.
- No comprehensive frontend/API contract test coverage is visible in the inspected files.

## 8. Environment & Setup

### Backend

Main dependencies from `backend/requirements.txt`:

- `fastapi`
- `uvicorn[standard]`
- `sqlalchemy`
- `aiosqlite`
- `numpy`
- `pydantic`
- `python-dotenv`
- `anthropic`

Important environment variables:

| Variable | Purpose | Code behavior |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy database URL. | Defaults in code to `sqlite:///./confidenceos.db`. Docker compose sets `sqlite:////app/data/confidenceos.db`. |
| `ANTHROPIC_API_KEY` | Enables Claude-backed handover and natural-language query. | If missing/default, fallback generation is used. |
| `BACKEND_HOST` | Docker/runtime host setting. | Used by compose/config, not directly central to app logic. |
| `BACKEND_PORT` | Backend exposed port. | Docker default is `8001`. |

Backend run modes:

- Local development expected backend port: `8001`.
- Docker backend service exposes `8001`.
- Health endpoint: `/api/health`.

### Frontend

Main dependencies from `frontend/package.json`:

- `react`
- `react-dom`
- `react-router-dom`
- `zustand`
- `recharts`
- `@vitejs/plugin-react`
- `vite`
- `tailwindcss`

Frontend dev server:

- Vite port: `5174`.
- Vite proxy:
  - `/api` -> `http://localhost:8001`
  - `/ws` -> `http://localhost:8001`

Frontend environment variables:

| Variable | Intended purpose | Current code behavior |
|---|---|---|
| `VITE_API_URL` | API base URL. | Present in `.env.example`, not used by current frontend code. |
| `VITE_WS_URL` | WebSocket base URL. | Present in `.env.example`, not used by current frontend code. |

Docker frontend:

- Uses Nginx.
- Serves the built SPA.
- Proxies `/api/` and `/ws/` to `backend:8001`.
- Default host port from compose is `5174`.

### Persistence

- Local default SQLite path from code: `./confidenceos.db`.
- Docker compose uses a named volume mounted at `/app/data` and sets database path under that directory.
- Database tables are created by `init_db()` on backend startup.
- There is no migration framework in the inspected code.

### Tests

Tests exist for several backend modules, including simulator, confidence, mass balance, startup, and handover behavior.

Not clearly implemented:

- End-to-end frontend route tests.
- Shared contract tests for API payloads consumed by React components.
- Migration tests.
- Long-running stability tests for plant loops and WebSocket behavior.

## 9. Observations (Critical Thinking)

The system has a coherent simulator-backed HMI core. The live operator loop is understandable: generate readings, score confidence, compute mass-balance, push through WebSocket, render in React. That part is the strongest current architecture.

The system also has many V2 product surfaces implemented as lightweight but useful slices: fleet, predictions, query, forensics, graph, compliance, sandbox, and adaptive thresholds. These are mostly demo-complete rather than production-complete.

Critical inconsistencies and risks:

- `PlantManager.get()` falling back to `plant-a` is the largest data-correctness risk because it can silently show the wrong plant.
- WebSocket `new_anomalies` exists in the contract but is not populated.
- `FlagEvent` suggests a richer flag lifecycle, but active flags are mostly transient or anomaly-log based.
- Frontend environment configuration is misleading because Vite API/WS variables are documented but unused.
- Backend loop health is reported, but failed loops are not recovered.
- Role-based UI can look like access control, but it is only a client-side presentation choice.
- Compliance and forensics features should be described as simulator/demo outputs, not audited industrial records.

Where the design feels incomplete:

- No shared typed API contract exists between FastAPI and React.
- No schema validation layer protects frontend assumptions about field names and enums.
- Simulation, confidence scoring, and prediction are useful for demonstration but not validated against real plant data.
- Adaptive thresholds are triggered by page/API access rather than governed as an operational learning process.
- The database layer uses table creation only; there is no migration or retention strategy.

Where the code is strong enough to build on:

- The per-plant object model is clear and easy to extend.
- The tick loop cleanly separates simulator, confidence, mass-balance, startup, and persistence steps.
- Frontend state is centralized in Zustand and route pages consume it consistently.
- REST endpoints expose most data needed for the current UI without requiring major backend rewrites.

Best mental model:

ConfidenceOS is currently a simulator-first industrial HMI prototype with a working live dashboard and broad demo surfaces. It should not be treated as production industrial control software yet. Its value is in demonstrating confidence-aware plant monitoring workflows, not in guaranteeing validated safety behavior.
