import { useState, useMemo } from 'react';
import useStore from '../store';

const SEVERITY_CLASS = {
  CRITICAL: 'status-critical',
  LOW:      'status-warning',
  DEGRADED: 'status-caution',
  NOMINAL:  'text-[var(--text-muted)]',
};

export default function WhatIfPanel() {
  const { authToken, plantId, confidence } = useStore();

  const sensors = useMemo(
    () =>
      [...(confidence || [])]
        .sort((a, b) => a.sensor_id.localeCompare(b.sensor_id)),
    [confidence],
  );

  const [sensorId, setSensorId]     = useState('');
  const [whatIfPct, setWhatIfPct]   = useState(50);
  const [result, setResult]         = useState(null);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState(null);

  const currentPct = useMemo(() => {
    const s = confidence?.find((c) => c.sensor_id === sensorId);
    return s ? Math.round(s.confidence_pct ?? 100) : null;
  }, [confidence, sensorId]);

  const runScenario = async () => {
    if (!sensorId) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (authToken) headers.Authorization = `Bearer ${authToken}`;
      const res = await fetch('/api/confidence/what-if', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          sensor_id: sensorId,
          what_if_pct: whatIfPct,
          plant_id: plantId || 'plant-a',
        }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail?.detail || `${res.status} ${res.statusText}`);
      }
      setResult(await res.json());
    } catch (err) {
      setError(err.message || 'Scenario failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="industrial-card p-0 overflow-hidden">
      <div className="industrial-card-header px-4 py-3 border-b border-[var(--border)] flex items-center justify-between">
        <span className="text-[14px] font-semibold text-[var(--text)]">What-If Scenario</span>
        {result?.ai_assisted && (
          <span className="industrial-badge status-safe">AI</span>
        )}
        {result && !result.ai_assisted && (
          <span className="industrial-badge text-[var(--text-muted)]">Deterministic</span>
        )}
      </div>

      <div className="p-4 space-y-4">
        {/* Sensor select */}
        <div className="space-y-1">
          <label className="label-caps text-[var(--text-muted)]">Sensor</label>
          <select
            value={sensorId}
            onChange={(e) => { setSensorId(e.target.value); setResult(null); setError(null); }}
            className="industrial-select w-full"
          >
            <option value="">— select sensor —</option>
            {sensors.map((s) => (
              <option key={s.sensor_id} value={s.sensor_id}>
                {s.sensor_id} ({Math.round(s.confidence_pct ?? 0)}%)
              </option>
            ))}
          </select>
        </div>

        {/* Slider */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <label className="label-caps text-[var(--text-muted)]">
              Hypothetical Confidence
            </label>
            <span className="caption-mono text-[var(--text)] font-semibold tabular-nums">
              {whatIfPct}%
              {currentPct !== null && (
                <span className="text-[var(--text-muted)] font-normal ml-1">
                  (currently {currentPct}%)
                </span>
              )}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            value={whatIfPct}
            onChange={(e) => { setWhatIfPct(Number(e.target.value)); setResult(null); setError(null); }}
            className="w-full accent-[var(--primary)]"
          />
          <div className="flex justify-between caption-mono text-[10px] text-[var(--text-muted)]">
            <span>0% Failed</span>
            <span>50% Degraded</span>
            <span>100% Nominal</span>
          </div>
        </div>

        {/* Run button */}
        <button
          onClick={runScenario}
          disabled={!sensorId || loading}
          className="industrial-control w-full disabled:opacity-40"
        >
          {loading ? 'Running Scenario…' : 'Run Scenario'}
        </button>

        {/* Loading */}
        {loading && (
          <div className="flex items-center gap-3 py-1">
            <span className="led-square status-warning dot-blink" />
            <span className="caption-mono text-[var(--text-muted)]">
              Propagating cascade from {sensorId}…
            </span>
          </div>
        )}

        {/* Error */}
        {error && (
          <p className="caption-mono status-critical">{error}</p>
        )}

        {/* Results */}
        {result && (
          <div className="space-y-4 pt-1 border-t border-[var(--border)]">
            {/* Narrative */}
            <p className="caption-mono text-[var(--text)] leading-relaxed text-[13px]">
              {result.narrative}
            </p>

            {/* Affected sensors table */}
            {result.affected?.length > 0 ? (
              <div className="space-y-1">
                <p className="label-caps text-[var(--text-muted)]">
                  Affected Downstream ({result.affected.length})
                </p>
                <div className="space-y-1">
                  {result.affected.map((s) => (
                    <div
                      key={s.sensor_id}
                      className="flex items-center justify-between gap-2 py-1 px-2 rounded industrial-panel-subtle"
                    >
                      <span className="caption-mono text-[var(--text)] font-semibold w-[80px] shrink-0">
                        {s.sensor_id}
                      </span>
                      <div className="flex items-center gap-1 caption-mono text-[12px] tabular-nums flex-1">
                        <span className="text-[var(--text-muted)]">{s.current_pct}%</span>
                        <span className="text-[var(--text-muted)]">→</span>
                        <span className={SEVERITY_CLASS[s.severity] || ''}>{s.estimated_pct}%</span>
                        <span className={`ml-1 ${SEVERITY_CLASS[s.severity] || ''}`}>
                          ({s.estimated_impact})
                        </span>
                      </div>
                      <span className={`industrial-badge text-[11px] ${SEVERITY_CLASS[s.severity] || ''}`}>
                        {s.severity}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 py-2">
                <span className="led-square status-safe" />
                <span className="caption-mono text-[var(--text-muted)]">
                  No downstream sensors affected at this confidence level.
                </span>
              </div>
            )}

            {/* AI label */}
            <p className="caption-mono text-[var(--text-dim)] text-[11px] leading-relaxed">
              {result.ai_label}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
