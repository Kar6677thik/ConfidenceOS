import { useMemo } from 'react';
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
} from 'recharts';

/**
 * MassBalanceChart — The "star of the demo" (PRD §4.3 / §5.1 center panel)
 *
 * Three live lines:
 *   - Implied level (cyan, from flow integration)
 *   - Measured level (emerald, from LT sensor)
 *   - Discrepancy area (red/orange fill between the two)
 *
 * Plus active flag indicators.
 */

// Custom tooltip
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;

  return (
    <div className="bg-gray-900/95 backdrop-blur-xl border border-gray-700/60 rounded-xl px-4 py-3 shadow-2xl">
      <p className="text-[10px] text-gray-500 font-mono mb-2">{label}</p>
      {payload.map((entry, idx) => (
        <div key={idx} className="flex items-center gap-2 mb-0.5">
          <span
            className="inline-block w-2.5 h-2.5 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-xs text-gray-400">{entry.name}:</span>
          <span className="text-xs font-bold text-gray-200 tabular-nums">
            {typeof entry.value === 'number' ? entry.value.toFixed(2) : '—'} ft
          </span>
        </div>
      ))}
    </div>
  );
}

// Custom legend
function ChartLegend() {
  const items = [
    { color: '#22d3ee', label: 'Implied Level (flows)' },
    { color: '#34d399', label: 'Measured Level (LT)' },
    { color: '#f97316', label: 'Discrepancy' },
  ];

  return (
    <div className="flex items-center justify-center gap-5 mt-3">
      {items.map(({ color, label }) => (
        <div key={label} className="flex items-center gap-1.5">
          <span
            className="inline-block w-2.5 h-0.5 rounded-full"
            style={{ backgroundColor: color }}
          />
          <span className="text-[10px] text-gray-500 font-medium">{label}</span>
        </div>
      ))}
    </div>
  );
}

export default function MassBalanceChart({ chartHistory, massBalance, flags }) {
  // Current values for the stat cards
  const currentImplied = massBalance?.implied_level;
  const currentMeasured = massBalance?.measured_level;
  const currentDiscrepancy = massBalance?.discrepancy;

  // Highest active flag severity
  const highestSeverity = useMemo(() => {
    const flagList = flags || massBalance?.flags || [];
    if (flagList.length === 0) return null;
    if (flagList.some(f => f.severity === 'CRITICAL')) return 'CRITICAL';
    if (flagList.some(f => f.severity === 'WARNING')) return 'WARNING';
    return 'INFO';
  }, [flags, massBalance?.flags]);

  const severityColor = {
    CRITICAL: 'text-red-400 border-red-500/40 bg-red-500/10',
    WARNING: 'text-amber-400 border-amber-500/40 bg-amber-500/10',
    INFO: 'text-blue-400 border-blue-500/40 bg-blue-500/10',
  };

  // Y-axis domain: auto but with some padding
  const yDomain = useMemo(() => {
    if (!chartHistory || chartHistory.length === 0) return ['auto', 'auto'];
    const allVals = chartHistory.flatMap(d => [d.implied, d.measured].filter(v => v != null));
    if (allVals.length === 0) return ['auto', 'auto'];
    const min = Math.min(...allVals);
    const max = Math.max(...allVals);
    const pad = Math.max((max - min) * 0.15, 2);
    return [Math.floor(min - pad), Math.ceil(max + pad)];
  }, [chartHistory]);

  return (
    <div className="bg-gray-900/60 backdrop-blur-xl border border-gray-700/50 rounded-2xl shadow-2xl p-5 w-full h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-bold tracking-wide text-gray-200 uppercase">
          Mass-Balance Cross-Check
        </h2>
        {highestSeverity && (
          <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full border ${severityColor[highestSeverity]}`}>
            {highestSeverity}
          </span>
        )}
      </div>

      {/* Stat cards row */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-gray-800/50 rounded-xl p-3 text-center">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Implied</p>
          <p className="text-lg font-bold text-cyan-400 tabular-nums">
            {currentImplied != null ? currentImplied.toFixed(1) : '—'}
          </p>
          <p className="text-[10px] text-gray-600">ft</p>
        </div>
        <div className="bg-gray-800/50 rounded-xl p-3 text-center">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Measured</p>
          <p className="text-lg font-bold text-emerald-400 tabular-nums">
            {currentMeasured != null ? currentMeasured.toFixed(1) : '—'}
          </p>
          <p className="text-[10px] text-gray-600">ft</p>
        </div>
        <div className="bg-gray-800/50 rounded-xl p-3 text-center">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Discrepancy</p>
          <p className={`text-lg font-bold tabular-nums ${
            currentDiscrepancy != null && currentDiscrepancy > 5 ? 'text-red-400' :
            currentDiscrepancy != null && currentDiscrepancy > 2 ? 'text-amber-400' :
            'text-gray-300'
          }`}>
            {currentDiscrepancy != null ? currentDiscrepancy.toFixed(2) : '—'}
          </p>
          <p className="text-[10px] text-gray-600">ft</p>
        </div>
      </div>

      {/* Chart */}
      <div className="flex-1 min-h-[280px]">
        {chartHistory && chartHistory.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartHistory} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
              <XAxis
                dataKey="time"
                tick={{ fontSize: 9, fill: '#6b7280' }}
                axisLine={{ stroke: '#374151' }}
                tickLine={false}
                interval="preserveStartEnd"
                minTickGap={40}
              />
              <YAxis
                domain={yDomain}
                tick={{ fontSize: 9, fill: '#6b7280' }}
                axisLine={{ stroke: '#374151' }}
                tickLine={false}
                width={40}
              />
              <Tooltip content={<ChartTooltip />} />

              {/* Implied level (cyan) */}
              <Line
                type="monotone"
                dataKey="implied"
                name="Implied Level"
                stroke="#22d3ee"
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 4, fill: '#22d3ee' }}
                isAnimationActive={false}
              />

              {/* Measured level (emerald) */}
              <Line
                type="monotone"
                dataKey="measured"
                name="Measured Level"
                stroke="#34d399"
                strokeWidth={2.5}
                dot={false}
                activeDot={{ r: 4, fill: '#34d399' }}
                isAnimationActive={false}
              />

              {/* Discrepancy (orange, dashed) */}
              <Line
                type="monotone"
                dataKey="discrepancy"
                name="Discrepancy"
                stroke="#f97316"
                strokeWidth={1.5}
                strokeDasharray="4 4"
                dot={false}
                activeDot={{ r: 3, fill: '#f97316' }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-600 text-sm">
            <div className="text-center">
              <div className="relative inline-block mb-3">
                <div className="h-8 w-8 rounded-full border-2 border-gray-700" />
                <div className="absolute top-0 left-0 h-8 w-8 rounded-full border-2 border-t-cyan-400 animate-spin" />
              </div>
              <p>Waiting for data stream…</p>
            </div>
          </div>
        )}
      </div>

      <ChartLegend />

      {/* Active flag message */}
      {highestSeverity && massBalance?.flags?.[0] && (
        <div className={`mt-3 px-3 py-2 rounded-lg border text-xs ${severityColor[highestSeverity]}`}>
          {massBalance.flags[0].message}
        </div>
      )}
    </div>
  );
}
