/**
 * views/FleetOverview.jsx - Instrument Integrity Overview
 *
 * Endpoints:
 *   GET /api/fleet          - fleet summary (auto-polls every 5s)
 *   GET /api/fleet/history  - 24h health trend data
 *
 * Secondary support view for instrument-integrity attention across plants.
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import useStore from '../store';
import { pctColor, TRUST_COLOR, chartGrid, axisTick, axisLine } from '../lib/chartTheme';
import PageIdentity from '../components/hmi/PageIdentity';

// Per-plant trend colors drawn from the shared NAMUR palette (distinct hues, on-token).
const PLANT_COLORS = { 'plant-a': TRUST_COLOR.CRITICAL, 'plant-b': TRUST_COLOR.MEDIUM, 'plant-c': TRUST_COLOR.HIGH };

const tierColor = pctColor;

function tierLabel(pct) {
  if (pct >= 80) return 'NORMAL';
  if (pct >= 50) return 'ATTENTION';
  if (pct >= 20) return 'LOW';
  return 'CRITICAL';
}

function tierBorderClass(pct) {
  if (pct >= 80) return 'border-[#8fd6ff]/40 hover:border-[#8fd6ff]';
  if (pct >= 50) return 'border-[var(--border-subtle)] hover:border-[var(--border)]';
  return 'border-[#ffb4ab]/50 hover:border-[#ffb4ab] glow-critical';
}

function IndustrialTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <p className="mb-2 label-caps text-[var(--text-muted)]">{label}</p>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="flex items-center gap-2 mt-1">
          <span className="led-square" style={{ color: entry.color }} />
          <span className="text-[var(--text)]">{entry.name || entry.dataKey}</span>
          <span className="ml-auto" style={{ color: entry.color }}>
            {typeof entry.value === 'number' ? entry.value.toFixed(1) : entry.value}%
          </span>
        </div>
      ))}
    </div>
  );
}

function TrendSnapshotFallback({ snapshot = [], status }) {
  if (!snapshot.length) {
    return (
      <div>
        <p className="caption-mono text-[var(--text-dim)]">Collecting confidence history. Trend appears after persisted samples accumulate.</p>
        <p className="caption-mono text-[var(--text-muted)] mt-2">Status: {status || 'insufficient_history'}</p>
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl">
      <p className="caption-mono text-[var(--text-dim)] mb-4">
        Current live snapshot only. No historical line is plotted until at least two persisted confidence buckets exist.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {snapshot.map((plant) => {
          const pct = Number(plant.health_pct ?? 0);
          const color = tierColor(pct);
          return (
            <div key={plant.plant_id} className="industrial-card px-4 py-3 text-left">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-[var(--text)] truncate">{plant.name || plant.plant_id}</p>
                  <p className="label-caps text-[var(--text-muted)] mt-1">{plant.plant_id}</p>
                </div>
                <span className="font-data text-[22px] font-bold" style={{ color }}>
                  {Number.isFinite(pct) ? `${Math.round(pct)}%` : '--'}
                </span>
              </div>
              <div className="h-2 bg-[var(--surface-base)] border border-[var(--border)] mt-3">
                <div className="h-full" style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: color }} />
              </div>
              <p className="caption-mono text-[var(--text-muted)] mt-2">
                {(plant.top_issues || [])[0] || 'No active operating question'}
              </p>
            </div>
          );
        })}
      </div>
      <p className="caption-mono text-[var(--text-muted)] mt-4">Status: {status || 'current_snapshot_only'}</p>
    </div>
  );
}

export default function FleetOverview() {
  const { fleetData, fleetLoading, fetchFleet, setPlantId } = useStore();
  const [trend, setTrend] = useState([]);
  const [trendMeta, setTrendMeta] = useState(null);
  const [trendError, setTrendError] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetchFleet();
    fetch('/api/fleet/history?hours=24')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => {
        setTrend(d.trend || []);
        setTrendMeta(d);
        setTrendError(false);
      })
      .catch(() => {
        setTrend([]);
        setTrendMeta(null);
        setTrendError(true);
      });
    const timer = setInterval(fetchFleet, 5000);
    return () => clearInterval(timer);
  }, [fetchFleet]);

  const openPlant = (id) => {
    setPlantId(id);
    navigate('/runtime');
  };

  const sorted = [...fleetData].sort((a, b) => a.health_pct - b.health_pct);
  const worst  = sorted[0];
  const best   = sorted[sorted.length - 1];
  const totalFlags = fleetData.reduce((s, p) => s + (p.top_issues?.length || 0), 0);
  const averageAttention = fleetData.length
    ? Math.round(fleetData.reduce((s, p) => s + Number(p.instrument_integrity_attention_score ?? p.attention_score ?? p.risk_score ?? 0), 0) / fleetData.length)
    : null;

  return (
    <div className="industrial-page flex flex-col overflow-hidden">
      <PageIdentity displayName="Instrument Integrity Overview" level={3} area="Real-time aggregate trust state across active facilities" />
      <div className="flex-1 overflow-y-auto scrollbar-thin overflow-x-hidden">
      <div className="p-8 space-y-8">

        {/* -- KPI chips -- */}
        <div className="flex justify-end items-start">
          <div className="flex gap-4">
            {/* Instrument integrity score */}
            <div className="industrial-card p-4 w-40">
              <p className="label-caps text-[var(--text-muted)] mb-2">Integrity</p>
              <div className="flex items-end gap-1">
                <span className="text-5xl font-bold leading-none" style={{ color: tierColor(fleetData[0]?.health_pct ?? 80) }}>
                  {fleetData.length
                    ? Math.round(fleetData.reduce((s, p) => s + p.health_pct, 0) / fleetData.length)
                    : '--'}
                </span>
                <span className="text-[20px] text-[var(--text-muted)] mb-1">%</span>
              </div>
            </div>
            {/* Active flags */}
            <div className="industrial-card p-4 w-40">
              <p className="label-caps text-[var(--text-muted)] mb-2">Attention</p>
              <div className="flex items-end gap-1">
                <span className="text-5xl font-bold leading-none text-[var(--primary)]">{averageAttention ?? '--'}</span>
                <span className="text-[20px] text-[var(--text-muted)] mb-1">/100</span>
              </div>
              <p className="caption-mono text-[var(--text-dim)] mt-2">sorting rubric, not a failure forecast</p>
            </div>
            <div className="industrial-card p-4 w-40">
              <p className="label-caps text-[var(--text-muted)] mb-2">Active Flags</p>
              <div className="flex items-end gap-1">
                <span className="text-5xl font-bold leading-none text-[var(--primary)]">{totalFlags}</span>
                <span className="material-symbols-outlined text-[var(--primary)] mb-1">flag</span>
              </div>
            </div>
          </div>
        </div>

        {/* -- Best / Worst banner -- */}
        {best && worst && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-1">
            <div className="bg-[var(--bg-card)] border border-[var(--border-subtle)] px-4 py-2 flex items-center justify-between rounded-l">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[var(--text-muted)] text-[18px]">workspace_premium</span>
                <span className="label-caps text-[var(--text-muted)]">Top Performer</span>
              </div>
              <span className="font-data text-[14px] text-[var(--text)]">{best.name} ({best.health_pct}%)</span>
            </div>
            <div className="bg-[rgba(147,0,10,0.12)] border border-[#ffb4ab]/30 px-4 py-2 flex items-center justify-between rounded-r glow-critical">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[var(--critical)] text-[18px]">warning</span>
                <span className="label-caps text-[var(--critical)]">Lowest Integrity</span>
              </div>
              <span className="font-data text-[14px] text-[var(--critical)]">{worst.name} ({worst.health_pct}%)</span>
            </div>
          </div>
        )}

        {/* -- Plant integrity cards -- */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {fleetData.map((plant) => {
            const color = tierColor(plant.health_pct);
            const label = tierLabel(plant.health_pct);
            const border = tierBorderClass(plant.health_pct);
            const history = trend.filter((point) => point[plant.plant_id] != null).slice(-16);
            const points = history.map((point, index) => {
              const x = history.length <= 1 ? 0 : (index / (history.length - 1)) * 100;
              const y = 30 - (Math.max(0, Math.min(100, Number(point[plant.plant_id]))) / 100) * 28;
              return `${x.toFixed(1)},${y.toFixed(1)}`;
            }).join(' ');
            return (
              <button
                key={plant.plant_id}
                onClick={() => openPlant(plant.plant_id)}
                className={`text-left bg-[var(--bg-card)] border ${border} rounded p-4 flex flex-col gap-4 relative overflow-hidden group transition-colors`}
              >
                {/* glow accent */}
                {plant.health_pct < 50 && (
                  <div className="absolute top-0 right-0 w-16 h-16 blur-xl rounded-full -mr-8 -mt-8 pointer-events-none"
                    style={{ background: 'rgba(255,180,171,0.15)' }} />
                )}

                {/* Name + badge */}
                <div className="flex justify-between items-start">
                  <div>
                    <p className="text-[18px] font-semibold text-[var(--text)]">{plant.name}</p>
                    <p className="label-caps text-[var(--text-muted)] mt-1">{plant.plant_id?.toUpperCase()}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className="industrial-badge" style={{ color, borderColor: color }}>
                      <span className="status-pip" style={{ background: color }} />
                      {label}
                    </span>
                    <span className="text-[20px] font-bold font-data mt-1" style={{ color }}>{plant.health_pct}%</span>
                    <span className="caption-mono text-[var(--text-muted)]">
                      attention {plant.instrument_integrity_attention_score ?? plant.attention_score ?? plant.risk_score ?? '--'}/100
                    </span>
                  </div>
                </div>

                {/* Top alerts */}
                <div>
                  <p className="label-caps text-[var(--text-dim)] mb-2">Operating Questions</p>
                  {(plant.top_issues || []).slice(0, 3).map((issue) => (
                    <div key={issue} className="flex items-center justify-between py-1 border-b border-[var(--border-subtle)]">
                      <span className="font-data text-[13px]" style={{ color }}>{issue.split(':')[0]}</span>
                      <span className="text-[12px] text-[var(--text-muted)]">{issue.split(':')[1] || ''}</span>
                    </div>
                  ))}
                  {(!plant.top_issues || plant.top_issues.length === 0) && (
                    <div className="flex items-center justify-between py-1 border-b border-[var(--border-subtle)] opacity-50">
                      <span className="font-data text-[13px] text-[var(--text-muted)]">--</span>
                      <span className="text-[12px] text-[var(--text-muted)]">No active flags</span>
                    </div>
                  )}
                </div>

                {/* Sparkline */}
                <div className="mt-auto pt-2 h-16 w-full relative">
                  <p className="label-caps text-[var(--text-dim)] absolute top-0 left-0">4H Trend</p>
                  {points ? (
                    <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 100 30">
                      <polyline fill="none" points={points} stroke={color} strokeWidth="1.5" />
                    </svg>
                  ) : (
                    <p className="caption-mono text-[var(--text-muted)] pt-7">Collecting history</p>
                  )}
                </div>
              </button>
            );
          })}
          {fleetLoading && fleetData.length === 0 && (
            <div className="col-span-3 industrial-card p-8 text-center">
              <p className="label-caps text-[var(--text-muted)]">Loading fleet data...</p>
            </div>
          )}
        </div>

        {/* -- 24h fleet health trend chart -- */}
        <div className="industrial-card p-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-[18px] font-semibold text-[var(--text)]">24h Instrument Integrity Trend</h2>
            <div className="flex gap-4">
              <span className="caption-mono text-[var(--text-muted)]" title="Provenance of this trend">
                {trendError
                  ? 'trend fetch failed'
                  : `source: ${trendMeta?.source || 'confidence_logs'} / ${trendMeta?.sample_count ?? 0} samples / ${trendMeta?.bucket_minutes ?? 15}-min buckets / ${trendMeta?.status || 'unknown'}`}
              </span>
              {Object.entries(PLANT_COLORS).map(([pid, color]) => (
                <div key={pid} className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full" style={{ background: color }} />
                  <span className="label-caps text-[var(--text-muted)]">{pid}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="h-[260px] border-l border-b border-[var(--border-subtle)]">
            {trendError ? (
              <div className="h-full grid place-items-center text-center px-6">
                <div>
                  <p className="caption-mono status-warning">Instrument integrity trend unavailable</p>
                  <p className="caption-mono text-[var(--text-dim)] mt-1">Could not load /api/fleet/history. Live fleet cards above are unaffected.</p>
                </div>
              </div>
            ) : trend.length === 0 ? (
              <div className="h-full grid place-items-center text-center px-6">
                <TrendSnapshotFallback snapshot={trendMeta?.current_snapshot || fleetData} status={trendMeta?.status} />
              </div>
            ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trend} margin={{ top: 16, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid {...chartGrid} strokeDasharray="4 2" />
                <XAxis dataKey="timestamp"
                  tick={{ ...axisTick, fontSize: 10 }}
                  axisLine={axisLine} tickLine={false} minTickGap={40} />
                <YAxis domain={[0, 100]}
                  tick={{ ...axisTick, fontSize: 10 }}
                  axisLine={false} tickLine={false} />
                <Tooltip content={<IndustrialTooltip />} />
                {Object.entries(PLANT_COLORS).map(([pid, color]) => (
                  <Line key={pid} type="monotone" dataKey={pid} name={pid} dot={false}
                    stroke={color} strokeWidth={2} isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
            )}
          </div>
        </div>

      </div>
      </div>
    </div>
  );
}
