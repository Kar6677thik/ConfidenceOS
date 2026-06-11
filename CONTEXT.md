# ConfidenceOS — Project Context Document

> **Last Updated:** 2026-06-11 | **Sprint Day:** 1 | **Active Work:** Module 1 complete — awaiting review before Module 2

## Project Summary

ConfidenceOS is a next-generation industrial Human-Machine Interface (HMI) that attaches real-time confidence scores to every sensor reading, runs continuous mass-balance cross-checks against physical conservation laws, and auto-generates structured shift handover briefs. It is built for a hackathon at the Institute of Aeronautical Engineering, Hyderabad, and is grounded in the BP Texas City, Three Mile Island, and Esso Longford industrial disasters.

## Architecture Overview

```
[ LAYER 1 — DATA LAYER ]
  Sensor Simulator (Python) — generates realistic streams for 6 sensor types
  Failure Injection Engine — introduces calibration drift, stuck readings, cross-sensor divergence
  SQLite Database — stores sensor history, calibration records, anomaly log

          |  WebSocket (FastAPI)  |

[ LAYER 2 — INTELLIGENCE LAYER ]
  Confidence Scoring Engine — per-sensor trust score (0-100%)
  Mass-Balance Engine — conservation-of-mass cross-check, volume delta tracking
  Anomaly Classifier — categorizes deviations: drift, stuck, implausible, divergent
  LLM Integration (Claude API) — natural language handover brief generation

          |  REST + WebSocket API  |

[ LAYER 3 — PRESENTATION LAYER ]
  React Dashboard — live sensor readings with confidence indicators
  Mass-Balance Panel — real-time inflow/outflow/implied-level visualization
  Sensor Health Timeline — per-sensor maintenance and anomaly history
  Startup Mode UI — heightened scrutiny overlay
  Shift Handover Generator — LLM-powered shift brief interface
```

### Data Flow
1. `SensorSimulator` generates sensor readings at 1 Hz with optional failure injection via `scenario.json`
2. Readings are persisted to SQLite via SQLAlchemy
3. FastAPI publishes readings over WebSocket to the frontend
4. Confidence Scoring Engine computes per-sensor trust scores (0–100%)
5. Mass-Balance Engine continuously integrates inflow/outflow and compares to level sensor
6. React dashboard renders live data with confidence indicators, mass-balance chart, and health timeline
7. Shift Handover Brief generator sends system state to Claude API for natural-language brief

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend API | FastAPI | latest |
| Runtime | Python | 3.11+ |
| Database | SQLite + SQLAlchemy | SQLAlchemy 2.x |
| LLM / AI | Claude API | claude-sonnet-4-20250514 |
| Frontend | React + Vite | React 18, Vite 5 |
| Charting | Recharts | latest |
| Styling | Tailwind CSS | v4 |
| State Mgmt | Zustand | latest |
| Deployment | Docker Compose | v3 |
| Version Control | Git + GitHub | — |

## Directory Structure

```
confidenceOS/
├── CONTEXT.md                    # This file — project handover document
├── prd.txt                       # Product Requirements Document
├── docker-compose.yml            # One-command deployment
├── .env.example                  # Environment variables template
├── .gitignore                    # Git ignore rules
│
├── backend/
│   ├── requirements.txt          # Python dependencies (FastAPI, SQLAlchemy, numpy, etc.)
│   ├── Dockerfile                # Backend container
│   ├── main.py                   # FastAPI app — WebSocket /ws/sensors, REST /api/*
│   ├── database.py               # SQLAlchemy setup — SensorReading & AnomalyLog models
│   ├── simulator.py              # SensorSimulator class — 6 sensors, 4 failure modes
│   ├── scenario.json             # Texas City compressed demo scenario
│   ├── test_simulator.py         # 10 unit tests for the simulator (all passing)
│   └── venv/                     # Python virtual environment (not committed)
│
└── frontend/
    ├── package.json              # Node deps (react, recharts, zustand, tailwindcss)
    ├── Dockerfile                # Multi-stage build → nginx
    ├── nginx.conf                # Nginx proxy config (API + WS → backend)
    ├── vite.config.js            # Vite + Tailwind v4 plugin + dev proxy
    ├── index.html                # HTML entry point
    └── src/
        ├── main.jsx              # React 18 entry point
        ├── App.jsx               # Placeholder root component
        └── index.css             # Tailwind v4 import
```

## Module Status

| Module | Owner | Status | Notes |
|--------|-------|--------|-------|
| 1. Sensor Simulator | Backend | **Done** | 6 sensors, 4 failure modes, WebSocket 1Hz, SQLite persistence, 10/10 tests passing |
| 2. Confidence Scoring Engine | Backend | Not Started | Composite 0–100% trust score per sensor |
| 3. Mass-Balance Cross-Check | Backend | Not Started | Conservation-of-mass real-time check |
| 4. Sensor Health Timeline | Full Stack | Not Started | Per-sensor history view |
| 5. Startup Mode | Frontend | Not Started | Heightened scrutiny UI overlay |
| 6. Shift Handover Brief | Backend + AI | Not Started | Claude API natural-language brief |
| 7. React Dashboard | Frontend | Not Started | Live sensor grid, mass-balance chart, panels |

## Current Sprint

- **Sprint Day:** 1
- **Active Work:** Module 1 (Sensor Simulator) — **COMPLETE**, awaiting user review
- **Next Up:** Module 2 (Confidence Scoring Engine) — pending review approval

## Module 1 Test Results

```
10 passed, 0 failed, 10 total
- All 6 sensor types present
- tick() produces 6 valid readings
- All readings within physical bounds over 100 ticks
- Readings have realistic noise/variation
- Calibration drift failure mode works
- Stuck reading failure mode works
- SG mismatch failure mode works (Texas City)
- Command-state decoupling works (TMI)
- scenario.json loads correctly (4 failures)
- Failure timing respects start_time
```

WebSocket tested end-to-end: 6 readings at 1 Hz, SQLite persistence verified, REST history API working.

## Known Issues / Blockers

- Windows terminal needs `$env:PYTHONIOENCODING="utf-8"` for Unicode test output (cosmetic only).
- No other blockers.

## How to Run Locally

### Backend (Python)
```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend (React)
```bash
cd frontend
npm install
npm run dev
```

### Full Stack (Docker)
```bash
docker-compose up --build
```

## Environment Variables

See `.env.example` in the repo root:
```
ANTHROPIC_API_KEY=your_anthropic_api_key_here
DATABASE_URL=sqlite:///./confidenceos.db
BACKEND_PORT=8000
FRONTEND_PORT=5173
```

## Git Branching Strategy

- `main` — production-ready, no direct commits
- `dev` — integration branch, all feature branches merge here first
- `feature/*` — one branch per module or feature (e.g., `feature/sensor-simulator`)
- PRs required from `feature/*` → `dev` → `main`
