import { useState, useEffect, useCallback } from 'react';
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts';

/**
 * HealthTimeline — Module 4: Sensor Health Timeline Panel
 *
 * Displays calibration status, anomaly log, and drift trend for a selected sensor.
 * Fetches data from GET {apiBase}/sensors/{sensorId}/health on sensor change.
 */

// ---------------------------------------------------------------------------
// Severity badge color mapping
// ---------------------------------------------------------------------------
const SEVERITY_STYLES = {
  CRITICAL: 'bg-red-500/20 text-red-400 border-red-500/40',
  WARNING:  'bg-amber-500/20 text-amber-400 border-amber-500/40',
  INFO:     'bg-blue-500/20 text-blue-400 border-blue-500/40',
};

// Calibration status badge colors
const CALIBRATION_STATUS_STYLES = {
  OK:       'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
  STALE:    'bg-amber-500/20 text-amber-400 border-amber-500/40',
  EXPIRED:  'bg-red-500/20 text-red-400 border-red-500/40',
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Loading spinner overlay */
function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="relative">
        <div className="h-10 w-10 rounded-full border-2 border-gray-700" />
        <div className="absolute top-0 left-0 h-10 w-10 rounded-full border-2 border-t-cyan-400 animate-spin" />
      </div>
      <span className="ml-3 text-gray-400 text-sm">Loading health data…</span>
    </div>
  );
}

/** Empty state when no sensor is selected */
function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-gray-500">
      <svg className="w-12 h-12 mb-3 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
      <p className="text-sm font-medium">Select a sensor</p>
      <p className="text-xs text-gray-600 mt-1">Choose a sensor to view its health timeline</p>
    </div>
  );
}

/** Calibration status card */
function CalibrationCard({ calibration }) {
  if (!calibration) return null;

  const { age_days: age, score, status } = calibration;
  const badgeStyle = CALIBRATION_STATUS_STYLES[status] || CALIBRATION_STATUS_STYLES.OK;

  return (
    <div className="mb-5">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">
        Calibration Status
      </h3>
      <div className="grid grid-cols-3 gap-3">
        {/* Age */}
        <div className="bg-gray-800/50 rounded-lg p-3 text-center">
          <p className="text-xs text-gray-500 mb-1">Age</p>
          <p className="text-lg font-bold text-gray-200">{age ?? '—'}</p>
        </div>
        {/* Score */}
        <div className="bg-gray-800/50 rounded-lg p-3 text-center">
          <p className="text-xs text-gray-500 mb-1">Score</p>
          <p className="text-lg font-bold text-gray-200">
            {score != null ? `${Math.round(score * 100)}%` : '—'}
          </p>
        </div>
        {/* Status badge */}
        <div className="bg-gray-800/50 rounded-lg p-3 flex items-center justify-center">
          <span className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${badgeStyle}`}>
            {status ?? 'UNKNOWN'}
          </span>
        </div>
      </div>
    </div>
  );
}

/** Anomaly log — scrollable list with severity badges */
function AnomalyLog({ anomalies }) {
  if (!anomalies || anomalies.length === 0) {
    return (
      <div className="mb-5">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">
          Anomaly Log
        </h3>
        <p className="text-sm text-gray-600 italic">No anomalies recorded.</p>
      </div>
    );
  }

  return (
    <div className="mb-5">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">
        Anomaly Log
        <span className="ml-2 text-gray-600 font-normal">({anomalies.length})</span>
      </h3>
      <ul className="max-h-56 overflow-y-auto space-y-2 pr-1 scrollbar-thin">
        {anomalies.map((entry, idx) => {
          const severity = entry.severity?.toUpperCase() ?? 'INFO';
          const badgeStyle = SEVERITY_STYLES[severity] || SEVERITY_STYLES.INFO;

          return (
            <li
              key={entry.id ?? idx}
              className="flex items-start gap-3 bg-gray-800/40 rounded-lg px-3 py-2.5 border border-gray-700/50"
            >
              {/* Severity badge */}
              <span className={`shrink-0 text-[10px] font-bold px-2 py-0.5 rounded border mt-0.5 ${badgeStyle}`}>
                {severity}
              </span>
              {/* Content */}
              <div className="min-w-0 flex-1">
                <p className="text-sm text-gray-300 leading-snug">{entry.description || entry.message}</p>
                {entry.timestamp && (
                  <p className="text-[10px] text-gray-600 mt-1">
                    {new Date(entry.timestamp).toLocaleString()}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Drift trend sparkline chart */
function DriftSparkline({ driftData }) {
  if (!driftData || driftData.length === 0) {
    return (
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">
          Drift Trend
        </h3>
        <p className="text-sm text-gray-600 italic">No drift data available.</p>
      </div>
    );
  }

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">
        Drift Trend
      </h3>
      <div className="bg-gray-800/40 rounded-lg p-3 border border-gray-700/50">
        <ResponsiveContainer width="100%" height={80}>
          <LineChart data={driftData}>
            <YAxis hide domain={['auto', 'auto']} />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#22d3ee"
              strokeWidth={2}
              dot={false}
              isAnimationActive={true}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function HealthTimeline({ sensorId, apiBase = '/api' }) {
  const [healthData, setHealthData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  /** Fetch health data whenever sensorId changes */
  const fetchHealth = useCallback(async (id) => {
    if (!id) {
      setHealthData(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${apiBase}/sensors/${id}/health`);

      if (!res.ok) {
        throw new Error(`Server responded with ${res.status}`);
      }

      const data = await res.json();
      setHealthData(data);
    } catch (err) {
      console.error('[HealthTimeline] Fetch failed:', err);
      setError(err.message ?? 'Failed to load health data');
      setHealthData(null);
    } finally {
      setLoading(false);
    }
  }, [apiBase]);

  useEffect(() => {
    fetchHealth(sensorId);
  }, [sensorId, fetchHealth]);

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div
      className="
        bg-gray-900/70 backdrop-blur-xl border border-gray-700/50
        rounded-2xl shadow-2xl p-5
        w-full max-w-md
      "
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-bold tracking-wide text-gray-200 uppercase">
          Sensor Health Timeline
        </h2>
        {sensorId && (
          <span className="text-[10px] bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 px-2 py-0.5 rounded-full font-mono">
            {sensorId}
          </span>
        )}
      </div>

      {/* Body — conditional render based on state */}
      {!sensorId && <EmptyState />}

      {sensorId && loading && <LoadingSpinner />}

      {sensorId && error && (
        <div className="text-center py-10">
          <p className="text-red-400 text-sm mb-2">⚠ {error}</p>
          <button
            onClick={() => fetchHealth(sensorId)}
            className="text-xs text-cyan-400 hover:text-cyan-300 underline underline-offset-2 cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {sensorId && !loading && !error && healthData && (
        <>
          <CalibrationCard calibration={healthData.calibration} />
          <AnomalyLog anomalies={healthData.anomalies} />
          <DriftSparkline driftData={healthData.drift_trend?.values?.map((v, i) => ({ value: v, time: i }))} />
        </>
      )}
    </div>
  );
}
