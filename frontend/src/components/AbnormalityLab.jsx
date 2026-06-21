/**
 * AbnormalityLab.jsx — ConfidenceOS Simulation Lab
 *
 * Comprehensive training console covering every HMI use case.
 *
 * Tabs:
 *   Scenarios  — 7 scenarios (3 file-based + 4 compound multi-inject)
 *   Demo Tours — 8 guided walkthroughs, one per HMI persona / feature
 *   Inject     — single-sensor failure injection with per-type parameter controls
 *   Controls   — scenario lifecycle (start, advance) + reset operations
 *
 * All actions configure the simulated source only.
 * ConfidenceOS never writes plant controls.
 */

import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useStore from '../store';
import apiFetch from '../lib/apiFetch';

const FALLBACK_SENSORS = ['LT-5100', 'FI-2010', 'FO-2020', 'PT-3100', 'TT-4100', 'ZT-6100'];

// ── Scenario definitions ─────────────────────────────────────────────────────
// type:'file'   → loads a scenario JSON via /api/scenario/load
// type:'inject' → sequentially injects failures via /api/sim/inject
const SCENARIOS = [
  {
    type: 'file',
    file: 'scenario.json',
    label: 'Texas City Overfill',
    roleLabel: 'Operator',
    roleColor: '#22c55e',
    accentColor: '#ff5252',
    activateImmediately: true,
    hint: 'LT-5100 frozen → ZT-6100 decoupled → TT drift → PT frozen',
    demonstrates: 'Root Cause · Mass Balance Mismatch · Trust Quarantine',
  },
  {
    type: 'file',
    file: 'scenario_b.json',
    label: 'North Sea Cold Restart',
    roleLabel: 'Engineer',
    roleColor: '#0a84ff',
    accentColor: '#ffcc00',
    hint: 'TT-4100 & PT-3100 calibration drift on startup',
    demonstrates: 'Root Cause · Predictive Timeline · Cascade Confidence',
  },
  {
    type: 'file',
    file: 'scenario_c.json',
    label: 'Water Treatment Valve',
    roleLabel: 'Maintenance',
    roleColor: '#f97316',
    accentColor: 'rgb(150,100,236)',
    hint: 'ZT-6100 command-state decoupling (valve stuck open)',
    demonstrates: 'What-If Propagation · Valve Decouple · Work Queue',
  },
  {
    type: 'inject',
    label: 'Mass Balance Crisis',
    roleLabel: 'Operator',
    roleColor: '#22c55e',
    accentColor: '#ff8c33',
    hint: 'FI-2010 inflow drift + FO-2020 density mismatch',
    demonstrates: 'Mass Balance Divergence · Material Imbalance Alert',
    injections: [
      { sensor_id: 'FI-2010', failure_type: 'calibration_drift', drift_rate: 1.2 },
      { sensor_id: 'FO-2020', failure_type: 'sg_mismatch', sg_actual: 0.65, sg_calibrated: 0.80 },
    ],
  },
  {
    type: 'inject',
    label: 'Cascade Multi-Failure',
    roleLabel: 'Engineer',
    roleColor: '#0a84ff',
    accentColor: '#ff5252',
    hint: 'LT-5100 frozen + PT-3100 drifting + ZT-6100 decoupled',
    demonstrates: 'Causal Graph Cascade · Root Cause · What-If Panel',
    injections: [
      { sensor_id: 'LT-5100', failure_type: 'stuck_reading' },
      { sensor_id: 'PT-3100', failure_type: 'calibration_drift', drift_rate: 0.5 },
      { sensor_id: 'ZT-6100', failure_type: 'command_state_decoupling', commanded_value: 0, actual_value: 85 },
    ],
  },
  {
    type: 'inject',
    label: 'SG Mismatch Pair',
    roleLabel: 'Maintenance',
    roleColor: '#f97316',
    accentColor: '#5fd0c5',
    hint: 'FI-2010 + FO-2020 both calibrated for wrong fluid density',
    demonstrates: 'SG Compensation · Flow Meter Recalibration Workflow',
    injections: [
      { sensor_id: 'FI-2010', failure_type: 'sg_mismatch', sg_actual: 0.72, sg_calibrated: 0.80 },
      { sensor_id: 'FO-2020', failure_type: 'sg_mismatch', sg_actual: 0.68, sg_calibrated: 0.80 },
    ],
  },
  {
    type: 'inject',
    label: 'All-Analog Drift',
    roleLabel: 'Engineer',
    roleColor: '#0a84ff',
    accentColor: '#ffcc00',
    hint: 'LT-5100, TT-4100, PT-3100 simultaneous calibration drift',
    demonstrates: 'Fleet Integrity · Confidence Scoring · ISA-18.2 Alarm Flood',
    injections: [
      { sensor_id: 'LT-5100', failure_type: 'calibration_drift', drift_rate: 0.6 },
      { sensor_id: 'TT-4100', failure_type: 'calibration_drift', drift_rate: 0.8 },
      { sensor_id: 'PT-3100', failure_type: 'calibration_drift', drift_rate: 0.4 },
    ],
  },
];

// ── Demo tours ───────────────────────────────────────────────────────────────
// Each tour is a guided walkthrough for a specific HMI persona or feature.
// Steps are executable: 'inject' / 'multi-inject' / 'scenario' / 'fullReset' / 'nav'
// Info steps ('info') are display-only guidance notes.
const TOURS = [
  {
    id: 'root-cause',
    label: 'AI Root Cause',
    persona: 'Any role',
    color: '#5fd0c5',
    steps: [
      {
        type: 'inject',
        label: 'Inject LT-5100 calibration drift (degrades level transmitter confidence)',
        payload: { sensor_id: 'LT-5100', failure_type: 'calibration_drift', drift_rate: 0.8 },
      },
      { type: 'nav', label: 'Navigate to Runtime Platform', path: '/runtime' },
      { type: 'info', label: 'Select the LT-5100 faceplate (V-5100 vessel) in the left dock → click "Analyze Root Cause" in the right panel' },
      { type: 'info', label: 'If AI is configured, the panel shows a narrative + fault class. "AI" badge = LLM-assisted; "Deterministic" = fallback.' },
    ],
  },
  {
    id: 'what-if',
    label: 'What-If Cascade',
    persona: 'Engineer',
    color: '#0a84ff',
    steps: [
      {
        type: 'inject',
        label: 'Inject FI-2010 stuck/frozen reading (flow meter frozen)',
        payload: { sensor_id: 'FI-2010', failure_type: 'stuck_reading' },
      },
      { type: 'nav', label: 'Navigate to Engineer Deep Dive', path: '/engineer' },
      { type: 'info', label: 'Scroll down to the What-If panel → select FI-2010 → drag the confidence slider to 20% → click Simulate' },
      { type: 'info', label: 'The panel shows downstream sensors affected by the BFS cascade (confidence dampens 40% per hop)' },
    ],
  },
  {
    id: 'compliance',
    label: 'Compliance Report PDF',
    persona: 'Manager / Auditor',
    color: '#a855f7',
    steps: [
      {
        type: 'scenario',
        label: 'Load Texas City Overfill (populates anomaly rows and alarm history)',
        file: 'scenario.json',
      },
      { type: 'nav', label: 'Navigate to Compliance Portal', path: '/compliance' },
      { type: 'info', label: 'Click "Download Operational Summary Report (PDF)" — the formatted PDF includes sensor anomalies, alarms, and trust state' },
      { type: 'info', label: 'PDF has page headers/footers, bold section titles, bullet lists, and page numbers' },
    ],
  },
  {
    id: 'causal-graph',
    label: 'Causal Graph Cascade',
    persona: 'Engineer',
    color: '#0a84ff',
    steps: [
      {
        type: 'multi-inject',
        label: 'Inject upstream + downstream sensor failures (level & pressure)',
        injections: [
          { sensor_id: 'LT-5100', failure_type: 'stuck_reading' },
          { sensor_id: 'PT-3100', failure_type: 'calibration_drift', drift_rate: 0.5 },
        ],
      },
      { type: 'nav', label: 'Navigate to Causal Graph', path: '/graph' },
      { type: 'info', label: 'Observe degraded nodes (orange/red) and the causal dependency paths between sensors' },
      { type: 'nav', label: 'Navigate to Engineer Deep Dive for What-If analysis on the same sensors', path: '/engineer' },
    ],
  },
  {
    id: 'fleet',
    label: 'Fleet Integrity View',
    persona: 'Manager',
    color: '#22c55e',
    steps: [
      {
        type: 'multi-inject',
        label: 'Degrade 3 sensors for visible fleet integrity impact',
        injections: [
          { sensor_id: 'LT-5100', failure_type: 'stuck_reading' },
          { sensor_id: 'TT-4100', failure_type: 'calibration_drift', drift_rate: 0.6 },
          { sensor_id: 'PT-3100', failure_type: 'calibration_drift', drift_rate: 0.4 },
        ],
      },
      { type: 'nav', label: 'Navigate to Fleet Overview', path: '/integrity' },
      { type: 'info', label: 'Observe plant integrity score drop and the sensor tier distribution (HIGH / MEDIUM / LOW / CRITICAL)' },
    ],
  },
  {
    id: 'shift-handover',
    label: 'Shift Handover Workflow',
    persona: 'Operator / Manager',
    color: '#a855f7',
    steps: [
      {
        type: 'scenario',
        label: 'Load Texas City (creates open verification tasks blocking handover)',
        file: 'scenario.json',
      },
      { type: 'nav', label: 'Navigate to Shift Channel', path: '/handover' },
      { type: 'info', label: 'Review "Open Items" — handover may be blocked by unresolved trust anomalies or pending tasks' },
      { type: 'nav', label: 'Navigate to Work Queue to inspect pending verification tasks', path: '/work-queue' },
    ],
  },
  {
    id: 'predictions',
    label: 'Predictive Timeline',
    persona: 'Engineer',
    color: '#0a84ff',
    steps: [
      {
        type: 'inject',
        label: 'Inject slow calibration drift on TT-4100 (temperature probe)',
        payload: { sensor_id: 'TT-4100', failure_type: 'calibration_drift', drift_rate: 0.3 },
      },
      { type: 'nav', label: 'Navigate to Predictive Timeline', path: '/predictions' },
      { type: 'info', label: 'Observe confidence forecast curves trending downward for the degrading sensor over the next horizon window' },
    ],
  },
  {
    id: 'studio',
    label: 'Studio Build & Publish',
    persona: 'Engineer',
    color: '#5fd0c5',
    steps: [
      { type: 'fullReset', label: 'Full reset to clean baseline state (clears Studio + simulator + shift notes)' },
      { type: 'nav', label: 'Navigate to Studio Workspace', path: '/studio' },
      { type: 'info', label: 'Select "texas_city_vessel" asset model → click Build → click Publish' },
      { type: 'nav', label: 'Return to Runtime to verify the published model is active', path: '/runtime' },
    ],
  },
];

// ── Failure type definitions ─────────────────────────────────────────────────
const FAILURE_TYPES = [
  {
    type: 'calibration_drift',
    label: 'Calibration Drift',
    color: '#ffcc00',
    params: ['drift_rate'],
    hint: 'Sensor reading drifts away from true value at the specified rate per tick.',
  },
  {
    type: 'stuck_reading',
    label: 'Stuck / Frozen',
    color: '#ff8c33',
    params: [],
    hint: 'Sensor output freezes at the last observed value. No oscillation, no response to process changes.',
  },
  {
    type: 'sg_mismatch',
    label: 'SG Mismatch',
    color: '#ff5252',
    params: ['sg_actual', 'sg_calibrated'],
    hint: 'Flow meter calibrated for a different fluid density than the actual process fluid.',
  },
  {
    type: 'command_state_decoupling',
    label: 'Valve Decouple',
    color: 'rgb(150,100,236)',
    params: ['commanded_value', 'actual_value'],
    hint: 'Valve position feedback disagrees with the commanded setpoint (stuck, seized, or positioner fault).',
  },
];

// ── Default parameter values ─────────────────────────────────────────────────
const DEFAULT_PARAMS = {
  drift_rate: 0.5,
  sg_actual: 0.65,
  sg_calibrated: 0.80,
  commanded_value: 0,
  actual_value: 85,
};

export default function AbnormalityLab({ onClose }) {
  const { plantId, role } = useStore();
  const navigate = useNavigate();

  // All state hooks must be declared before any conditional return
  const [activeTab, setActiveTab] = useState('scenarios');
  const [sensors, setSensors] = useState(FALLBACK_SENSORS);
  const [sensor, setSensor] = useState('LT-5100');
  const [failureType, setFailureType] = useState('calibration_drift');
  const [params, setParams] = useState(DEFAULT_PARAMS);
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [expandedTour, setExpandedTour] = useState(null);
  const [stepsCompleted, setStepsCompleted] = useState({});
  const [pos, setPos] = useState(null);
  const dragRef = useRef({ active: false, startX: 0, startY: 0, baseX: 0, baseY: 0 });
  const panelRef = useRef(null);

  useEffect(() => {
    fetch('/api/model/signals')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        const ids = (data?.signals || []).map((s) => s.tag || s.id).filter(Boolean);
        if (ids.length) {
          setSensors(ids);
          setSensor((prev) => (ids.includes(prev) ? prev : ids[0]));
        }
      })
      .catch(() => {});
  }, []);

  // ── Access guard ─────────────────────────────────────────────────────────
  if (!['Engineer', 'Manager'].includes(role)) {
    return (
      <div style={{
        position: 'fixed', right: 16, bottom: 44, width: 320, zIndex: 60,
        background: '#14171c', border: '1px solid #2c333d', borderRadius: 6,
        boxShadow: '0 10px 30px rgba(0,0,0,0.5)', color: '#e6e8ec',
        fontFamily: 'Geist, ui-monospace, monospace', padding: 16,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <span style={{ fontSize: 12, fontWeight: 700 }}>Simulation Lab</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#7f8794', cursor: 'pointer', fontSize: 14 }}>✕</button>
        </div>
        <p style={{ fontSize: 11, color: '#ff7a7a', lineHeight: 1.5, margin: 0 }}>
          Simulation Lab requires <strong>Engineer</strong> or <strong>Manager</strong> role.
          Log out and log in as Engineer to use training scenarios.
        </p>
      </div>
    );
  }

  // ── API helpers ──────────────────────────────────────────────────────────
  const post = async (path, body, label) => {
    setBusy(true);
    setStatus(null);
    try {
      const res = await apiFetch(path, {
        method: 'POST',
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setStatus({ ok: true, text: label + ' — runtime updating from simulator stream' });
      return true;
    } catch (err) {
      setStatus({ ok: false, text: label + ' failed: ' + err.message });
      return false;
    } finally {
      setBusy(false);
    }
  };

  const injectMultiple = async (injections, label) => {
    setBusy(true);
    setStatus(null);
    try {
      for (const inj of injections) {
        const res = await apiFetch('/api/sim/inject', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ plant_id: plantId, ...inj }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status} on ${inj.sensor_id}`);
      }
      setStatus({ ok: true, text: label + ' — runtime updating from simulator stream' });
      return true;
    } catch (err) {
      setStatus({ ok: false, text: label + ' failed: ' + err.message });
      return false;
    } finally {
      setBusy(false);
    }
  };

  // ── Scenario actions ─────────────────────────────────────────────────────
  const handleScenario = async (s) => {
    if (s.type === 'file') {
      const loaded = await post(
        `/api/scenario/load?scenario_path=${encodeURIComponent(s.file)}&plant_id=${plantId}`,
        null,
        s.label,
      );
      if (loaded && s.activateImmediately) {
        return post(
          `/api/simulation/start-abnormal-situation?plant_id=${plantId}`,
          null,
          `${s.label} active abnormal path`,
        );
      }
      return loaded;
    }
    return injectMultiple(s.injections, s.label);
  };

  // ── Inject tab actions ───────────────────────────────────────────────────
  const handleInject = () => {
    const ft = FAILURE_TYPES.find((f) => f.type === failureType);
    const body = { plant_id: plantId, sensor_id: sensor, failure_type: failureType };
    if (ft?.params.includes('drift_rate')) body.drift_rate = params.drift_rate;
    if (ft?.params.includes('sg_actual')) body.sg_actual = params.sg_actual;
    if (ft?.params.includes('sg_calibrated')) body.sg_calibrated = params.sg_calibrated;
    if (ft?.params.includes('commanded_value')) body.commanded_value = params.commanded_value;
    if (ft?.params.includes('actual_value')) body.actual_value = params.actual_value;
    return post('/api/sim/inject', body, `${ft?.label} on ${sensor}`);
  };

  const handleClear = () =>
    post(`/api/sim/clear?plant_id=${plantId}`, null, 'Restored normal operation');

  // ── System control actions ───────────────────────────────────────────────
  const handleStartAbnormal = () =>
    post(`/api/simulation/start-abnormal-situation?plant_id=${plantId}`, null, 'Abnormal situation started');

  const handleAdvance = () =>
    post(`/api/simulation/advance?plant_id=${plantId}`, null, 'Scenario phase advanced');

  const handleFullReset = () =>
    post(`/api/demo/reset?plant_id=${plantId}`, null, 'Full reset complete');

  // ── Tour step executor ───────────────────────────────────────────────────
  const executeTourStep = async (tourId, stepIdx, step) => {
    let ok = false;
    if (step.type === 'inject') {
      ok = await post('/api/sim/inject', { plant_id: plantId, ...step.payload }, step.label);
    } else if (step.type === 'multi-inject') {
      ok = await injectMultiple(step.injections, step.label);
    } else if (step.type === 'scenario') {
      ok = await post(
        `/api/scenario/load?scenario_path=${encodeURIComponent(step.file)}&plant_id=${plantId}`,
        null,
        step.label,
      );
    } else if (step.type === 'fullReset') {
      ok = await post(`/api/demo/reset?plant_id=${plantId}`, null, step.label);
    } else if (step.type === 'nav') {
      navigate(step.path);
      ok = true;
    }
    if (ok) {
      setStepsCompleted((prev) => {
        const existing = new Set(prev[tourId] || []);
        existing.add(stepIdx);
        return { ...prev, [tourId]: existing };
      });
    }
  };

  // ── Drag by header ───────────────────────────────────────────────────────
  const onPointerDown = (e) => {
    if (e.button !== 0) return;
    const rect = panelRef.current.getBoundingClientRect();
    dragRef.current = {
      active: true,
      startX: e.clientX,
      startY: e.clientY,
      baseX: rect.left,
      baseY: rect.top,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e) => {
    if (!dragRef.current.active) return;
    setPos({
      x: dragRef.current.baseX + (e.clientX - dragRef.current.startX),
      y: dragRef.current.baseY + (e.clientY - dragRef.current.startY),
    });
  };
  const onPointerUp = () => { dragRef.current.active = false; };

  // ── Inline styles ────────────────────────────────────────────────────────
  const anchored = pos == null;
  const ft = FAILURE_TYPES.find((f) => f.type === failureType) || FAILURE_TYPES[0];

  const S = {
    panel: {
      position: 'fixed', width: 384, maxHeight: 'calc(100vh - 80px)',
      zIndex: 60, background: '#14171c', border: '1px solid #2c333d',
      borderRadius: 6, boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
      color: '#e6e8ec', fontFamily: 'Geist, ui-monospace, monospace',
      display: 'flex', flexDirection: 'column',
      ...(anchored ? { right: 16, bottom: 44 } : { left: pos.x, top: pos.y }),
    },
    header: {
      display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px',
      background: '#0f1216', borderBottom: '1px solid #2c333d',
      borderTopLeftRadius: 6, borderTopRightRadius: 6,
      cursor: 'grab', userSelect: 'none', flexShrink: 0,
    },
    tabs: {
      display: 'flex', borderBottom: '1px solid #2c333d', flexShrink: 0,
    },
    tab: (active) => ({
      flex: 1, padding: '6px 0', background: 'none', border: 'none',
      borderBottom: active ? '2px solid #5fd0c5' : '2px solid transparent',
      color: active ? '#5fd0c5' : '#7f8794', fontSize: 10, fontWeight: 700,
      letterSpacing: '0.04em', cursor: 'pointer', fontFamily: 'inherit',
    }),
    body: {
      padding: '10px 12px 14px', overflowY: 'auto', flex: 1,
    },
    secLabel: {
      fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
      textTransform: 'uppercase', color: '#7f8794', marginBottom: 4, display: 'block',
    },
    divider: { height: 1, background: '#1e2530', margin: '12px 0' },
    scenarioBtn: (accent) => ({
      width: '100%', textAlign: 'left', padding: '8px 10px', marginTop: 6,
      background: '#1c212a', border: `1px solid ${accent}44`,
      borderLeft: `3px solid ${accent}`, borderRadius: 4,
      color: '#e6e8ec', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
      display: 'block',
    }),
    roleTag: (color) => ({
      display: 'inline-block', fontSize: 9, fontWeight: 700, padding: '1px 5px',
      background: color + '22', color, border: `1px solid ${color}44`,
      borderRadius: 3, marginRight: 6,
    }),
    demonstratesLine: { display: 'block', fontSize: 10, color: '#5fd0c5', marginTop: 3, lineHeight: 1.3 },
    hintLine: { display: 'block', fontSize: 10, color: '#7f8794', marginTop: 2 },
    greenBtn: {
      width: '100%', textAlign: 'center', padding: '7px 10px', marginTop: 10,
      background: '#15201a', border: '1px solid #2f6b4f', borderRadius: 4,
      color: '#7fe0a8', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
      display: 'block',
    },
    redBtn: {
      width: '100%', textAlign: 'center', padding: '7px 10px', marginTop: 6,
      background: '#201515', border: '1px solid #6b2f2f', borderRadius: 4,
      color: '#ff7a7a', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
      display: 'block',
    },
    controlBtn: (accent) => ({
      width: '100%', textAlign: 'left', padding: '7px 10px', marginTop: 8,
      background: '#1c212a', border: `1px solid ${accent}55`, borderLeft: `3px solid ${accent}`,
      borderRadius: 4, color: '#e6e8ec', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
    }),
    select: {
      width: '100%', padding: '6px 8px', background: '#1c212a',
      border: '1px solid #2c333d', borderRadius: 4, color: '#e6e8ec',
      fontSize: 12, fontFamily: 'inherit', marginTop: 4,
    },
    inputNum: {
      width: '100%', padding: '5px 8px', background: '#1c212a',
      border: '1px solid #2c333d', borderRadius: 4, color: '#e6e8ec',
      fontSize: 11, fontFamily: 'inherit', marginTop: 4, boxSizing: 'border-box',
    },
    paramLabel: { fontSize: 10, color: '#7f8794', marginTop: 8, display: 'block' },
    injectBtn: {
      width: '100%', textAlign: 'center', padding: '7px 10px', marginTop: 12,
      background: '#1c212a', border: `1px solid ${ft.color}66`,
      borderRadius: 4, color: ft.color, fontSize: 12, fontWeight: 700,
      cursor: 'pointer', fontFamily: 'inherit',
    },
  };

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div ref={panelRef} style={S.panel} role="dialog" aria-label="Simulation Lab">
      {/* ── Header / drag handle ── */}
      <div
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        style={S.header}
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#5fd0c5" strokeWidth="2">
          <path d="M9 3h6M9 3v6l-5 9a1 1 0 00.9 1.5h14.2A1 1 0 0020 18l-5-9V3" />
        </svg>
        <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.04em' }}>Simulation Lab</span>
        <span style={{
          fontSize: 9, fontWeight: 700, color: '#0f1216', background: '#5fd0c5',
          borderRadius: 3, padding: '1px 5px', marginLeft: 2, letterSpacing: '0.08em',
        }}>TRAINING</span>
        <span style={{ marginLeft: 'auto', fontSize: 10, color: '#7f8794' }}>
          {String(plantId).toUpperCase()}
        </span>
        <button
          onClick={onClose}
          aria-label="Close Simulation Lab"
          style={{ background: 'none', border: 'none', color: '#7f8794', cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: 0, marginLeft: 6 }}
        >✕</button>
      </div>

      {/* ── Tab strip ── */}
      <div style={S.tabs}>
        {[
          ['scenarios', 'Scenarios'],
          ['tours', 'Demo Tours'],
          ['inject', 'Inject'],
          ['controls', 'Controls'],
        ].map(([id, label]) => (
          <button key={id} style={S.tab(activeTab === id)} onClick={() => setActiveTab(id)}>
            {label}
          </button>
        ))}
      </div>

      {/* ── Tab body ── */}
      <div style={S.body}>

        {/* ════ Scenarios Tab ════ */}
        {activeTab === 'scenarios' && (
          <>
            <span style={S.secLabel}>File-Based Scenarios</span>
            {SCENARIOS.filter((s) => s.type === 'file').map((s) => (
              <button
                key={s.file}
                style={S.scenarioBtn(s.accentColor)}
                disabled={busy}
                onClick={() => handleScenario(s)}
              >
                <span>
                  <span style={S.roleTag(s.roleColor)}>{s.roleLabel}</span>
                  <span style={{ fontWeight: 700 }}>{s.label}</span>
                </span>
                <span style={S.hintLine}>{s.hint}</span>
                <span style={S.demonstratesLine}>→ {s.demonstrates}</span>
              </button>
            ))}

            <div style={S.divider} />
            <span style={S.secLabel}>Compound Scenarios (multi-inject)</span>
            {SCENARIOS.filter((s) => s.type === 'inject').map((s, i) => (
              <button
                key={i}
                style={S.scenarioBtn(s.accentColor)}
                disabled={busy}
                onClick={() => handleScenario(s)}
              >
                <span>
                  <span style={S.roleTag(s.roleColor)}>{s.roleLabel}</span>
                  <span style={{ fontWeight: 700 }}>{s.label}</span>
                </span>
                <span style={S.hintLine}>{s.hint}</span>
                <span style={S.demonstratesLine}>→ {s.demonstrates}</span>
              </button>
            ))}

            <button style={S.greenBtn} disabled={busy} onClick={handleClear}>
              ✓ Restore Normal Operation
            </button>
          </>
        )}

        {/* ════ Demo Tours Tab ════ */}
        {activeTab === 'tours' && (
          <>
            <span style={S.secLabel}>Guided HMI Walkthroughs — click to expand</span>
            {TOURS.map((tour) => {
              const isExpanded = expandedTour === tour.id;
              const done = stepsCompleted[tour.id] || new Set();
              return (
                <div
                  key={tour.id}
                  style={{
                    border: `1px solid ${isExpanded ? tour.color + '66' : '#2c333d'}`,
                    borderRadius: 4, marginTop: 6, overflow: 'hidden',
                  }}
                >
                  {/* Tour header */}
                  <div
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '7px 10px', cursor: 'pointer', background: '#1c212a',
                      userSelect: 'none',
                    }}
                    onClick={() => setExpandedTour(isExpanded ? null : tour.id)}
                  >
                    <div>
                      <span style={{ fontSize: 12, fontWeight: 700 }}>{tour.label}</span>
                      <span style={{ fontSize: 10, color: '#7f8794', marginLeft: 8 }}>{tour.persona}</span>
                    </div>
                    <span style={{ fontSize: 10, color: tour.color }}>{isExpanded ? '▲' : '▼'}</span>
                  </div>

                  {/* Tour steps */}
                  {isExpanded && tour.steps.map((step, si) => {
                    const completed = done.has(si);
                    const isInfo = step.type === 'info';
                    const isNav = step.type === 'nav';
                    return (
                      <div
                        key={si}
                        style={{
                          display: 'flex', alignItems: 'flex-start', gap: 8,
                          padding: '7px 10px', borderTop: '1px solid #1e2530',
                          background: isInfo ? '#161b22' : '#1a1f28',
                          opacity: completed ? 0.65 : 1,
                        }}
                      >
                        {/* Step icon */}
                        <div style={{
                          width: 18, height: 18, borderRadius: '50%', flexShrink: 0,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          marginTop: 1, fontSize: 9, fontWeight: 700,
                          background: completed ? '#2f6b4f33'
                            : isInfo ? '#2c333d'
                            : isNav ? '#0a84ff22'
                            : '#5fd0c522',
                          color: completed ? '#7fe0a8'
                            : isInfo ? '#7f8794'
                            : isNav ? '#0a84ff'
                            : '#5fd0c5',
                          border: completed ? '1px solid #2f6b4f' : 'none',
                        }}>
                          {completed ? '✓' : isInfo ? 'i' : isNav ? '→' : '▶'}
                        </div>

                        {/* Step content */}
                        <div style={{ flex: 1 }}>
                          <p style={{
                            margin: 0, fontSize: 11, lineHeight: 1.4,
                            color: isInfo ? '#7f8794' : '#e6e8ec',
                          }}>
                            {step.label}
                          </p>
                          {!isInfo && (
                            <button
                              disabled={busy}
                              onClick={() => executeTourStep(tour.id, si, step)}
                              style={{
                                marginTop: 5, padding: '3px 8px', background: 'none',
                                border: `1px solid ${isNav ? '#0a84ff66' : '#5fd0c566'}`,
                                borderRadius: 3,
                                color: isNav ? '#0a84ff' : '#5fd0c5',
                                fontSize: 10, cursor: 'pointer', fontFamily: 'inherit',
                              }}
                            >
                              {isNav ? 'Navigate →' : 'Run ▶'}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </>
        )}

        {/* ════ Inject Tab ════ */}
        {activeTab === 'inject' && (
          <>
            <span style={S.secLabel}>Target Sensor</span>
            <select value={sensor} onChange={(e) => setSensor(e.target.value)} style={S.select}>
              {sensors.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>

            <span style={{ ...S.secLabel, marginTop: 12 }}>Failure Type</span>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginTop: 4 }}>
              {FAILURE_TYPES.map((f) => (
                <button
                  key={f.type}
                  onClick={() => setFailureType(f.type)}
                  style={{
                    padding: '6px 8px', background: failureType === f.type ? '#1e2530' : '#1c212a',
                    border: `1px solid ${failureType === f.type ? f.color : f.color + '55'}`,
                    borderLeft: `3px solid ${f.color}`, borderRadius: 4,
                    color: failureType === f.type ? '#e6e8ec' : '#7f8794',
                    fontSize: 11, cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left',
                  }}
                >{f.label}</button>
              ))}
            </div>

            {/* Failure type hint */}
            <p style={{ margin: '8px 0 0', fontSize: 10, color: '#7f8794', lineHeight: 1.4 }}>
              {ft.hint}
            </p>

            {/* Conditional parameter inputs */}
            {ft.params.includes('drift_rate') && (
              <>
                <span style={S.paramLabel}>
                  Drift Rate (units per tick): <strong style={{ color: '#e6e8ec' }}>{params.drift_rate.toFixed(1)}</strong>
                </span>
                <input
                  type="range" min="0.1" max="2.0" step="0.1"
                  value={params.drift_rate}
                  onChange={(e) => setParams((p) => ({ ...p, drift_rate: parseFloat(e.target.value) }))}
                  style={{ width: '100%', marginTop: 4 }}
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: '#5a626e' }}>
                  <span>0.1 slow</span><span>1.0 moderate</span><span>2.0 fast</span>
                </div>
              </>
            )}

            {ft.params.includes('sg_actual') && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 4 }}>
                <div>
                  <span style={S.paramLabel}>SG Actual</span>
                  <input
                    type="number" min="0.1" max="2.0" step="0.01"
                    value={params.sg_actual}
                    onChange={(e) => setParams((p) => ({ ...p, sg_actual: parseFloat(e.target.value) || p.sg_actual }))}
                    style={S.inputNum}
                  />
                </div>
                <div>
                  <span style={S.paramLabel}>SG Calibrated</span>
                  <input
                    type="number" min="0.1" max="2.0" step="0.01"
                    value={params.sg_calibrated}
                    onChange={(e) => setParams((p) => ({ ...p, sg_calibrated: parseFloat(e.target.value) || p.sg_calibrated }))}
                    style={S.inputNum}
                  />
                </div>
              </div>
            )}

            {ft.params.includes('commanded_value') && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 4 }}>
                <div>
                  <span style={S.paramLabel}>Commanded (%)</span>
                  <input
                    type="number" min="0" max="100" step="1"
                    value={params.commanded_value}
                    onChange={(e) => setParams((p) => ({ ...p, commanded_value: parseFloat(e.target.value) ?? p.commanded_value }))}
                    style={S.inputNum}
                  />
                </div>
                <div>
                  <span style={S.paramLabel}>Actual (%)</span>
                  <input
                    type="number" min="0" max="100" step="1"
                    value={params.actual_value}
                    onChange={(e) => setParams((p) => ({ ...p, actual_value: parseFloat(e.target.value) ?? p.actual_value }))}
                    style={S.inputNum}
                  />
                </div>
              </div>
            )}

            <button style={S.injectBtn} disabled={busy} onClick={handleInject}>
              Inject {ft.label} → {sensor}
            </button>
            <button style={S.greenBtn} disabled={busy} onClick={handleClear}>
              ✓ Clear All Failures
            </button>
          </>
        )}

        {/* ════ Controls Tab ════ */}
        {activeTab === 'controls' && (
          <>
            <span style={S.secLabel}>Scenario Lifecycle</span>

            <button
              style={S.controlBtn('#ff8c33')}
              disabled={busy}
              onClick={handleStartAbnormal}
            >
              <span style={{ fontWeight: 700 }}>▶ Start Abnormal Situation</span>
              <span style={{ display: 'block', fontSize: 10, color: '#7f8794', marginTop: 2 }}>
                Activates startup scrutiny mode — elevates monitoring thresholds
              </span>
            </button>

            <button
              style={S.controlBtn('#ffcc00')}
              disabled={busy}
              onClick={handleAdvance}
            >
              <span style={{ fontWeight: 700 }}>↷ Advance Scenario Phase</span>
              <span style={{ display: 'block', fontSize: 10, color: '#7f8794', marginTop: 2 }}>
                Moves the simulator to the next phase in the active scenario
              </span>
            </button>

            <div style={S.divider} />
            <span style={S.secLabel}>Reset Operations</span>

            <button style={S.greenBtn} disabled={busy} onClick={handleClear}>
              ✓ Restore Normal Operation
              <span style={{ display: 'block', fontSize: 10, color: '#7fe0a8aa', marginTop: 2, fontWeight: 400 }}>
                Clears sensor failures and resets the simulator source
              </span>
            </button>

            <button style={S.redBtn} disabled={busy} onClick={handleFullReset}>
              ⚠ Full System Reset
              <span style={{ display: 'block', fontSize: 10, color: '#ff7a7aaa', marginTop: 2 }}>
                Resets Studio compiler state, shift notes, and the simulator
              </span>
            </button>
          </>
        )}

        {/* ── Status feedback ── */}
        {status && (
          <p style={{ marginTop: 10, fontSize: 11, lineHeight: 1.4, color: status.ok ? '#7fe0a8' : '#ff7a7a', margin: '10px 0 0' }}>
            {status.text}
          </p>
        )}

        <p style={{ marginTop: 10, fontSize: 9, color: '#5a626e', lineHeight: 1.4 }}>
          Training source only — drives the simulated provider. ConfidenceOS never writes plant controls.
        </p>
      </div>
    </div>
  );
}
