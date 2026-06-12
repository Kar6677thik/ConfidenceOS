/**
 * store.js — Zustand store for ConfidenceOS dashboard.
 *
 * Manages:
 *   - WebSocket connection to /ws/sensors (auto-reconnect)
 *   - Live sensor readings, confidence scores, mass-balance state
 *   - Operating mode (NORMAL / STARTUP)
 *   - Stale reading flags, anomalies
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

  // ── Live data from WebSocket ──────────────────────────────────────────
  readings: [],           // raw sensor readings (latest tick)
  confidence: [],         // confidence results (latest tick)
  massBalance: null,      // mass-balance state (latest tick)
  mode: null,             // startup manager state
  staleFlags: [],         // stale reading flags
  newAnomalies: [],       // anomalies detected this tick
  timestamp: null,        // last update timestamp

  // ── Derived / computed ────────────────────────────────────────────────
  averageConfidence: 0,   // overall plant health score

  // ── Chart history (rolling window) ────────────────────────────────────
  chartHistory: [],       // array of { time, implied, measured, discrepancy }

  // ── UI state ──────────────────────────────────────────────────────────
  selectedSensorId: null,

  // ── Actions ───────────────────────────────────────────────────────────

  selectSensor: (sensorId) => set({ selectedSensorId: sensorId }),

  connect: () => {
    const state = get();
    if (state._ws) return; // already connected

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/sensors`;

    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch (err) {
      console.error('[Store] WebSocket creation failed:', err);
      // schedule reconnect
      const timer = setTimeout(() => {
        set({ _reconnectTimer: null });
        get().connect();
      }, RECONNECT_DELAY);
      set({ _reconnectTimer: timer });
      return;
    }

    ws.onopen = () => {
      console.log('[Store] WebSocket connected');
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
      const res = await fetch('/api/mode/startup', {
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
      const res = await fetch(`/api/mode/startup/acknowledge/${sensorId}`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error(`Server responded ${res.status}`);
    } catch (err) {
      console.error('[Store] acknowledgeStale failed:', err);
    }
  },
}));

export default useStore;
