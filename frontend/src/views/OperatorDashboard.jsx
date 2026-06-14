/**
 * views/OperatorDashboard.jsx — Live HMI Operator View
 *
 * Endpoints (via Zustand store):
 *   WS  /ws/sensors?plant_id=...  — live 1Hz sensor + confidence + mass-balance
 *   POST /api/mode/startup         — toggle startup scrutiny mode
 *   POST /api/mode/startup/acknowledge/:id — clear stale flag
 *   GET  /api/predictions/:plant_id — forecast data (sidebar)
 *
 * Stitch mockup: 2operator dashboard.html
 */

import { useEffect, useMemo } from 'react';
import useStore from '../store';
import SensorCard from '../components/SensorCard';
import MassBalanceChart from '../components/MassBalanceChart';
import HealthTimeline from '../components/HealthTimeline';
import HandoverBrief from '../components/HandoverBrief';
import StartupBanner from '../components/StartupBanner';
import FlagBar from '../components/FlagBar';
import QueryPanel from '../components/QueryPanel';

function healthColor(pct) {
  if (pct >= 80) return 'text-[var(--safe-text)]';
  if (pct >= 50) return 'text-[var(--caution)]';
  if (pct >= 20) return 'text-[var(--warning)]';
  return 'text-[var(--critical)]';
}

function PredictionSidecard({ prediction }) {
  if (!prediction) {
    return (
      <p className="caption-mono text-[var(--text-muted)] p-4">
        Select a sensor to view forecast.
      </p>
    );
  }
  const hasCrit = prediction.time_to_critical_hours != null;
  const hasLow  = prediction.time_to_low_hours != null;
  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="font-data text-[var(--primary)] text-[14px]">{prediction.sensor_id}</span>
        <span className="label-caps text-[var(--text-muted)]">{prediction.model_type || '—'}</span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="stitch-card p-3 text-center">
          <p className="label-caps text-[var(--text-muted)] mb-1">LOW in</p>
          <p className={`text-[24px] font-bold font-data ${hasLow ? 'text-[var(--warning)]' : 'text-[var(--text-dim)]'}`}>
            {hasLow ? `${prediction.time_to_low_hours}h` : '—'}
          </p>
        </div>
        <div className="stitch-card p-3 text-center">
          <p className="label-caps text-[var(--text-muted)] mb-1">CRIT in</p>
          <p className={`text-[24px] font-bold font-data ${hasCrit ? 'text-[var(--critical)]' : 'text-[var(--text-dim)]'}`}>
            {hasCrit ? `${prediction.time_to_critical_hours}h` : '—'}
          </p>
        </div>
      </div>
      <p className="caption-mono text-[var(--text-muted)] leading-relaxed">
        {prediction.recommended_action || prediction.action || 'No action required.'}
      </p>
    </div>
  );
}

export default function OperatorDashboard() {
  const {
    connect,
    connected,
    readings,
    confidence,
    massBalance,
    mode,
    staleFlags,
    averageConfidence,
    chartHistory,
    selectedSensorId,
    selectSensor,
    toggleStartupMode,
    acknowledgeStale,
    predictions,
    fetchPredictions,
    plantId,
    role,
  } = useStore();

  useEffect(() => { connect(); }, [connect]);
  useEffect(() => { fetchPredictions(plantId); }, [fetchPredictions, plantId]);

  const selectedPrediction = predictions?.[selectedSensorId];

  const lastUpdate = useMemo(() => {
    if (!readings.length) return '—';
    return new Date().toLocaleTimeString();
  }, [readings]);

  return (
    <div className="industrial-page flex flex-col overflow-hidden">
      {/* Startup mode banner */}
      {mode?.is_active && (
        <div className="startup-banner">
          <span className="material-symbols-outlined text-[var(--critical)] text-[18px]">warning</span>
          <span className="label-caps text-[var(--critical)] tracking-widest">
            STARTUP MODE ACTIVE — ELEVATED MONITORING REQUIRED
          </span>
        </div>
      )}

      {/* Main 3-column layout */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Center canvas ── */}
        <main className="flex-1 min-w-0 flex flex-col overflow-y-auto scrollbar-thin bg-[var(--bg-base)] p-4 gap-4">

          {/* Plant header */}
          <div className="flex justify-between items-end">
            <div>
              <h1 className="text-[18px] font-semibold text-[var(--text)]">
                {plantId?.replace('-', ' ').toUpperCase()} — Operator Dashboard
              </h1>
              <p className="label-caps text-[var(--text-muted)] mt-1">Live Data · 1 Hz</p>
            </div>
            <div className="flex items-center gap-4">
              <span className="caption-mono text-[var(--text-dim)]">
                Last Update: <span className="text-[var(--primary)]">{lastUpdate}</span>
              </span>
              <span className={`industrial-badge ${connected ? 'text-[var(--safe-text)] border-[var(--safe-text)]' : 'text-[var(--critical)] border-[var(--critical)]'}`}>
                {connected ? 'LIVE' : 'OFFLINE'}
              </span>
              <span className={`font-data text-[32px] font-bold ${healthColor(averageConfidence)}`}>
                {averageConfidence}%
              </span>
            </div>
          </div>

          {/* Startup manager */}
          <StartupBanner
            isActive={mode?.is_active ?? false}
            onToggle={toggleStartupMode}
            staleFlags={staleFlags}
            onAcknowledge={acknowledgeStale}
          />

          {/* Sensor grid */}
          <div className="label-caps text-[var(--text-muted)]">Critical Sensors</div>
          <div className="grid grid-cols-2 xl:grid-cols-3 gap-1 bg-[var(--border)] border border-[var(--border)]">
            {readings.map((reading) => {
              const conf = confidence.find((c) => c.sensor_id === reading.sensor_id);
              return (
                <SensorCard
                  key={reading.sensor_id}
                  reading={reading}
                  confidence={conf}
                  isSelected={selectedSensorId === reading.sensor_id}
                  onSelect={selectSensor}
                />
              );
            })}
          </div>

          {/* Mass-balance chart */}
          <div className="h-[380px]">
            <MassBalanceChart chartHistory={chartHistory} massBalance={massBalance} flags={massBalance?.flags} />
          </div>

          {/* Flag bar */}
          <FlagBar confidence={confidence} massBalance={massBalance} staleFlags={staleFlags} />
        </main>

        {/* ── Right sidebar — 3-tab panel ── */}
        <aside className="w-80 xl:w-96 bg-[var(--bg-surface)] border-l border-[var(--border)] flex flex-col overflow-hidden flex-shrink-0">
          {/* Tab header */}
          <div className="flex border-b border-[var(--border)] gap-1 p-1">
            {[
              { icon: 'psychology', label: 'Assistant' },
              { icon: 'hub',        label: 'Graph' },
              { icon: 'flag',       label: 'Flags' },
            ].map(({ icon, label }, i) => (
              <button key={label} className={`flex-1 py-2 label-caps flex flex-col items-center gap-1 rounded transition-all
                ${i === 0 ? 'bg-[var(--bg-elevated)] text-[var(--primary)]' : 'text-[var(--text-muted)] hover:bg-[var(--bg-elevated)]/50'}`}>
                <span className="material-symbols-outlined text-[20px]">{icon}</span>
                {label}
              </button>
            ))}
          </div>

          {/* Query assistant */}
          <div className="h-[480px] border-b border-[var(--border)]">
            <QueryPanel />
          </div>

          {/* Predictive forecast */}
          <div className="border-b border-[var(--border)]">
            <div className="stitch-card-header">
              <span className="text-[14px] font-semibold text-[var(--text)]">Predictive Forecast</span>
            </div>
            <PredictionSidecard prediction={selectedPrediction} />
          </div>

          {/* Engineer deep-dive (role-gated) */}
          {role === 'Engineer' && selectedSensorId && (
            <div className="flex-1 overflow-y-auto scrollbar-thin border-b border-[var(--border)]">
              <div className="stitch-card-header">
                <span className="text-[14px] font-semibold text-[var(--text)]">Engineer Deep-Dive</span>
              </div>
              <EngineerMini sensorId={selectedSensorId} confidence={confidence} plantId={plantId} />
            </div>
          )}

          {/* Health timeline + Handover */}
          <div className="flex-1 overflow-y-auto scrollbar-thin">
            <HealthTimeline sensorId={selectedSensorId} />
            <HandoverBrief />
          </div>
        </aside>
      </div>
    </div>
  );
}

function EngineerMini({ sensorId, confidence, plantId }) {
  const selected = confidence.find((c) => c.sensor_id === sensorId);
  const subs = selected?.sub_scores || {};

  return (
    <div className="p-4 space-y-3">
      <div className="grid grid-cols-4 gap-1">
        {[
          { key: 'CAL', val: subs.calibration },
          { key: 'STB', val: subs.stability },
          { key: 'XSN', val: subs.cross_sensor },
          { key: 'PHY', val: subs.physical_plausibility },
        ].map(({ key, val }) => {
          const pct = val != null ? Math.round(val * 100) : null;
          const col = pct == null ? 'text-[var(--text-dim)]'
            : pct >= 80 ? 'text-[var(--safe-text)]'
            : pct >= 50 ? 'text-[var(--caution)]'
            : 'text-[var(--critical)]';
          return (
            <div key={key} className="stitch-card p-2 text-center">
              <p className="label-caps text-[var(--text-muted)]">{key}</p>
              <p className={`text-[16px] font-bold font-data mt-1 ${col}`}>
                {pct != null ? `${pct}%` : '—'}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
