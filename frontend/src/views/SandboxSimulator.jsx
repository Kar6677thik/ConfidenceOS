/**
 * views/SandboxSimulator.jsx - Failure Scenario Sandbox
 *
 * Endpoints:
 *   POST /api/sandbox/run - inject failure, returns simulated sensor trajectory
 *
 * Stitch mockup: (no dedicated HTML - uses App.jsx logic)
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import useStore from '../store';
import { chartColors, chartGrid, axisTick, axisLine, TRUST_COLOR } from '../lib/chartTheme';
import PageIdentity from '../components/hmi/PageIdentity';
import StatusTag from '../components/hmi/StatusTag';
import apiFetch from '../lib/apiFetch';

// Fallback only — the live list is fetched from the active asset model
// (/api/model/signals) so the sandbox reflects whatever model is loaded.
const FALLBACK_SENSOR_IDS = ['LT-5100', 'FI-2010', 'FO-2020', 'PT-3100', 'TT-4100', 'ZT-6100'];
const FAILURE_MODES = [
  { value: 'calibration_drift',       label: 'Calibration Drift' },
  { value: 'stuck_reading',            label: 'Stuck Reading' },
  { value: 'sg_mismatch',              label: 'Specific Gravity Mismatch' },
  { value: 'command_state_decoupling', label: 'Command-State Decoupling' },
];
const SEVERITIES = ['mild', 'moderate', 'severe'];

function IndustrialTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <p className="label-caps text-[var(--text-muted)] mb-2">T+{label}h</p>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="flex items-center gap-2 mt-1">
          <span className="led-square" style={{ color: entry.color }} />
          <span className="text-[var(--text)]">{entry.name}</span>
          <span className="ml-auto" style={{ color: entry.color }}>
            {typeof entry.value === 'number' ? entry.value.toFixed(1) : entry.value}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function SandboxSimulator() {
  const { plantId, role } = useStore();
  const navigate = useNavigate();

  useEffect(() => {
    if (role !== 'Engineer') {
      navigate('/runtime', { replace: true });
    }
  }, [role, navigate]);
  const [form, setForm] = useState({
    sensor_id:    'LT-5100',
    failure_mode: 'calibration_drift',
    severity:     'moderate',
    duration_hours: 6,
  });
  const [result,  setResult]  = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);
  const [sensorIds, setSensorIds] = useState(FALLBACK_SENSOR_IDS);

  // Populate the sensor dropdown from the active asset model rather than a
  // hardcoded six-sensor list; fall back to the constant on error.
  useEffect(() => {
    fetch('/api/model/signals')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        const ids = (data?.signals || []).map((s) => s.tag || s.id).filter(Boolean);
        if (ids.length) {
          setSensorIds(ids);
          setForm((prev) => (ids.includes(prev.sensor_id) ? prev : { ...prev, sensor_id: ids[0] }));
        }
      })
      .catch(() => { /* keep fallback list */ });
  }, []);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch('/api/sandbox/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plant_id: plantId,
          ...form,
          duration_hours: Number(form.duration_hours),
        }),
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      setResult(await res.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const chartData = result?.results?.map((item) => ({
    time:        item.time_hours,
    confidence:  item.confidence_pct,
    discrepancy: item.mass_balance?.discrepancy,
  })) || [];
  const massBalanceApplicable = result?.results?.some(
    (item) => item.mass_balance?.applicable !== false && item.mass_balance?.discrepancy != null,
  );
  const massBalanceReason = result?.results?.find(
    (item) => item.mass_balance?.applicable === false,
  )?.mass_balance?.reason;

  const minConf = chartData.length
    ? Math.min(...chartData.map((d) => d.confidence ?? 100))
    : null;

  return (
    <div className="industrial-page flex overflow-hidden">

      {/* -- Left controls sidebar -- */}
      <aside className="w-80 flex flex-col bg-[var(--bg-low)] border-r border-[var(--border)]">
        <PageIdentity displayName="Trust Degradation Sandbox" level={3} area="Isolated Simulation Environment" />
        <div className="flex items-center gap-2 px-5 py-1.5 border-b border-[var(--border)] flex-shrink-0">
          <StatusTag tier="MEDIUM" label="Isolated" />
          <span className="caption-mono text-[var(--text-dim)]">Live plant unaffected</span>
        </div>

        <div className="p-5 space-y-4 flex-1 overflow-y-auto scrollbar-thin">
          <p className="caption-mono text-[var(--text-muted)] leading-relaxed">
            Inject synthetic trust degradation into an isolated sensor model.
            Live plant data is never affected.
          </p>

          {/* Sensor */}
          <div>
            <label className="label-caps text-[var(--text-muted)] block mb-2">Sensor</label>
            <select value={form.sensor_id}
              onChange={(e) => setForm({ ...form, sensor_id: e.target.value })}
              className="industrial-select">
              {sensorIds.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
          </div>

          {/* Failure mode */}
          <div>
            <label className="label-caps text-[var(--text-muted)] block mb-2">Degradation Mode</label>
            <select value={form.failure_mode}
              onChange={(e) => setForm({ ...form, failure_mode: e.target.value })}
              className="industrial-select">
              {FAILURE_MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
          </div>

          {/* Severity */}
          <div>
            <label className="label-caps text-[var(--text-muted)] block mb-2">Severity</label>
            <div className="flex gap-1">
              {SEVERITIES.map((s) => (
                <button key={s} onClick={() => setForm({ ...form, severity: s })}
                  className={`flex-1 py-2 label-caps capitalize rounded border transition-colors
                    ${form.severity === s
                      ? 'bg-[var(--bg-elevated)] text-[var(--warning)] border-[var(--warning)]/60'
                      : 'text-[var(--text-muted)] border-[var(--border)] hover:bg-[var(--bg-elevated)]'}`}>
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Duration */}
          <div>
            <label className="label-caps text-[var(--text-muted)] block mb-2">
              Duration (hours)
            </label>
            <input type="number" value={form.duration_hours}
              onChange={(e) => setForm({ ...form, duration_hours: e.target.value })}
              className="industrial-input" min="1" max="72" />
          </div>

          <button onClick={run} disabled={loading}
            className="w-full industrial-control text-[var(--warning)] border-[var(--warning)]/60 disabled:opacity-40">
            {loading ? 'Simulating...' : ' Run Sandbox'}
          </button>

          {error && (
            <p className="caption-mono text-[var(--critical)] bg-[rgba(147,0,10,0.1)] px-3 py-2 rounded">
              {error}
            </p>
          )}
        </div>
      </aside>

      {/* -- Main - results canvas -- */}
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden bg-[var(--bg-base)]">
        <div className="industrial-card-header px-5 py-3 border-b border-[var(--border)] bg-[var(--bg-surface)]">
          <span className="text-[18px] font-semibold text-[var(--text)]">Sandbox Results</span>
          {result && (
            <span className="caption-mono text-[var(--text-muted)]">
              {result.sample_count} samples / {form.sensor_id} / {form.failure_mode.replace(/_/g, ' ')}
            </span>
          )}
        </div>

        <div className="flex-1 overflow-y-auto scrollbar-thin p-6 space-y-6">
          {!result ? (
            <div className="h-full flex flex-col items-center justify-center gap-4 text-center">
              <span className="material-symbols-outlined text-[64px] text-[var(--border)]">science</span>
              <p className="text-[18px] font-semibold text-[var(--text-muted)]">No simulation run yet</p>
              <p className="caption-mono text-[var(--text-dim)] max-w-sm">
                Configure a failure scenario on the left and click Run Sandbox to see how ConfidenceOS responds.
              </p>
            </div>
          ) : (
            <>
              {/* Summary chips */}
              {minConf != null && (
                <div className="flex gap-3">
                  <div className="industrial-card px-4 py-3">
                    <p className="label-caps text-[var(--text-muted)] mb-1">Min Confidence</p>
                    <p className={`text-[24px] font-bold font-data ${
                      minConf < 20 ? 'text-[var(--critical)]' : minConf < 50 ? 'text-[var(--warning)]' : 'text-[var(--primary)]'
                    }`}>{minConf.toFixed(1)}%</p>
                  </div>
                  <div className="industrial-card px-4 py-3">
                    <p className="label-caps text-[var(--text-muted)] mb-1">Samples</p>
                    <p className="text-[24px] font-bold font-data text-[var(--text)]">{result.sample_count}</p>
                  </div>
                  <div className="industrial-card px-4 py-3">
                    <p className="label-caps text-[var(--text-muted)] mb-1">Duration</p>
                    <p className="text-[24px] font-bold font-data text-[var(--text)]">{form.duration_hours}h</p>
                  </div>
                  <div className="industrial-card px-4 py-3">
                    <p className="label-caps text-[var(--text-muted)] mb-1">Physical Check</p>
                    <p className="text-[16px] leading-[22px] font-bold font-data text-[var(--text)]">
                      {massBalanceApplicable ? 'Mass balance' : 'Device trust only'}
                    </p>
                  </div>
                </div>
              )}

              {/* Chart */}
              <div className="industrial-card p-4">
                <p className="label-caps text-[var(--text-muted)] mb-4">Confidence & Mass-Balance Trajectory</p>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
                      <CartesianGrid {...chartGrid} strokeDasharray="4 2" />
                      <XAxis dataKey="time" tick={{ ...axisTick, fontSize: 10 }}
                        axisLine={axisLine} tickLine={false} />
                      <YAxis tick={{ ...axisTick, fontSize: 10 }}
                        axisLine={false} tickLine={false} />
                      <Tooltip content={<IndustrialTooltip />} />
                      <Legend wrapperStyle={{ paddingTop: '8px', fontSize: '11px', color: chartColors.muted }} />
                      <Line dataKey="confidence" name="Confidence %" stroke={chartColors.primary}
                        strokeWidth={2} dot={false} isAnimationActive={false} />
                      {massBalanceApplicable && (
                        <Line dataKey="discrepancy" name="Mass-Balance Delta" stroke={TRUST_COLOR.LOW}
                          strokeWidth={2} dot={false} isAnimationActive={false} strokeDasharray="4 2" />
                      )}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                {!massBalanceApplicable && massBalanceReason && (
                  <p className="caption-mono text-[var(--text-muted)] mt-3">
                    {massBalanceReason}
                  </p>
                )}
              </div>

              {/* Advisory note */}
              <div className="industrial-card p-4 border-[var(--warning)]/30">
                <div className="flex gap-3">
                  <span className="material-symbols-outlined text-[var(--warning)] shrink-0">science</span>
                  <p className="caption-mono text-[var(--text-muted)] leading-relaxed">
                    This simulation ran entirely on isolated data - no live plant tags were affected.
                    The confidence curve shows how ConfidenceOS would respond to a <strong className="text-[var(--text)]">
                    {form.severity} {form.failure_mode.replace(/_/g, ' ')}</strong> on sensor <strong className="text-[var(--text)]">{form.sensor_id}</strong>.
                  </p>
                </div>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

