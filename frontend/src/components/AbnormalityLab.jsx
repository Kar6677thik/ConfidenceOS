/**
 * AbnormalityLab.jsx — Demo cheat panel for ConfidenceOS.
 *
 * A floating, draggable "demo operator console" that fires prebuilt scenarios
 * and individual sensor failures against the LIVE simulator (the demo data
 * source) so the whole product reacts live during a presentation.
 *
 * These actions configure the simulated source — they are NOT plant-control
 * writes. The read-only-to-plant contract is unchanged.
 *
 * Endpoints:
 *   POST /api/scenario/load?scenario_path=...&plant_id=...  (prebuilt scenarios)
 *   POST /api/sim/inject   { plant_id, sensor_id, failure_type, ... }
 *   POST /api/sim/clear?plant_id=...
 */

import { useEffect, useRef, useState } from 'react';
import useStore from '../store';

const FALLBACK_SENSORS = ['LT-5100', 'FI-2010', 'FO-2020', 'PT-3100', 'TT-4100', 'ZT-6100'];

const SCENARIOS = [
  { file: 'scenario.json',   label: 'Texas City Overfill',   hint: 'frozen level + decoupled feed valve' },
  { file: 'scenario_b.json', label: 'North Sea Cold Restart', hint: 'drifting temperature & pressure' },
  { file: 'scenario_c.json', label: 'Water Treatment Valve',  hint: 'valve command-state decoupling' },
];

// Failure types, colour-coded by how severe they read in the demo.
const FAILURES = [
  { type: 'calibration_drift',       label: 'Calibration Drift', color: '#ffcc00' },
  { type: 'stuck_reading',           label: 'Stuck / Frozen',    color: '#ff8c33' },
  { type: 'sg_mismatch',             label: 'SG Mismatch',       color: '#ff5252' },
  { type: 'command_state_decoupling', label: 'Valve Decouple',   color: 'rgb(150,100,236)' },
];

export default function AbnormalityLab({ onClose }) {
  const { plantId } = useStore();
  const [sensors, setSensors] = useState(FALLBACK_SENSORS);
  const [sensor, setSensor] = useState('LT-5100');
  const [status, setStatus] = useState(null);   // { ok, text }
  const [busy, setBusy] = useState(false);
  const [pos, setPos] = useState(null);          // {x,y} once dragged; null = anchored bottom-right
  const dragRef = useRef({ active: false, startX: 0, startY: 0, baseX: 0, baseY: 0 });
  const panelRef = useRef(null);

  // Populate the sensor list from the active model (fallback to the defaults).
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
      .catch(() => { /* keep fallback list */ });
  }, []);

  const post = async (url, label) => {
    setBusy(true);
    setStatus(null);
    try {
      const res = await fetch(url.path, {
        method: 'POST',
        headers: url.body ? { 'Content-Type': 'application/json' } : undefined,
        body: url.body ? JSON.stringify(url.body) : undefined,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await res.json().catch(() => null);
      setStatus({ ok: true, text: `${label} — watch Runtime update live` });
    } catch (err) {
      setStatus({ ok: false, text: `${label} failed: ${err.message}` });
    } finally {
      setBusy(false);
    }
  };

  const loadScenario = (file, label) =>
    post({ path: `/api/scenario/load?scenario_path=${encodeURIComponent(file)}&plant_id=${plantId}` }, label);

  const injectFailure = (failure_type, label) =>
    post({ path: '/api/sim/inject', body: { plant_id: plantId, sensor_id: sensor, failure_type } }, `${label} on ${sensor}`);

  const restore = () =>
    post({ path: `/api/sim/clear?plant_id=${plantId}` }, 'Restored normal operation');

  // ── Drag by header (pointer capture, 4px dead-zone) ──────────────────────
  const onPointerDown = (e) => {
    if (e.button !== 0) return;
    const rect = panelRef.current.getBoundingClientRect();
    dragRef.current = { active: true, startX: e.clientX, startY: e.clientY, baseX: rect.left, baseY: rect.top };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e) => {
    if (!dragRef.current.active) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    setPos({ x: dragRef.current.baseX + dx, y: dragRef.current.baseY + dy });
  };
  const onPointerUp = () => { dragRef.current.active = false; };

  const anchored = pos == null;
  const panelStyle = {
    position: 'fixed',
    width: 312,
    zIndex: 60,
    background: '#14171c',
    border: '1px solid #2c333d',
    borderRadius: 6,
    boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
    color: '#e6e8ec',
    fontFamily: 'Geist, ui-monospace, monospace',
    ...(anchored ? { right: 16, bottom: 44 } : { left: pos.x, top: pos.y }),
  };

  const sectionLabel = { fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#7f8794' };
  const btn = {
    width: '100%', textAlign: 'left', padding: '7px 10px', marginTop: 6,
    background: '#1c212a', border: '1px solid #2c333d', borderRadius: 4,
    color: '#e6e8ec', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
  };

  return (
    <div ref={panelRef} style={panelStyle} role="dialog" aria-label="Abnormality Lab">
      {/* Header / drag handle */}
      <div
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px',
          background: '#0f1216', borderBottom: '1px solid #2c333d',
          borderTopLeftRadius: 6, borderTopRightRadius: 6, cursor: 'grab', userSelect: 'none',
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#5fd0c5" strokeWidth="2">
          <path d="M9 3h6M9 3v6l-5 9a1 1 0 00.9 1.5h14.2A1 1 0 0020 18l-5-9V3" />
        </svg>
        <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.04em' }}>Abnormality Lab</span>
        <span style={{
          fontSize: 9, fontWeight: 700, letterSpacing: '0.08em', color: '#0f1216',
          background: '#5fd0c5', borderRadius: 3, padding: '1px 5px', marginLeft: 2,
        }}>DEMO</span>
        <span style={{ marginLeft: 'auto', fontSize: 10, color: '#7f8794' }}>{String(plantId).toUpperCase()}</span>
        <button
          onClick={onClose}
          aria-label="Close Abnormality Lab"
          style={{ background: 'none', border: 'none', color: '#7f8794', cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: 0 }}
        >✕</button>
      </div>

      <div style={{ padding: '10px 12px 12px' }}>
        {/* Prebuilt scenarios */}
        <p style={sectionLabel}>Prebuilt Scenarios</p>
        {SCENARIOS.map((s) => (
          <button key={s.file} style={btn} disabled={busy} onClick={() => loadScenario(s.file, s.label)}>
            <span style={{ fontWeight: 600 }}>{s.label}</span>
            <span style={{ display: 'block', fontSize: 10, color: '#7f8794', marginTop: 1 }}>{s.hint}</span>
          </button>
        ))}

        {/* Individual sensor failure */}
        <p style={{ ...sectionLabel, marginTop: 14 }}>Inject Sensor Failure</p>
        <select
          value={sensor}
          onChange={(e) => setSensor(e.target.value)}
          style={{
            width: '100%', marginTop: 6, padding: '6px 8px', background: '#1c212a',
            border: '1px solid #2c333d', borderRadius: 4, color: '#e6e8ec', fontSize: 12, fontFamily: 'inherit',
          }}
        >
          {sensors.map((id) => <option key={id} value={id}>{id}</option>)}
        </select>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginTop: 6 }}>
          {FAILURES.map((f) => (
            <button
              key={f.type}
              disabled={busy}
              onClick={() => injectFailure(f.type, f.label)}
              style={{
                padding: '6px 8px', background: '#1c212a', border: `1px solid ${f.color}66`,
                borderLeft: `3px solid ${f.color}`, borderRadius: 4, color: '#e6e8ec',
                fontSize: 11, cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left',
              }}
            >{f.label}</button>
          ))}
        </div>

        {/* Restore */}
        <button
          onClick={restore}
          disabled={busy}
          style={{
            ...btn, marginTop: 14, textAlign: 'center', fontWeight: 700,
            borderColor: '#2f6b4f', color: '#7fe0a8', background: '#15201a',
          }}
        >Restore Normal Operation</button>

        {/* Status */}
        {status && (
          <p style={{
            marginTop: 10, fontSize: 11, lineHeight: 1.4,
            color: status.ok ? '#7fe0a8' : '#ff7a7a',
          }}>{status.text}</p>
        )}
        <p style={{ marginTop: 10, fontSize: 9, color: '#5a626e', lineHeight: 1.4 }}>
          Demo only — drives the simulated source. ConfidenceOS never writes plant controls.
        </p>
      </div>
    </div>
  );
}
