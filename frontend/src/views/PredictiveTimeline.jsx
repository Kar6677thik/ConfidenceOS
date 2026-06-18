/**
 * views/PredictiveTimeline.jsx - Confidence Degradation Timeline
 *
 * Endpoints:
 *   GET /api/predictions/:plant_id - degradation forecasts for all sensors
 *
 * Stitch mockup: 3predictive_maintanance.html
 */

import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import useStore from '../store';
import ConfidenceDebtPanel from '../components/ConfidenceDebtPanel';
import PageIdentity from '../components/hmi/PageIdentity';

const WINDOW_HOURS = 12;

function ConfidenceBadge({ conf }) {
  if (conf == null) return null;
  const color = conf >= 80 ? 'var(--safe-text)' : conf >= 50 ? 'var(--caution)' : conf >= 20 ? 'var(--warning)' : 'var(--critical)';
  return (
    <span className="label-caps font-bold" style={{ color }}>{conf}% conf</span>
  );
}

function forecastLabel(pred) {
  const status = pred.forecast_status || pred.model_fit;
  if (status === 'insufficient_history') return `Collecting history (${pred.sample_count || 0} samples)`;
  if (status === 'flat_or_no_degradation') return 'No active degradation trend';
  if (status === 'model_error') return 'Forecast model unavailable';
  return pred.model_type || 'deterministic trend';
}

// Honest one-line explanation so a flat/empty forecast reads as deliberate,
// not broken — distinguishes "stable" from "not enough data to project".
function forecastDetail(pred) {
  const status = pred.forecast_status || pred.model_fit;
  if (status === 'insufficient_history') return 'Not enough confidence history yet to project a trend.';
  if (status === 'flat_or_no_degradation') return 'Confidence is stable over the window — nothing to project.';
  if (status === 'model_error') return 'Forecast model could not run; deterministic status only.';
  return null;
}

export default function PredictiveTimeline() {
  const { plantId, predictions, predictionsLoading, fetchPredictions } = useStore();

  useEffect(() => { fetchPredictions(plantId); }, [fetchPredictions, plantId]);

  const rows = Object.values(predictions || {});
  const actionQueue = rows
    .filter((p) => p.time_to_low_hours != null || p.time_to_critical_hours != null)
    .sort((a, b) =>
      (a.time_to_critical_hours ?? a.time_to_low_hours ?? 99) -
      (b.time_to_critical_hours ?? b.time_to_low_hours ?? 99)
    );

  const avgPLT = rows.filter((r) => r.time_to_low_hours != null).length
    ? (rows.reduce((s, r) => s + (r.time_to_low_hours ?? 0), 0) /
        rows.filter((r) => r.time_to_low_hours != null).length).toFixed(1)
    : null;

  return (
    <div className="industrial-page flex flex-col overflow-hidden">

      {/* -- Context header -- */}
      <PageIdentity displayName="Confidence Degradation Timeline" level={3} area="12-Hour Trust Forecast Window / Sorted by Criticality" plant={plantId} />
      <div className="px-6 py-2 border-b border-[var(--border)] flex items-center justify-end gap-3 flex-shrink-0 bg-[var(--bg-low)]">
        {avgPLT && (
          <div className="industrial-card px-4 py-2 flex items-center gap-3">
            <div>
              <p className="label-caps text-[var(--text-muted)] mb-1">Avg Degradation Lead Time</p>
              <p className="text-[20px] font-bold font-data text-[var(--primary)]">{avgPLT}<span className="text-[12px] text-[var(--text-muted)] ml-1">hrs</span></p>
            </div>
            <span className="material-symbols-outlined text-[var(--primary)]">update</span>
          </div>
        )}
        <button onClick={() => fetchPredictions(plantId)} className="industrial-control text-[var(--safe-text)]">
          {predictionsLoading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* -- Main body split -- */}
      <div className="flex flex-1 overflow-hidden">

        {/* Timeline canvas */}
        <div className="flex-1 flex flex-col min-w-0 border-r border-[var(--border)] overflow-hidden">
          {/* Time axis */}
          <div className="h-10 border-b border-[var(--border)] flex flex-shrink-0 bg-[var(--bg-surface)]">
            <div className="w-48 shrink-0 border-r border-[var(--border)] px-4 flex items-center">
              <span className="label-caps text-[var(--text-muted)]">Sensor ID</span>
            </div>
            <div className="flex-1 flex items-end pb-1.5 px-2 justify-between">
              {['Now', '+2h', '+4h', '+6h', '+8h', '+10h', '+12h'].map((t) => (
                <span key={t} className="caption-mono text-[10px] text-[var(--text-dim)]">{t}</span>
              ))}
            </div>
          </div>

          {/* Timeline rows */}
          <div className="flex-1 overflow-y-auto scrollbar-thin relative">
            {/* Background grid */}
            <div className="absolute inset-0 left-48 timeline-grid opacity-30 pointer-events-none" />

            {rows.length === 0 && (
              <div className="p-8 text-center">
                <p className="caption-mono text-[var(--text-muted)]">
                  {predictionsLoading ? 'Loading predictions...' : 'Waiting for confidence history data.'}
                </p>
              </div>
            )}

            {rows.map((pred) => {
              const low  = Math.min(WINDOW_HOURS, pred.time_to_low_hours ?? WINDOW_HOURS);
              const crit = Math.min(WINDOW_HOURS, pred.time_to_critical_hours ?? WINDOW_HOURS);
              const isCrit = pred.time_to_critical_hours != null && pred.time_to_critical_hours < 4;
              const color = isCrit ? 'var(--critical)' : pred.time_to_low_hours != null ? 'var(--primary-dim)' : 'var(--text-dim)';

              return (
                <div key={pred.sensor_id}
                  className="flex h-16 border-b border-[var(--border-subtle)]/30 hover:bg-[var(--bg-surface)]/50 transition-colors group relative">
                  {/* Sensor label */}
                  <div className="w-48 shrink-0 border-r border-[var(--border)] px-4 flex items-center bg-[var(--bg-low)] z-10">
                    <div className="flex items-center gap-2">
                      <div className="status-pip" style={{ background: color }} />
                      <div>
                        <p className="font-data text-[14px] text-[var(--text)] group-hover:text-[var(--primary)] transition-colors">
                          {pred.sensor_id}
                        </p>
                        <p className="caption-mono text-[10px] text-[var(--text-muted)]">
                          {forecastLabel(pred)}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Track */}
                  <div className="flex-1 relative py-3 px-2 flex items-center">
                    <div className="absolute left-2 right-2 h-2 bg-[var(--bg-elevated)]/30 rounded-full top-1/2 -translate-y-1/2" />
                    {/* Forecast/status portion */}
                    <div className="absolute left-0 h-2 rounded-l-full top-1/2 -translate-y-1/2 transition-all"
                      style={{
                        width: pred.time_to_low_hours != null ? `${(low / WINDOW_HOURS) * 100}%` : '100%',
                        background: pred.time_to_low_hours != null ? color : 'var(--border)',
                      }}
                    />
                    {/* Probability corridor */}
                    {pred.time_to_low_hours != null && (
                      <div className="absolute h-7 rounded top-1/2 -translate-y-1/2 opacity-10"
                        style={{
                          left: `${(low / WINDOW_HOURS) * 100}%`,
                          width: `${Math.max(0, (crit - low) / WINDOW_HOURS) * 100}%`,
                          background: color,
                        }} />
                    )}
                    {/* TTC marker */}
                    {pred.time_to_critical_hours != null && (
                      <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 flex flex-col items-center z-10"
                        style={{ left: `${(crit / WINDOW_HOURS) * 100}%` }}>
                        <div className="w-3.5 h-3.5 rounded border-2 flex items-center justify-center rotate-45"
                          style={{ borderColor: color, background: 'var(--bg-card)' }}>
                          <div className="w-1 h-1 rounded-full" style={{ background: color }} />
                        </div>
                        <div className="absolute top-5 caption-mono text-[10px] whitespace-nowrap px-1 border rounded"
                          style={{ color, borderColor: `${color}50`, background: 'var(--bg-low)' }}>
                          TTC: {pred.time_to_critical_hours}h
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* -- Action queue & Confidence Debt sidebar -- */}
        <aside className="w-[360px] flex flex-col bg-[var(--bg-low)] shrink-0 overflow-y-auto scrollbar-thin p-4 gap-4">
          
          {/* Confidence Debt Ledger */}
          <ConfidenceDebtPanel />

          {/* Action queue */}
          <div className="industrial-card p-0 overflow-hidden">
            <div className="industrial-card-header px-4 py-3 border-b border-[var(--border)]">
              <h2 className="text-[14px] font-semibold text-[var(--text)] flex items-center gap-2">
                <span className="material-symbols-outlined text-[18px] text-[var(--primary)]">dynamic_form</span>
                Action Queue
              </h2>
            </div>
            <div className="p-4 space-y-3">
              {rows.filter((pred) => !pred.time_to_low_hours && !pred.time_to_critical_hours).slice(0, 3).map((pred) => (
                <div key={`${pred.sensor_id}-flat`} className="industrial-card p-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-data text-[13px] text-[var(--text)]">{pred.sensor_id}</p>
                    <ConfidenceBadge conf={pred.current_confidence} />
                  </div>
                  <p className="caption-mono text-[var(--data-mono)] mt-1">{forecastLabel(pred)}</p>
                  {forecastDetail(pred) && (
                    <p className="caption-mono text-[var(--text-dim)] mt-1">{forecastDetail(pred)}</p>
                  )}
                  <p className="caption-mono text-[var(--text-muted)] mt-1">{pred.recommended_action || pred.action}</p>
                </div>
              ))}
              {actionQueue.map((pred) => {
                const hours = pred.time_to_critical_hours ?? pred.time_to_low_hours;
                const isCrit = pred.time_to_critical_hours != null && pred.time_to_critical_hours < 4;
                const borderColor = isCrit ? 'var(--critical)' : 'var(--primary-dim)';
                const confColor   = isCrit ? 'var(--critical)' : 'var(--primary-dim)';
                return (
                  <div key={pred.sensor_id}
                    className="industrial-card relative overflow-hidden"
                    style={{ borderColor: `${borderColor}50` }}>
                    <div className="absolute top-0 left-0 w-1 h-full" style={{ background: borderColor }} />
                    <div className="pl-3 p-3">
                      <div className="flex justify-between items-start mb-1">
                        <span className="label-caps px-1.5 py-0.5 rounded"
                          style={{ color: confColor, background: `${confColor}1a` }}>
                          TTC: {hours != null ? `${isCrit ? '< 4h' : `~${hours}h`}` : '-'}
                        </span>
                        <ConfidenceBadge conf={pred.current_confidence} />
                      </div>
                      <h3 className="font-data text-[14px] text-[var(--text)] mt-2">
                        {isCrit ? 'Calibrate' : 'Inspect'} {pred.sensor_id}
                      </h3>
                      <p className="caption-mono text-[var(--text-muted)] text-[12px] mt-1 leading-snug">
                        {pred.recommended_action || pred.action || 'Confidence degradation context.'}
                      </p>
                      <div className="flex gap-2 mt-3">
                        <Link to="/runtime" className="flex-1 industrial-control inline-flex items-center justify-center text-[var(--text)] text-[11px] py-1.5">
                          Open Runtime
                        </Link>
                        <Link to="/handover" className="flex-1 industrial-control inline-flex items-center justify-center text-[var(--primary)] border-[var(--primary)] text-[11px] py-1.5">
                          Shift Debt
                        </Link>
                      </div>
                    </div>
                  </div>
                );
              })}
              {actionQueue.length === 0 && (
                <p className="caption-mono text-[var(--text-muted)] text-[12px]">
                  No sensors forecast to cross a lower trust tier. The panel shows deterministic confidence trend status, not predictive failure.
                </p>
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
