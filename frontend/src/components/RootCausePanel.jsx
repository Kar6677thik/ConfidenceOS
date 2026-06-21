import { useState } from 'react';
import useStore from '../store';

const FAULT_CLASS_META = {
  sensor_fault:  { label: 'Sensor Fault',    className: 'status-warning' },
  process_issue: { label: 'Process Issue',   className: 'status-caution' },
  uncertain:     { label: 'Uncertain',        className: 'text-[var(--text-muted)]' },
};

export default function RootCausePanel({ sensorId }) {
  const { plantId, authToken, confidence } = useStore();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  if (!sensorId) return null;

  const selected = confidence.find((c) => c.sensor_id === sensorId);
  const tier = selected?.tier || 'HIGH';
  const isHealthy = tier === 'HIGH';

  const analyze = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const headers = {};
      if (authToken) headers.Authorization = `Bearer ${authToken}`;
      const res = await fetch(
        `/api/confidence/${encodeURIComponent(sensorId)}/root-cause?plant_id=${plantId}`,
        { headers },
      );
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err.message || 'Analysis failed.');
    } finally {
      setLoading(false);
    }
  };

  const meta = FAULT_CLASS_META[result?.fault_class] || FAULT_CLASS_META.uncertain;

  return (
    <div className="industrial-card p-0 overflow-hidden shrink-0">
      <div className="industrial-card-header px-4 py-3 border-b border-[var(--border)] flex items-center justify-between">
        <span className="text-[14px] font-semibold text-[var(--text)]">AI Root Cause</span>
        {result?.ai_assisted && (
          <span className="industrial-badge status-safe">AI</span>
        )}
        {result && !result.ai_assisted && (
          <span className="industrial-badge text-[var(--text-muted)]">Deterministic</span>
        )}
      </div>

      <div className="p-4 space-y-3">
        {!result && !loading && (
          <>
            {isHealthy ? (
              <div className="flex items-center gap-2 mb-1">
                <span className="led-square status-safe" />
                <span className="caption-mono text-[var(--text-muted)] text-[11px]">
                  {sensorId} at HIGH confidence — analyse baseline or inject a failure to test
                </span>
              </div>
            ) : (
              <p className="caption-mono text-[var(--text-muted)]">
                Sensor <span className="text-[var(--text)] font-semibold">{sensorId}</span> is{' '}
                <span className="status-warning font-semibold">{tier}</span> — click to identify
                whether this is a sensor fault or process issue.
              </p>
            )}
            <button onClick={analyze} className="industrial-control w-full">
              Analyze Root Cause
            </button>
          </>
        )}

        {loading && (
          <div className="flex items-center gap-3 py-2">
            <span className="led-square status-warning dot-blink" />
            <span className="caption-mono text-[var(--text-muted)]">Analysing {sensorId}…</span>
          </div>
        )}

        {error && (
          <div className="space-y-2">
            <p className="caption-mono status-critical">{error}</p>
            <button onClick={analyze} className="industrial-control w-full">Retry</button>
          </div>
        )}

        {result && (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <span className={`industrial-badge ${meta.className}`}>{meta.label}</span>
              <span className="caption-mono text-[var(--text-muted)] text-[11px]">
                {result.confidence_pct}% confidence
              </span>
            </div>

            <p className="caption-mono text-[var(--text)] leading-relaxed text-[13px]">
              {result.narrative}
            </p>

            {result.check_first && (
              <div className="industrial-panel-subtle p-3">
                <p className="label-caps text-[var(--text-muted)]">Check First</p>
                <p className="caption-mono text-[var(--text)] mt-1 font-semibold">
                  {result.check_first}
                </p>
              </div>
            )}

            <p className="caption-mono text-[var(--text-dim)] text-[11px] leading-relaxed">
              {result.ai_label}
            </p>

            <button
              onClick={analyze}
              className="industrial-control w-full opacity-60 hover:opacity-100"
            >
              Re-analyse
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
