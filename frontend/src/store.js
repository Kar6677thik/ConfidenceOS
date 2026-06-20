/**
 * store.js - Zustand store for ConfidenceOS Runtime.
 *
 * Manages:
 *   - WebSocket connection to /ws/sensors (auto-reconnect, plant-aware)
 *   - Live sensor readings, confidence scores, mass-balance state
 *   - Operating mode (NORMAL / STARTUP)
 *   - Stale reading flags, anomalies
 *   - V2: Plant selection, role-based views, integrity overview, confidence forecasts
 *   - UI state: selected sensor, mass-balance chart history
 */

import { create } from 'zustand';

// How many data points to keep for the mass-balance chart
const CHART_HISTORY_MAX = 120;

// WebSocket reconnect delay (ms)
const RECONNECT_DELAY = 2000;

const useStore = create((set, get) => ({
  // -- Connection state --------------------------------------------------
  connected: false,
  _ws: null,
  _reconnectTimer: null,
  _intentionalDisconnect: false,
  systemHealth: null,
  healthLoading: false,
  healthError: '',
  lastHealthAt: null,

  // -- Auth (JWT) --------------------------------------------------------
  authToken: null,       // Bearer token from /api/auth/login
  authUser: null,        // { username, role, full_name }
  authLoading: false,
  authError: null,

  // -- V2: Plant & Role --------------------------------------------------
  plantId: 'plant-a',
  role: 'Operator',  // Operator | Maintenance | Engineer | Manager | Auditor

  // -- V2: Instrument integrity overview ---------------------------------
  fleetData: [],
  fleetLoading: false,

  // -- V2: Confidence degradation forecasts ------------------------------
  predictions: {},
  predictionsMeta: null,
  predictionsLoading: false,

  // -- V2: Grounded operator explanation ---------------------------------
  queryHistory: [],
  queryLoading: false,

  // -- Live data from WebSocket ------------------------------------------
  readings: [],           // raw sensor readings (latest tick)
  confidence: [],         // confidence results (latest tick)
  massBalance: null,      // mass-balance state (latest tick)
  mode: null,             // startup manager state
  staleFlags: [],         // stale reading flags
  newAnomalies: [],       // anomalies detected this tick
  plantContext: null,     // advisory context inferred by backend
  incidents: [],          // fused advisory incidents
  incidentTimeline: [],    // lightweight decision-integrity events
  verificationTokens: [],  // compatibility: active field verification tasks
  verificationTasks: [],   // full field verification task lifecycle records
  handoverDebt: null,      // unresolved operational debt ledger
  confidenceDebt: [],      // confidence-hours maintenance priority data
  demoState: null,         // simulator scenario phase and source state
  providerType: null,      // "simulator" | "opcua" | "csv_replay" | "read_only"
  unackedAlarms: 0,        // ISA-18.2 unacknowledged alarm count
  timestamp: null,        // last update timestamp

  // -- Derived / computed ------------------------------------------------
  averageConfidence: 0,   // overall plant health score

  // -- Chart history (rolling window) ------------------------------------
  chartHistory: [],       // array of { time, implied, measured, actual, discrepancy }

  // -- UI state ----------------------------------------------------------
  selectedSensorId: null,

  // -- Actions -----------------------------------------------------------

  selectSensor: (sensorId) => set({ selectedSensorId: sensorId }),

  setPlantId: (plantId) => {
    const state = get();
    if (state.plantId === plantId) return;

    // Disconnect current WS and reconnect with new plant
    state.disconnect();
    set({
      plantId,
      readings: [],
      confidence: [],
      massBalance: null,
      chartHistory: [],
      selectedSensorId: null,
      predictions: {},
      plantContext: null,
      incidents: [],
      incidentTimeline: [],
      verificationTokens: [],
      verificationTasks: [],
      handoverDebt: null,
      confidenceDebt: [],
      demoState: null,
    });

    // Reconnect after state update
    setTimeout(() => get().connect(), 100);
  },

  setRole: (role) => set({ role }),

  login: async (username, password) => {
    set({ authLoading: true, authError: null });
    try {
      const resp = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ username, password }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        set({ authLoading: false, authError: err.detail || 'Login failed.' });
        return false;
      }
      const data = await resp.json();
      set({
        authToken: data.access_token,
        authUser: { username: data.username, role: data.role, full_name: data.full_name },
        role: data.role,
        authLoading: false,
        authError: null,
      });
      return true;
    } catch (e) {
      set({ authLoading: false, authError: 'Network error.' });
      return false;
    }
  },

  logout: () => set({ authToken: null, authUser: null, role: 'Operator' }),

  connect: () => {
    const state = get();
    if (state._ws) return; // already connected
    if (state._reconnectTimer) {
      clearTimeout(state._reconnectTimer);
      set({ _reconnectTimer: null });
    }
    set({ _intentionalDisconnect: false });

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/sensors?plant_id=${state.plantId}`;

    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch (err) {
      console.error('[Store] WebSocket creation failed:', err);
      const timer = setTimeout(() => {
        set({ _reconnectTimer: null });
        get().connect();
      }, RECONNECT_DELAY);
      set({ _reconnectTimer: timer });
      return;
    }

    ws.onopen = () => {
      console.log('[Store] WebSocket connected to', state.plantId);
      set({ connected: true, _ws: ws });
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type !== 'sensor_update') return;

        const confidenceList = data.confidence || [];
        const avgConf = confidenceList.length > 0
          ? Math.round(
              confidenceList.reduce((sum, c) => sum + c.confidence_pct, 0) /
              confidenceList.length
            )
          : 0;

        // Build chart data point
        const mb = data.mass_balance;
        const chartPoint = mb ? {
          time: new Date(data.timestamp * 1000).toLocaleTimeString(),
          implied: mb.implied_level,
          measured: mb.measured_level,
          actual: mb.actual_level,
          discrepancy: mb.discrepancy,
        } : null;

        // Delta-compressed update: only override slow-changing fields when the
        // server signals they changed (via _delta key list).
        const delta = data._delta || null;
        const hasDelta = (key) => !delta || delta.includes(key);

        set((prev) => {
          const newHistory = chartPoint
            ? [...prev.chartHistory, chartPoint].slice(-CHART_HISTORY_MAX)
            : prev.chartHistory;

          return {
            readings: data.readings || [],
            confidence: confidenceList,
            massBalance: mb || null,
            mode: data.mode || null,
            staleFlags: data.stale_flags || [],
            newAnomalies: data.new_anomalies || [],
            providerType: data.provider_type || null,
            unackedAlarms: data.unacked_alarms ?? prev.unackedAlarms,
            timestamp: data.timestamp,
            averageConfidence: avgConf,
            chartHistory: newHistory,
            // Delta-compressed slow fields:
            plantContext: hasDelta('plant_context') ? (data.plant_context || null) : prev.plantContext,
            incidents: hasDelta('incidents') ? (data.incidents || []) : prev.incidents,
            incidentTimeline: hasDelta('incident_timeline') ? (data.incident_timeline || []) : prev.incidentTimeline,
            verificationTokens: hasDelta('verification_tokens') ? (data.verification_tokens || []) : prev.verificationTokens,
            verificationTasks: hasDelta('verification_tasks') ? (data.verification_tasks || data.verification_tokens || []) : prev.verificationTasks,
            handoverDebt: hasDelta('handover_debt') ? (data.handover_debt || null) : prev.handoverDebt,
            confidenceDebt: hasDelta('confidence_debt') ? (data.confidence_debt || []) : prev.confidenceDebt,
            demoState: hasDelta('demo_state') ? (data.demo_state || null) : prev.demoState,
          };
        });
      } catch (err) {
        console.error('[Store] Failed to parse WS message:', err);
      }
    };

    ws.onclose = () => {
      const intentional = get()._intentionalDisconnect;
      console.log('[Store] WebSocket closed', intentional ? 'intentionally' : 'unexpectedly');
      set({ connected: false, _ws: null });
      if (intentional) {
        set({ _intentionalDisconnect: false });
        return;
      }

      const timer = setTimeout(() => {
        set({ _reconnectTimer: null });
        get().connect();
      }, RECONNECT_DELAY);
      set({ _reconnectTimer: timer });
    };

    ws.onerror = (err) => {
      console.error('[Store] WebSocket error:', err);
      ws.close();
    };

    set({ _ws: ws });
  },

  disconnect: () => {
    const { _ws, _reconnectTimer } = get();
    if (_reconnectTimer) clearTimeout(_reconnectTimer);
    set({ _intentionalDisconnect: true, _reconnectTimer: null });
    if (_ws) {
      // Null out handlers before close() to eliminate any race window
      // where onclose fires and schedules a reconnect after intentional close.
      _ws.onclose = null;
      _ws.onerror = null;
      _ws.onmessage = null;
      _ws.close();
    }
    set({ _ws: null, connected: false });
  },

  // -- API actions -------------------------------------------------------

  fetchSystemHealth: async () => {
    set({ healthLoading: true });
    try {
      const res = await fetch('/api/health');
      const payload = await res.json().catch(() => null);
      if (!res.ok) throw new Error(payload?.detail || `Health check failed: ${res.status}`);
      set({
        systemHealth: payload,
        healthError: '',
        healthLoading: false,
        lastHealthAt: Date.now(),
      });
    } catch (err) {
      set({
        healthError: err.message || 'Health check failed.',
        healthLoading: false,
        lastHealthAt: Date.now(),
      });
    }
  },

  toggleStartupMode: async (active) => {
    try {
      const { plantId } = get();
      const res = await fetch(`/api/mode/startup?plant_id=${plantId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active }),
      });
      if (!res.ok) throw new Error(`Server responded ${res.status}`);
    } catch (err) {
      console.error('[Store] toggleStartupMode failed:', err);
    }
  },

  acknowledgeStale: async (sensorId) => {
    try {
      const { plantId } = get();
      const res = await fetch(`/api/mode/startup/acknowledge/${sensorId}?plant_id=${plantId}`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error(`Server responded ${res.status}`);
    } catch (err) {
      console.error('[Store] acknowledgeStale failed:', err);
    }
  },

  // -- V2: Integrity overview actions ------------------------------------

  fetchFleet: async () => {
    set({ fleetLoading: true });
    try {
      const res = await fetch('/api/fleet');
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      set({ fleetData: data.fleet || [], fleetLoading: false });
    } catch (err) {
      console.error('[Store] fetchFleet failed:', err);
      set({ fleetLoading: false });
    }
  },

  // -- V2: Confidence forecast actions -----------------------------------

  fetchPredictions: async (plantId) => {
    const pid = plantId || get().plantId;
    set({ predictionsLoading: true });
    try {
      const res = await fetch(`/api/predictions/${pid}`);
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      set({ predictions: data.predictions || {}, predictionsMeta: data.meta || null, predictionsLoading: false });
    } catch (err) {
      console.error('[Store] fetch confidence forecasts failed:', err);
      set({ predictionsLoading: false, predictionsMeta: null });
    }
  },

  // -- V2: Grounded explanation actions ----------------------------------

  askQuestion: async (question) => {
    const { plantId } = get();
    set({ queryLoading: true });
    try {
      const res = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, plant_id: plantId }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();

      set((prev) => ({
        queryHistory: [
          ...prev.queryHistory,
          { question, answer: data.answer, sources: data.sources || [], source_type: data.source_type, timestamp: Date.now() },
        ].slice(-10), // keep last 10
        queryLoading: false,
      }));
      return data;
    } catch (err) {
      console.error('[Store] askQuestion failed:', err);
      set({ queryLoading: false });
      return { answer: 'Failed to get response. Please try again.', sources: [] };
    }
  },
}));

export default useStore;
