/**
 * store.js — Zustand store for ConfidenceOS V2 Dashboard.
 *
 * Manages:
 *   - WebSocket connection to /ws/sensors (auto-reconnect, plant-aware)
 *   - Live sensor readings, confidence scores, mass-balance state
 *   - Operating mode (NORMAL / STARTUP)
 *   - Stale reading flags, anomalies
 *   - V2: Plant selection, role-based views, fleet data, predictions
 *   - UI state: selected sensor, mass-balance chart history
 */

import { create } from 'zustand';

// How many data points to keep for the mass-balance chart
const CHART_HISTORY_MAX = 120;

// WebSocket reconnect delay (ms)
const RECONNECT_DELAY = 2000;

const useStore = create((set, get) => ({
  // ── Connection state ──────────────────────────────────────────────────
  connected: false,
  _ws: null,
  _reconnectTimer: null,

  // ── V2: Plant & Role ──────────────────────────────────────────────────
  plantId: 'plant-a',
  role: 'Operator',  // Operator | Engineer | Manager | Auditor

  // ── V2: Fleet data ────────────────────────────────────────────────────
  fleetData: [],
  fleetLoading: false,

  // ── V2: Predictions ───────────────────────────────────────────────────
  predictions: {},
  predictionsLoading: false,

  // ── V2: Query ─────────────────────────────────────────────────────────
  queryHistory: [],
  queryLoading: false,

  // ── Live data from WebSocket ──────────────────────────────────────────
  readings: [],           // raw sensor readings (latest tick)
  confidence: [],         // confidence results (latest tick)
  massBalance: null,      // mass-balance state (latest tick)
  mode: null,             // startup manager state
  staleFlags: [],         // stale reading flags
  newAnomalies: [],       // anomalies detected this tick
  plantContext: null,     // advisory context inferred by backend
  incidents: [],          // fused advisory incidents
  incidentTimeline: [],    // lightweight decision-integrity events
  timestamp: null,        // last update timestamp

  // ── Derived / computed ────────────────────────────────────────────────
  averageConfidence: 0,   // overall plant health score

  // ── Chart history (rolling window) ────────────────────────────────────
  chartHistory: [],       // array of { time, implied, measured, discrepancy }

  // ── UI state ──────────────────────────────────────────────────────────
  selectedSensorId: null,

  // ── Actions ───────────────────────────────────────────────────────────

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
    });

    // Reconnect after state update
    setTimeout(() => get().connect(), 100);
  },

  setRole: (role) => set({ role }),

  connect: () => {
    const state = get();
    if (state._ws) return; // already connected

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
          discrepancy: mb.discrepancy,
        } : null;

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
            plantContext: data.plant_context || null,
            incidents: data.incidents || [],
            incidentTimeline: data.incident_timeline || [],
            timestamp: data.timestamp,
            averageConfidence: avgConf,
            chartHistory: newHistory,
          };
        });
      } catch (err) {
        console.error('[Store] Failed to parse WS message:', err);
      }
    };

    ws.onclose = () => {
      console.log('[Store] WebSocket closed, reconnecting...');
      set({ connected: false, _ws: null });

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
    if (_ws) _ws.close();
    set({ _ws: null, connected: false, _reconnectTimer: null });
  },

  // ── API actions ───────────────────────────────────────────────────────

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

  // ── V2: Fleet actions ─────────────────────────────────────────────────

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

  // ── V2: Prediction actions ────────────────────────────────────────────

  fetchPredictions: async (plantId) => {
    const pid = plantId || get().plantId;
    set({ predictionsLoading: true });
    try {
      const res = await fetch(`/api/predictions/${pid}`);
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      set({ predictions: data.predictions || {}, predictionsLoading: false });
    } catch (err) {
      console.error('[Store] fetchPredictions failed:', err);
      set({ predictionsLoading: false });
    }
  },

  // ── V2: NL Query actions ──────────────────────────────────────────────

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
