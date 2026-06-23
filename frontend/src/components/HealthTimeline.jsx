import { useState, useEffect, useCallback } from 'react';
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts';

const SEVERITY_STYLES = {
  CRITICAL: 'status-critical',
  WARNING: 'status-warning',
  INFO: 'text-[var(--data-mono)]',
};

const CALIBRATION_STATUS_LABELS = {
  current: 'OK',
  due_soon: 'STALE',
  expired: 'EXPIRED',
  OK: 'OK',
  STALE: 'STALE',
  EXPIRED: 'EXPIRED',
};

const CALIBRATION_STATUS_STYLES = {
  OK: 'status-safe',
  STALE: 'status-warning',
  EXPIRED: 'status-critical',
};

function LoadingSpinner() {
  return (
    <div className="py-12 caption-mono text-[var(--data-mono)]">
      Loading health data...
    </div>
  );
}

function EmptyState() {
  return (
    <div className="py-12 text-center">
      <p className="label-caps text-[var(--text-muted)]">No Sensor Selected</p>
      <p className="caption-mono text-[var(--data-mono)] mt-2">Choose a sensor to view health timeline.</p>
    </div>
  );
}

function CalibrationCard({ calibration }) {
  if (!calibration) return null;

  const { age_days: age, score, status } = calibration;
  const displayStatus = CALIBRATION_STATUS_LABELS[status] || 'UNKNOWN';
  const statusClass = CALIBRATION_STATUS_STYLES[displayStatus] || 'text-[var(--data-mono)]';

  return (
    <div className="mb-5">
      <h3 className="label-caps text-[var(--text-muted)] mb-3">Calibration Status</h3>
      <div className="industrial-grid-shell grid-cols-3">
        <div className="industrial-panel-subtle p-3 text-center">
          <p className="label-caps text-[var(--text-muted)]">Age</p>
          <p className="font-data text-xl text-[var(--text)]">{age ?? '--'}</p>
        </div>
        <div className="industrial-panel-subtle p-3 text-center">
          <p className="label-caps text-[var(--text-muted)]">Score</p>
          <p className="font-data text-xl text-[var(--text)]">{score != null ? `${Math.round(score * 100)}%` : '--'}</p>
        </div>
        <div className="industrial-panel-subtle p-3 text-center">
          <p className="label-caps text-[var(--text-muted)]">Status</p>
          <span className={`industrial-badge ${statusClass}`}>{displayStatus}</span>
        </div>
      </div>
    </div>
  );
}

function AnomalyLog({ anomalies }) {
  if (!anomalies || anomalies.length === 0) {
    return (
      <div className="mb-5">
        <h3 className="label-caps text-[var(--text-muted)] mb-3">Anomaly Log</h3>
        <p className="caption-mono text-[var(--data-mono)]">No anomalies recorded.</p>
      </div>
    );
  }

  return (
    <div className="mb-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="label-caps text-[var(--text-muted)]">Anomaly Log</h3>
        <span className="industrial-badge text-[var(--data-mono)]">{anomalies.length}</span>
      </div>
      <ul className="max-h-56 overflow-y-auto scrollbar-thin space-y-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
        {anomalies.map((entry, index) => {
          const severity = entry.severity?.toUpperCase() ?? 'INFO';
          const statusClass = SEVERITY_STYLES[severity] || SEVERITY_STYLES.INFO;
          return (
            <li key={entry.id ?? index} className="industrial-panel-subtle p-3">
              <div className="flex items-start gap-3">
                <span className={`industrial-badge ${statusClass}`}>{severity}</span>
                <div className="min-w-0">
                  <p className="text-sm text-[var(--text)]">{entry.description || entry.message}</p>
                  {entry.timestamp && (
                    <p className="caption-mono text-[var(--data-mono)] mt-1">
                      {new Date(entry.timestamp).toLocaleString()}
                    </p>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function DriftSparkline({ driftData }) {
  if (!driftData || driftData.length === 0) {
    return (
      <div>
        <h3 className="label-caps text-[var(--text-muted)] mb-3">Drift Trend</h3>
        <p className="caption-mono text-[var(--data-mono)]">No drift data available.</p>
      </div>
    );
  }

  return (
    <div>
      <h3 className="label-caps text-[var(--text-muted)] mb-3">Drift Trend</h3>
      <div className="industrial-panel-subtle p-3" style={{ minWidth: 0 }}>
        <ResponsiveContainer width="100%" height={80} debounce={50}>
          <LineChart data={driftData}>
            <YAxis hide domain={['auto', 'auto']} />
            <Line type="monotone" dataKey="value" stroke="#00FF41" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function HealthTimeline({ sensorId, apiBase = '/api' }) {
  const [healthData, setHealthData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchHealth = useCallback(async (id) => {
    if (!id) {
      setHealthData(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${apiBase}/sensors/${id}/health`);
      if (!res.ok) throw new Error(`Server responded with ${res.status}`);
      setHealthData(await res.json());
    } catch (err) {
      console.error('[HealthTimeline] Fetch failed:', err);
      setError(err.message ?? 'Failed to load health data');
      setHealthData(null);
    } finally {
      setLoading(false);
    }
  }, [apiBase]);

  useEffect(() => {
    if (!sensorId) {
      setHealthData(null);
      return;
    }
    fetchHealth(sensorId);
    const interval = setInterval(() => fetchHealth(sensorId), 8000);
    return () => clearInterval(interval);
  }, [sensorId, fetchHealth]);

  return (
    <section className="industrial-panel w-full">
      <div className="industrial-panel-header">
        <h2 className="industrial-panel-title text-base">Sensor Health Timeline</h2>
        {sensorId && <span className="industrial-badge status-safe">{sensorId}</span>}
      </div>
      <div className="industrial-body">
        {!sensorId && <EmptyState />}
        {sensorId && loading && <LoadingSpinner />}
        {sensorId && error && (
          <div className="py-8 text-center">
            <p className="caption-mono status-critical mb-3">{error}</p>
            <button onClick={() => fetchHealth(sensorId)} className="industrial-control status-safe">Retry</button>
          </div>
        )}
        {sensorId && !loading && !error && healthData && (
          <>
            <CalibrationCard calibration={healthData.calibration} />
            <AnomalyLog anomalies={healthData.anomalies} />
            <DriftSparkline driftData={healthData.drift_trend?.values?.map((value, index) => ({ value, time: index }))} />
          </>
        )}
      </div>
    </section>
  );
}
