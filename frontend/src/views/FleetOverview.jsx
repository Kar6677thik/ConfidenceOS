/**
 * views/FleetOverview.jsx - Instrument Integrity Overview
 *
 * Endpoints:
 *   GET /api/fleet          - fleet summary (auto-polls every 5s)
 *   GET /api/fleet/history  - 24h health trend data
 *
 * Stitch mockup: 1fleet_overview.html
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

export default function FleetOverview() {
  const { fleetData, fleetLoading, fetchFleet, setPlantId } = useStore();
  const [trend, setTrend] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    fetchFleet();
    fetch('/api/fleet/history?hours=24')
      .then((r) => r.json())
      .then((d) => setTrend(d.trend || []))
      .catch(() => setTrend([]));
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
                  <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 100 30">
                    <polyline
                      fill="none"
                      points={plant.health_pct < 50
                        ? '0,10 15,12 30,18 50,24 65,20 80,26 100,25'
                        : plant.health_pct < 80
                        ? '0,12 20,10 40,15 60,12 80,18 100,16'
                        : '0,8 20,9 40,7 60,9 80,7 100,8'}
                      stroke={color}
                      strokeWidth="1.5"
                    />
                    <defs>
                      <linearGradient id={`grad-${plant.plant_id}`} x1="0" x2="0" y1="0" y2="1">
                        <stop offset="0%" stopColor={color} stopOpacity="0.4" />
                        <stop offset="100%" stopColor={color} stopOpacity="0" />
                      </linearGradient>
                    </defs>
                  </svg>
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
              {Object.entries(PLANT_COLORS).map(([pid, color]) => (
                <div key={pid} className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full" style={{ background: color }} />
                  <span className="label-caps text-[var(--text-muted)]">{pid}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="h-[260px] border-l border-b border-[var(--border-subtle)]">
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
          </div>
        </div>

      </div>
      </div>
    </div>
  );
}
