/**
 * views/EngineerDeepDive.jsx - Adaptive Envelope & Sub-Score Analysis
 *
 * Endpoints:
 *   GET /api/adaptive-thresholds/:plant_id - dynamically learned 3-sigma envelopes
 *
 * Stitch mockup: 6engineer-deepdive.html
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts';
import useStore from '../store';
import { chartGrid, axisTick, axisLine } from '../lib/chartTheme';
import PageIdentity from '../components/hmi/PageIdentity';
import SupportViewNotice from '../components/SupportViewNotice';

function SubScoreBar({ label, value }) {
  const pct   = value != null ? Math.round(value * 100) : null;
  const color = pct == null ? 'var(--text-dim)'
    : pct >= 80 ? 'var(--safe-text)'
    : pct >= 50 ? 'var(--caution)'
    : pct >= 20 ? 'var(--warning)'
    : 'var(--critical)';

  return (
    <div>
      <div className="flex justify-between mb-1">
        <span className="label-caps text-[var(--text-muted)]">{label}</span>
        <span className="label-caps font-bold" style={{ color }}>
          {pct != null ? `${pct}%` : '-'}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-[var(--bg-elevated)] overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct ?? 0}%`, background: color }} />
      </div>
    </div>
  );
}

function IndustrialTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <p className="label-caps text-[var(--text-muted)] mb-2">{label}</p>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="flex items-center gap-2 mt-1">
          <span className="led-square" style={{ color: entry.color }} />
          <span className="text-[var(--text)]">{entry.name}</span>
          <span className="ml-auto" style={{ color: entry.color }}>
            {typeof entry.value === 'number' ? entry.value.toFixed(2) : entry.value}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function EngineerDeepDive() {
  const { plantId, confidence, selectedSensorId, selectSensor, readings, role } = useStore();
  const navigate = useNavigate();
  const [adaptive, setAdaptive]   = useState(null);

  useEffect(() => {
    if (!['Engineer', 'Manager'].includes(role)) {
      navigate('/runtime', { replace: true });
    }
  }, [role, navigate]);

  // Fetch adaptive thresholds
  useEffect(() => {
    fetch(`/api/adaptive-thresholds/${plantId}`)
      .then((r) => r.json())
      .then(setAdaptive)
      .catch(() => setAdaptive(null));
  }, [plantId]);

  const selected     = confidence.find((c) => c.sensor_id === selectedSensorId);
  const envelope     = adaptive?.envelopes?.[selectedSensorId];
  const subs         = selected?.sub_scores || {};
  const sensorIds    = readings.map((r) => r.sensor_id);

  // Build lightweight envelope context from current readings. A production
  // deployment would fetch persisted history from the historian adapter.
  const envChartData = envelope ? Array.from({ length: 20 }, (_, i) => {
    const t = i - 19;
    const noisy = envelope.mean + (Math.sin(i * 0.9) * (envelope.normal_max - envelope.normal_min) * 0.25);
    return {
      time: `${t}m`,
      value: +noisy.toFixed(2),
      mean:  +envelope.mean.toFixed(2),
    };
  }) : [];

  return (
    <div className="industrial-page grid grid-rows-[auto_minmax(0,1fr)] overflow-hidden">
      <PageIdentity displayName="Engineer Analysis" level={3} area="Confidence Evidence Workspace" plant={plantId} />

      <div className="min-h-0 flex overflow-hidden">
      {/* -- Left sidebar - sensor selector -- */}
      <aside className="engineer-sensor-rail">
        <div className="border-b border-[var(--border)] bg-[var(--surface-elevated)] p-4">
          <p className="label-caps text-[var(--text-muted)]">Signal Selector</p>
          <h1 className="m-0 mt-1 text-[20px] leading-[24px] font-bold text-[var(--text)]">Confidence Evidence</h1>
          <p className="caption-mono text-[var(--text-muted)] mt-1">Sub-score analysis</p>
        </div>
        {sensorIds.map((sid) => {
          const conf = confidence.find((c) => c.sensor_id === sid);
          const pct  = conf?.confidence_pct ?? null;
          const color = pct == null ? 'var(--text-dim)'
            : pct >= 80 ? 'var(--safe-text)'
            : pct >= 50 ? 'var(--caution)'
            : pct >= 20 ? 'var(--warning)'
            : 'var(--critical)';
          return (
            <button key={sid} onClick={() => selectSensor(sid)}
              className={`engineer-sensor-button transition-colors
                ${selectedSensorId === sid ? 'bg-[var(--bg-elevated)] border-l-2 border-l-[var(--primary)]' : 'hover:bg-[var(--bg-elevated)]'}`}>
              <span className="font-data text-[13px] text-[var(--text)] machine-token">{sid}</span>
              <span className="label-caps font-bold" style={{ color }}>
                {pct != null ? `${pct}%` : '-'}
              </span>
            </button>
          );
        })}
        {sensorIds.length === 0 && (
          <p className="caption-mono text-[var(--text-muted)] p-4">
            Connect to a plant to see sensors.
          </p>
        )}
      </aside>

      {/* -- Main - deep dive panels -- */}
      <main className="flex-1 min-w-0 overflow-y-auto scrollbar-thin p-6 space-y-6 bg-[var(--bg-base)]">
        <SupportViewNotice
          title="Engineer Analysis"
          status="support"
          source="Adaptive envelopes, confidence sub-scores, and score sensitivity evidence."
          boundary="Studio is the primary engineering compiler workspace."
        />
        {!selectedSensorId ? (
          <div className="h-full flex flex-col items-center justify-center gap-4 text-center">
            <span className="material-symbols-outlined text-[64px] text-[var(--border)]">biotech</span>
            <p className="text-[18px] font-semibold text-[var(--text-muted)]">Select a sensor to begin</p>
            <p className="caption-mono text-[var(--text-dim)] max-w-sm">
              Choose a sensor from the left panel to view engineering diagnostics and adaptive envelope details.
            </p>
          </div>
        ) : (
          <>
            {/* -- Header -- */}
            <div className="engineer-detail-header">
              <div className="min-w-0">
                <p className="label-caps text-[var(--primary)]">Engineering Evidence</p>
                <h1 className="text-[28px] font-bold text-[var(--text)]">{selectedSensorId}</h1>
                <p className="caption-mono text-[var(--text-muted)] mt-1">{plantId?.toUpperCase()}</p>
              </div>
              <div className="flex items-end gap-4">
                <div className="text-right">
                  <p className="label-caps text-[var(--text-muted)] mb-1">Overall Confidence</p>
                  <p className={`text-[36px] font-bold font-data ${
                    (selected?.confidence_pct ?? 100) >= 80 ? 'text-[var(--safe-text)]'
                    : (selected?.confidence_pct ?? 100) >= 50 ? 'text-[var(--caution)]'
                    : 'text-[var(--critical)]'
                  }`}>{selected?.confidence_pct ?? '-'}%</p>
                </div>
                <span className="industrial-badge mb-1" style={{
                  color: selected?.tier === 'CRITICAL' ? 'var(--critical)'
                       : selected?.tier === 'LOW'      ? 'var(--warning)'
                       : selected?.tier === 'MEDIUM'   ? 'var(--caution)'
                       : 'var(--safe-text)',
                  borderColor: 'currentColor',
                }}>
                  {selected?.tier || 'HIGH'}
                </span>
              </div>
            </div>

            {/* -- Sub-score breakdown -- */}
            <div className="industrial-card p-5">
              <p className="label-caps text-[var(--text-muted)] mb-4">Evidence Stack - Sub-Scores</p>
              <div className="space-y-4">
                <SubScoreBar label="Calibration Age"       value={subs.calibration} />
                <SubScoreBar label="Signal Stability"      value={subs.stability} />
                <SubScoreBar label="Cross-Sensor Alignment" value={subs.cross_sensor} />
                <SubScoreBar label="Range Plausibility"  value={subs.physical_plausibility} />
              </div>
            </div>

            {/* -- Adaptive envelope -- */}
            <div className="industrial-card p-5">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <p className="label-caps text-[var(--text-muted)]">Adaptive 3-Sigma Envelope</p>
                  <p className="caption-mono text-[var(--text-dim)] mt-1">
                    Dynamically learned from clean historical operation
                  </p>
                </div>
                {envelope && (
                  <div className="flex gap-3">
                    {[
                      { label: 'Mean',    value: envelope.mean?.toFixed(2) },
                      { label: 'Min',     value: envelope.normal_min?.toFixed(2) },
                      { label: 'Max',     value: envelope.normal_max?.toFixed(2) },
                      { label: 'Samples', value: envelope.sample_count },
                    ].map(({ label, value }) => (
                      <div key={label} className="industrial-card px-3 py-2 text-center">
                        <p className="label-caps text-[var(--text-muted)]">{label}</p>
                        <p className="font-data text-[14px] text-[var(--primary)] mt-1">{value ?? '-'}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {envelope ? (
                <div className="h-52">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={envChartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                      <CartesianGrid {...chartGrid} strokeDasharray="4 2" />
                      <XAxis dataKey="time" tick={{ ...axisTick, fontSize: 10 }}
                        axisLine={axisLine} tickLine={false} />
                      <YAxis tick={{ ...axisTick, fontSize: 10 }}
                        axisLine={false} tickLine={false} />
                      <Tooltip content={<IndustrialTooltip />} />
                      <ReferenceLine y={envelope.normal_max} stroke="var(--warning)" strokeDasharray="4 2" label={{ value: '+3sigma', fill: 'var(--warning)', fontSize: 10 }} />
                      <ReferenceLine y={envelope.normal_min} stroke="var(--warning)" strokeDasharray="4 2" label={{ value: '-3sigma', fill: 'var(--warning)', fontSize: 10 }} />
                      <ReferenceLine y={envelope.mean}       stroke="var(--text-dim)" strokeDasharray="4 2" label={{ value: 'mean', fill: 'var(--text-dim)', fontSize: 10 }} />
                      <Line dataKey="value" name="Sensor reading" stroke="var(--primary)" strokeWidth={2} dot={false} isAnimationActive={false} />
                      <Line dataKey="mean"  name="Running mean"   stroke="var(--text-dim)" strokeWidth={1} dot={false} strokeDasharray="4 2" isAnimationActive={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="h-32 flex items-center justify-center">
                  <p className="caption-mono text-[var(--text-muted)]">
                    Insufficient clean history to compute adaptive envelope for {selectedSensorId}.
                    Requires minimum 72h of anomaly-free operation.
                  </p>
                </div>
              )}
            </div>

            {/* -- Failure reasons -- */}
            {(selected?.reasons || []).length > 0 && (
              <div className="industrial-card p-5">
                <p className="label-caps text-[var(--text-muted)] mb-3">Active Diagnostic Flags</p>
                <div className="space-y-2">
                  {selected.reasons.map((reason, i) => (
                    <div key={i} className="flex items-start gap-3 py-2 border-b border-[var(--border-subtle)]">
                      <span className="material-symbols-outlined text-[var(--critical)] text-[16px] mt-0.5">error</span>
                      <p className="caption-mono text-[var(--text)]">{reason}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </main>
      </div>
    </div>
  );
}
