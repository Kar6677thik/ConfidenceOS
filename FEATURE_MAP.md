# ConfidenceOS — Feature Mapping & Implementation Guide

This document catalogs every functional feature (modules V1 and V2) of ConfidenceOS, mapping them directly to their corresponding files, API endpoints, and implementation status. 

---

## 1. Feature Map Directory

### Module 1: Sensor Simulator
* **Purpose**: Generates 1 Hz raw sensor streams and processes programmed failure injections.
* **Backend Files**: `backend/simulator.py`
* **Frontend Files**: None (rendered implicitly through dashboard feeds)
* **API Endpoints**:
  * `POST /api/scenario/load` (Loads simulated profiles)
  * `POST /api/scenario/reset` (Resets timeline clock)
* **Dependencies**: None
* **Implementation Status**: **Completed**

### Module 2: Confidence Scoring Engine
* **Purpose**: Evaluates real-time sensor measurements against calibration, stability, and plausibility rules to output a 0-100% composite trust score.
* **Backend Files**: `backend/confidence.py`
* **Frontend Files**: `frontend/src/components/SensorCard.jsx` (displays sub-scores and gauges)
* **API Endpoints**: Broadcasts real-time updates via `ws://.../ws/sensors`
* **Dependencies**: None
* **Implementation Status**: **Completed**

### Module 3: Mass-Balance Cross-Check Engine
* **Purpose**: Performs real-time trapezoidal flow integrations to check conservation-of-mass rules against vessel levels.
* **Backend Files**: `backend/mass_balance.py`
* **Frontend Files**: `frontend/src/components/MassBalanceChart.jsx` (recharts plot)
* **API Endpoints**: Broadcasts real-time updates via `ws://.../ws/sensors`
* **Dependencies**: None
* **Implementation Status**: **Completed**

### Module 4: Sensor Health Timeline
* **Purpose**: Displays historical logs of anomalies and severity levels for the currently selected sensor.
* **Backend Files**: `backend/database.py` (queries sqlite logs)
* **Frontend Files**: `frontend/src/components/HealthTimeline.jsx` (rendered in side panel)
* **API Endpoints**: `GET /api/anomalies/{sensor_id}`
* **Dependencies**: SQLite database logs
* **Implementation Status**: **Completed**

### Module 5: Startup Scrutiny Manager
* **Purpose**: Implements tighter operational envelopes, elevates confidence requirements, and tracks stuck sensors during startups.
* **Backend Files**: `backend/startup.py`
* **Frontend Files**: `frontend/src/components/StartupBanner.jsx` (operator checkboxes)
* **API Endpoints**:
  * `GET /api/mode` (current startup/normal state)
  * `POST /api/mode/startup` (toggle startup scrutiny)
  * `POST /api/mode/startup/acknowledge/{sensor_id}` (acknowledge stuck alarm)
* **Dependencies**: None
* **Implementation Status**: **Completed**

### Module 6: Shift Handover Brief Generator
* **Purpose**: Aggregates shift events, anomalies, and active alerts into a structured natural language handover brief.
* **Backend Files**: `backend/handover.py`
* **Frontend Files**: `frontend/src/components/HandoverBrief.jsx` (brief render card in side rail)
* **API Endpoints**:
  * `POST /api/handover/generate` (compile new handover brief)
  * `GET /api/handover/latest` (fetch latest cached brief)
* **Dependencies**: Claude API (with structured local markdown fallback parser)
* **Implementation Status**: **Completed**

### Module 7: Operator HMI Dashboard
* **Purpose**: Primary control room grid layouts consolidating real-time sparklines, timelines, charts, and startup banner modules.
* **Backend Files**: `backend/main.py`
* **Frontend Files**: `frontend/src/App.jsx` (OperatorDashboard view component)
* **API Endpoints**: Unified WebSocket subscription `/ws/sensors`
* **Dependencies**: All V1 core engines
* **Implementation Status**: **Completed**

### Module 8: Natural Language Query Panel
* **Purpose**: Lets operators query the plant database in plain English, returning cited sensor details.
* **Backend Files**: `backend/nlquery.py`
* **Frontend Files**: `frontend/src/components/QueryPanel.jsx` (embedded in operator panel rail)
* **API Endpoints**: `POST /api/query`
* **Dependencies**: Claude API (with keyword matching local fallback)
* **Implementation Status**: **Completed**

### Module 9: Fleet Manager
* **Purpose**: Aggregates risk summaries and operational indicators for all virtual plants.
* **Backend Files**: `backend/plants.py`
* **Frontend Files**: `frontend/src/App.jsx` (FleetOverviewPage component)
* **API Endpoints**: `GET /api/fleet`, `GET /api/fleet/history`
* **Dependencies**: `backend/plants.py` PlantManager
* **Implementation Status**: **Completed**

### Module 10: Predictive Failure Dashboard
* **Purpose**: Renders predicted degradation timelines before confidence drops below acceptable levels.
* **Backend Files**: `backend/prediction.py`
* **Frontend Files**: `frontend/src/App.jsx` (PredictiveTimelinePage component & PredictionCard)
* **API Endpoints**:
  * `GET /api/predictions/{plant_id}` (all sensors)
  * `GET /api/predictions/{plant_id}/{sensor_id}` (single sensor)
* **Dependencies**: SQLite historical database logs
* **Implementation Status**: **Completed**

### Module 11: Incident Forensics & Replay
* **Purpose**: Play, pause, and scrub back through historical data logs to dissect plant disturbances.
* **Backend Files**: `backend/main.py` (replay endpoints)
* **Frontend Files**: `frontend/src/App.jsx` (ForensicsPage component)
* **API Endpoints**:
  * `GET /api/forensics/presets` (Texas City etc. scenarios)
  * `GET /api/forensics/{plant_id}` (historical telemetry timeline)
* **Dependencies**: SQLite historical databases
* **Implementation Status**: **Completed**

### Module 12: Causal Graph Explorer
* **Purpose**: Shows physical causal node trees, highlighting anomaly propagations downstream.
* **Backend Files**: `backend/causal_graph.py`
* **Frontend Files**: `frontend/src/App.jsx` (CausalGraphPage component)
* **API Endpoints**: `GET /api/graph/{plant_id}`
* **Dependencies**: Directed topology maps
* **Implementation Status**: **Completed**

### Module 13: Compliance Audits Panel
* **Purpose**: Compiles alarm records, sensor stats, and shift logs into audit sheets.
* **Backend Files**: `backend/main.py` (compliance endpoint)
* **Frontend Files**: `frontend/src/App.jsx` (CompliancePage component)
* **API Endpoints**: `POST /api/compliance/generate`
* **Dependencies**: Shift briefs database logs
* **Implementation Status**: **Completed**

### Module 14: Simulation Sandbox
* **Purpose**: Isolated sandbox testing of simulated scenarios without modifying production databases.
* **Backend Files**: `backend/main.py` (sandbox run endpoint)
* **Frontend Files**: `frontend/src/App.jsx` (SandboxPage component)
* **API Endpoints**: `POST /api/sandbox/run`
* **Dependencies**: Isolated instances of simulator and analytics engines
* **Implementation Status**: **Completed**

### Module 15: Adaptive Plausibility Envelopes (New V2 addition)
* **Purpose**: Computes operating envelopes dynamically by calculating mean and standard deviation (3-sigma) over recent anomaly-free historical readings.
* **Backend Files**: `backend/adaptive_thresholds.py`
* **Frontend Files**: `frontend/src/App.jsx` (EngineerDeepDive info section renders envelope details)
* **API Endpoints**: `GET /api/adaptive-thresholds/{plant_id}`
* **Dependencies**: SQLite database tables (`SensorReading`, `AnomalyLog`, `AdaptiveEnvelopeLog`)
* **Implementation Status**: **Completed**

---

## 2. Future Enhancements & Recommendations

Since all baseline V1 and V2 modules have been completed, development focuses on stability and UX:
1. **Dynamic Graph Layout Styling**: Upgrade CausalGraphPage node layouts from static SVG positioning to dynamic network physics (e.g. via D3 or React Flow).
2. **Offline Replay Scrubbing**: Allow playing back live-saved database chunks beyond the pre-configured Texas City preset.
3. **Database Migration Pipeline**: Integrate Alembic for schema migrations as databases scale.
