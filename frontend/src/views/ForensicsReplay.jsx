/**
 * views/ForensicsReplay.jsx — Incident Forensics / Replay Terminal
 *
 * Endpoints:
 *   GET /api/forensics/presets             — list available replay presets
 *   GET /api/forensics/presets/:preset_id  — load a preset (texas-city default)
 *   GET /api/forensics/:plant_id           — live forensics for a plant
 *
 * Stitch mockup: 5incident-forencies.html
 */

import { useEffect, useState } from 'react';
import SensorCard from '../components/SensorCard';
import MassBalanceChart from '../components/MassBalanceChart';

const DEFAULT_PRESET = 'texas-city';

export default function ForensicsReplay() {
  const [presets, setPresets]   = useState([]);
  const [activePreset, setActivePreset] = useState(DEFAULT_PRESET);
  const [data, setData]         = useState(null);
  const [index, setIndex]       = useState(0);
  const [playing, setPlaying]   = useState(false);
  const [speed, setSpeed]       = useState(1);
  const [viewMode, setViewMode] = useState('confidenceos'); // 'confidenceos' | 'traditional'

  // Load preset list
  useEffect(() => {
    fetch('/api/forensics/presets')
      .then((r) => r.json())
      .then((d) => setPresets(d.presets || []))
      .catch(() => {});
  }, []);

  // Load selected preset
  useEffect(() => {
    fetch(`/api/forensics/presets/${activePreset}`)
      .then((r) => r.json())
      .then((d) => { setData(d); setIndex(0); setPlaying(false); })
      .catch(() => {});
  }, [activePreset]);

  // Playback timer
  useEffect(() => {
    if (!playing || !data?.timeline?.length) return undefined;
    const intervalMs = Math.max(100, 650 / speed);
    const timer = setInterval(() => {
      setIndex((prev) => {
        if (prev + 1 >= data.timeline.length) { setPlaying(false); return prev; }
        return prev + 1;
      });
    }, intervalMs);
    return () => clearInterval(timer);
  }, [playing, data, speed]);

  const frame       = data?.timeline?.[index];
  const totalFrames = data?.timeline?.length || 1;
  const progress    = ((index) / Math.max(1, totalFrames - 1)) * 100;

  const readings  = frame
    ? Object.entries(frame.readings).map(([sid, v]) => ({ sensor_id: sid, ...v }))
    : [];
  const confidence = frame
    ? Object.entries(frame.confidence).map(([sid, v]) => ({ sensor_id: sid, reasons: [], sub_scores: {}, ...v }))
    : [];
  const chartHistory = (data?.timeline || []).slice(0, index + 1).map((pt) => ({
    time: `${pt.minute}m`,
    implied: pt.mass_balance?.implied_level,
    measured: pt.mass_balance?.measured_level,
    discrepancy: pt.mass_balance?.discrepancy,
  }));

  return (
    <div className="industrial-page flex flex-col overflow-hidden">

      {/* ── Replay control bar ── */}
      <div className="flex-shrink-0 bg-[var(--bg-surface)] border-b border-[var(--warning)] px-5 py-3 flex items-center gap-5">
        {/* Mode badge */}
        <span className="industrial-badge text-[var(--warning)] border-[var(--warning)]">
          ▶ Replay
        </span>

        {/* Preset selector */}
        <select
          value={activePreset}
          onChange={(e) => setActivePreset(e.target.value)}
          className="industrial-select w-48"
        >
          {presets.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
          {presets.length === 0 && (
            <option value={DEFAULT_PRESET}>Texas City — 2005</option>
          )}
        </select>

        {/* Play / Pause */}
        <button onClick={() => setPlaying((v) => !v)} className="industrial-control text-[var(--text)] px-4">
          {playing ? '⏸ Pause' : '▶ Play'}
        </button>

        {/* Timeline scrubber */}
        <div className="flex-1 min-w-0">
          <div className="flex justify-between caption-mono text-[10px] text-[var(--text-muted)] mb-1">
            <span>MAR 23, 2005 — 00:00</span>
            <span className="text-[var(--primary)]">T+{frame?.minute ?? 0}m</span>
            <span>MAR 23, 2005 — 12:00</span>
          </div>
          <div className="relative">
            <div className="h-2 bg-[var(--bg-elevated)] border border-[var(--border)] rounded-full overflow-hidden">
              <div className="h-full bg-[var(--primary-glow)] transition-all"
                style={{ width: `${progress}%` }} />
            </div>
            <input
              type="range" min="0" max={Math.max(0, totalFrames - 1)} value={index}
              onChange={(e) => { setIndex(Number(e.target.value)); setPlaying(false); }}
              className="absolute inset-0 w-full opacity-0 cursor-pointer"
            />
          </div>
        </div>

        {/* Speed selector */}
        <div className="flex border border-[var(--border)] rounded overflow-hidden">
          {[1, 5, 10, 30].map((s) => (
            <button key={s} onClick={() => setSpeed(s)}
              className={`px-3 py-1 caption-mono border-r border-[var(--border)] last:border-r-0 transition-colors
                ${speed === s ? 'bg-[var(--bg-elevated)] text-[var(--primary)]' : 'text-[var(--text-muted)]'}`}>
              {s}×
            </button>
          ))}
        </div>

        {/* Exit */}
        <button onClick={() => { setPlaying(false); setIndex(0); }} className="industrial-control text-[var(--text-muted)]">
          ✕ Reset
        </button>
      </div>

      {/* ── Main body ── */}
      <div className="flex-1 flex overflow-hidden">

        {/* Main canvas */}
        <main className="flex-1 min-w-0 overflow-y-auto scrollbar-thin bg-[var(--bg-base)] p-1">
          {/* Sensor grid */}
          <div className="stitch-card-header px-4 py-3 bg-[var(--bg-surface)] border-b border-[var(--warning)]">
            <span className="text-[18px] font-semibold text-[var(--text)]">
              Unit 15 ISOM Replay {frame ? `/ T+${frame.minute}m` : ''}
            </span>
            <div className="flex gap-1 border border-[var(--border)]">
              <button onClick={() => setViewMode('confidenceos')}
                className={`px-3 py-1 label-caps transition-colors
                  ${viewMode === 'confidenceos' ? 'text-[var(--primary)] bg-[var(--bg-elevated)]' : 'text-[var(--text-muted)]'}`}>
                ConfidenceOS
              </button>
              <button onClick={() => setViewMode('traditional')}
                className={`px-3 py-1 label-caps transition-colors
                  ${viewMode === 'traditional' ? 'text-[var(--primary)] bg-[var(--bg-elevated)]' : 'text-[var(--text-muted)]'}`}>
                Traditional HMI
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-1 bg-[var(--border)] border border-[var(--border)]">
            {readings.map((reading) => {
              const conf = confidence.find((c) => c.sensor_id === reading.sensor_id);
              if (viewMode === 'traditional') {
                return (
                  <div key={reading.sensor_id} className="stitch-card p-5 h-[200px] flex flex-col justify-between">
                    <p className="font-data text-[var(--text-muted)]">{reading.sensor_id}</p>
                    <p className="text-[42px] font-bold text-[var(--text)] font-data">
                      {reading.value}
                      <span className="text-[14px] text-[var(--text-muted)] ml-1">{reading.unit}</span>
                    </p>
                    <p className="label-caps text-[var(--text-muted)]">No diagnostic context</p>
                  </div>
                );
              }
              return <SensorCard key={reading.sensor_id} reading={reading} confidence={conf} />;
            })}
          </div>

          {/* Mass balance replay chart */}
          <div className="h-[260px] mt-1">
            <MassBalanceChart chartHistory={chartHistory} massBalance={frame?.mass_balance} flags={frame?.mass_balance?.flags} />
          </div>
        </main>

        {/* ── Right sidebar — annotations + counterfactual ── */}
        <aside className="w-96 bg-[var(--bg-surface)] border-l border-[var(--border)] flex flex-col overflow-hidden">
          <div className="stitch-card-header px-4 py-3 border-b border-[var(--border)]">
            <span className="text-[14px] font-semibold text-[var(--text)]">Counterfactual Analysis</span>
          </div>
          <div className="flex-1 overflow-y-auto scrollbar-thin p-4 space-y-4">
            {/* AI root cause */}
            <div className="stitch-card p-4 border-[var(--safe-text)]/30">
              <p className="label-caps text-[var(--text)] mb-2">AI Root Cause Projection</p>
              <p className="caption-mono text-[var(--text-muted)] leading-relaxed">
                {viewMode === 'confidenceos'
                  ? 'Mass-balance divergence detected at T+45m. Level transmitter LT-5100 shows growing calibration drift. ConfidenceOS flags: physical plausibility score < 0.4.'
                  : 'Traditional HMI shows no alarm. Raw values appear within normal range. Silent failure scenario in progress.'}
              </p>
            </div>

            {/* Replay annotations */}
            <div>
              <p className="label-caps text-[var(--text-muted)] mb-3">Replay Annotations</p>
              <div className="space-y-3">
                {(data?.annotations || []).map((note) => {
                  const isPast = frame && note.minute <= frame.minute;
                  return (
                    <div key={note.minute}
                      className={`border-l-2 pl-3 ${isPast ? 'border-[var(--warning)]' : 'border-[var(--border)]'}`}>
                      <p className={`caption-mono font-bold ${isPast ? 'text-[var(--warning)]' : 'text-[var(--text-muted)]'}`}>
                        T+{note.minute}m — {note.title}
                      </p>
                      <p className={`caption-mono mt-1 leading-relaxed ${isPast ? 'text-[var(--text)]' : 'text-[var(--text-muted)]'}`}>
                        {note.body}
                      </p>
                    </div>
                  );
                })}
                {(!data?.annotations || data.annotations.length === 0) && (
                  <p className="caption-mono text-[var(--text-muted)]">Annotations will appear as the replay progresses.</p>
                )}
              </div>
            </div>

            {/* Available presets */}
            {presets.length > 0 && (
              <div>
                <p className="label-caps text-[var(--text-muted)] mb-2">Available Presets</p>
                {presets.map((p) => (
                  <button key={p.id} onClick={() => setActivePreset(p.id)}
                    className={`w-full text-left caption-mono py-2 px-3 border-b border-[var(--border-subtle)] transition-colors
                      ${activePreset === p.id ? 'text-[var(--primary)] bg-[var(--bg-elevated)]' : 'text-[var(--text-muted)] hover:bg-[var(--bg-elevated)]'}`}>
                    {p.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
