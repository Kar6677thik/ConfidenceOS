# ConfidenceOS — File Priority & Navigation Guide

This document maps all repository source files into three priority tiers. It is designed to minimize context load during future development sessions by indicating precisely what to read first, what to read for specific features, and what to ignore.

---

## Tier 1: Must Read (Critical System Architecture)

These files define the application's core architecture, routing protocols, state management, and the baseline physics/confidence algorithms. Read these first.

### Backend

#### 1. `backend/main.py`
* **Purpose**: Entry point of the FastAPI application. Houses all REST endpoints (V1 & V2), the 1 Hz WebSocket broadcast server `/ws/sensors`, and scenario injection coordinators.
* **Dependencies**: `backend/plants.py`, `backend/database.py`, `backend/prediction.py`, `backend/causal_graph.py`, `backend/nlquery.py`, `backend/adaptive_thresholds.py`
* **When to Read**: To understand API routing, WebSocket event loops, or how the backend state orchestrator communicates with the database and frontend.
* **Estimated Importance**: **10/10**

#### 2. `backend/plants.py`
* **Purpose**: Implements fleet-level multi-plant caching and management (`plant-a`, `plant-b`, `plant-c`). Computes the consolidated Plant Risk Score using confidence levels, active flags, and calibration age.
* **Dependencies**: `backend/simulator.py`, `backend/confidence.py`, `backend/mass_balance.py`, `backend/startup.py`, `backend/handover.py`
* **When to Read**: To understand how virtual plants are modeled, how multi-tenant states are partitioned, and how risk scoring is normalized.
* **Estimated Importance**: **9/10**

#### 3. `backend/confidence.py`
* **Purpose**: Computes 0-100% composite trust scores for each sensor reading based on calibration age (30%), stability/stuck indicators (20%), cross-sensor valve/flow mapping (30%), and plausibility boundaries (20%).
* **Dependencies**: None (incorporates dynamic adaptive envelopes if calculated)
* **When to Read**: To analyze or modify the core confidence scoring weights, tier classifications, or operating envelope parameters.
* **Estimated Importance**: **9/10**

#### 4. `backend/mass_balance.py`
* **Purpose**: Performs real-time conservation of mass validation by integrating inflow and outflow rates using the trapezoidal rule over a rolling 15-minute window and comparing it to measured vessel levels.
* **Dependencies**: None
* **When to Read**: To inspect the physics integration rules, tolerance envelopes, or flag escalation logic.
* **Estimated Importance**: **9/10**

### Frontend

#### 5. `frontend/src/store.js`
* **Purpose**: Zustand store coordinating the entire frontend. Manages WebSocket connections/reconnections, plant switching, operator role state, query results, and live telemetry data pipelines.
* **Dependencies**: None
* **When to Read**: Whenever modifying frontend state, API connections, UI caches, or handling new telemetry parameters.
* **Estimated Importance**: **10/10**

#### 6. `frontend/src/App.jsx`
* **Purpose**: The main router and shell of the web application. Configures page-level routing routes to the view modules and manages the global bottom status bar.
* **Dependencies**: `frontend/src/store.js`, components in `frontend/src/components/`, `react-router-dom`
* **When to Read**: To understand page routing or modify the root application shell.
* **Estimated Importance**: **9/10**

---

## Tier 2: Feature Specific (Read only when required)

These files implement specific business features, analytical pages, or UI panels. Open them only when developing or debugging those specific domains.

### Modular Page Views (Frontend)

* `frontend/src/views/FleetOverview.jsx`: Grid view ranking plant integrity summaries and risk cards.
* `frontend/src/views/OperatorDashboard.jsx`: Live operator dashboard rendering sensor grids, mass-balance charts, and side-panel utilities.
* `frontend/src/views/PredictiveTimeline.jsx`: Predictive maintenance degradation timeline with probability corridors and confidence debt priorities.
* `frontend/src/views/CausalGraph.jsx`: SVG-based diagnostic network displaying BFS propagation chains.
* `frontend/src/views/ForensicsReplay.jsx`: Playback player enabling scrubbed simulation presets.
* `frontend/src/views/CompliancePortal.jsx`: Alarm distribution charts, statistics, and audit PDF exporter.
* `frontend/src/views/SandboxSimulator.jsx`: Direct scenario failure injector panel.
* `frontend/src/views/EngineerDeepDive.jsx`: Operating envelope visualizer and adaptive thresholds explorer.

### Backend Adapters & Engines

#### 7. `backend/opc_ua_adapter.py` (New)
* **Purpose**: Industrial adapter client template subscribing to a live OPC UA server's tags in a thread-safe, read-only manner.
* **Dependencies**: `tag_provider.py`
* **When to Read**: Connecting to physical industrial server protocols or testing tag-provider subclasses.
* **Estimated Importance**: **8/10**

#### 8. `backend/adaptive_thresholds.py`
* **Purpose**: Dynamic operating envelopes calculations. Computes per-sensor learned envelopes using standard deviations on historical readings.
* **Dependencies**: `backend/database.py` (reads SensorReading logs and Anomaly logs)
* **When to Read**: When modifying how plausibility envelopes are computed or updating standard deviation bounds.
* **Estimated Importance**: **8/10**

#### 9. `backend/prediction.py`
* **Purpose**: Predictive Failure Engine. Uses `numpy.polyfit` linear regression on database histories to forecast when a degraded sensor will cross LOW (50%) and CRITICAL (20%) trust thresholds.
* **Dependencies**: None (imported by `backend/main.py`)
* **When to Read**: When working on degradation modeling, forecasting alerts, or failure schedule recommendations.
* **Estimated Importance**: **8/10**

#### 10. `backend/causal_graph.py`
* **Purpose**: Maps directional dependencies between sensors and uses a Breadth-First Search (BFS) to trace anomalous propagation paths back to their root cause.
* **Dependencies**: None
* **When to Read**: When adjusting plant topology mappings or refining root-cause narrative generation.
* **Estimated Importance**: **7/10**

#### 11. `backend/startup.py`
* **Purpose**: Tightens operational envelopes and flags stuck sensors (unchanged readings $> 8$ minutes) during high-risk startup windows.
* **Dependencies**: None
* **When to Read**: When updating startup mode rules, acknowledgment flows, or custom threshold overrides.
* **Estimated Importance**: **7/10**

#### 12. `backend/handover.py`
* **Purpose**: Generates shift handover briefs. Queries the Anthropic Claude API using plant state snapshots and falls back to a structured template if no key is configured.
* **Dependencies**: None
* **When to Read**: When working on operator communication screens or updating LLM system prompting.
* **Estimated Importance**: **6/10**

#### 13. `backend/nlquery.py`
* **Purpose**: Natural Language Query Interface. Evaluates user text inputs against current plant conditions (readings, anomalies, predictions) using grounded Claude prompts or regex-driven fallbacks.
* **Dependencies**: None
* **When to Read**: When tweaking control room query parameters, citation extraction rules, or regex keywords.
* **Estimated Importance**: **6/10**

#### 14. `backend/simulator.py`
* **Purpose**: Implements mock telemetry generation and manages scenario failure injections (e.g. drift, stuck readings).
* **Dependencies**: None
* **When to Read**: When adding new virtual sensors, adjusting simulator ticks, or injecting new failure scenarios.
* **Estimated Importance**: **6/10**

#### 15. `backend/database.py`
* **Purpose**: SQLite schema definitions (SQLAlchemy 2.0).
* **Dependencies**: None
* **When to Read**: When changing database schemas, querying metrics, or adding historical persistence fields.
* **Estimated Importance**: **7/10**

### Frontend Components

* `frontend/src/components/SensorCard.jsx`: Multi-score cell displaying NAMUR NE107 diagnostic states. (Importance: **7/10**)
* `frontend/src/components/ConfidenceDebtPanel.jsx`: Dynamic prioritization list tracking cumulative plant confidence debt. (Importance: **7/10**)
* `frontend/src/components/TrustDependencyGraph.jsx`: Topology flow displaying dependencies and node rankings. (Importance: **7/10**)
* `frontend/src/components/HandoverBrief.jsx`: Interactive shift-change card featuring a SAP PM / IBM Maximo ERP work order exporter. (Importance: **6/10**)
* `frontend/src/components/MassBalanceChart.jsx`: Renders the live discrepancy and flow timelines using Recharts. (Importance: **6/10**)
* `frontend/src/components/HealthTimeline.jsx`: Visualizes anomaly histories and severity distributions for the currently selected sensor. (Importance: **5/10**)
* `frontend/src/components/StartupBanner.jsx`: Interactive banner to toggle startup mode and acknowledge stale sensor flags. (Importance: **5/10**)
* `frontend/src/components/FlagBar.jsx` & `QueryPanel.jsx`: Banners and natural language search boxes. (Importance: **5/10**)

---

## Tier 3: Rarely Needed (Tests, Configuration, Assets)

These files are configuration settings, static visual assets, or test files that require no reading during general development unless writing test assertions or updating dev ops.

* **Tests** (`backend/test_*.py`): Contains localized validation assertions. Read only when writing features that alter math engines or endpoint schemas. (Importance: **3/10**)
* **Stitch Files** (`stitch_confidenceos_industrial_hmi/...`): Mockup pages and reference preview templates. (Importance: **2/10**)
* **Scenarios** (`backend/scenario*.json`): JSON specifications of mock sensor values during failure sequences. (Importance: **2/10**)
* **Docker & Server Configs** (`backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `docker-compose.yml`): Container deployments. (Importance: **2/10**)
* **Frontend Configs** (`eslint.config.js`, `vite.config.js`, `package.json`): Build setups. (Importance: **1/10**)
* **Static Assets** (`hero.png`, `index.css`): Stylesheets. (Importance: **1/10**)
