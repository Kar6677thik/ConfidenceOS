import { useEffect, useMemo, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { chartColors, chartGrid, axisTick, axisLine, TRUST_COLOR } from '../lib/chartTheme';

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;

  return (
    <div className="chart-tooltip">
      <p className="mb-2 text-[var(--data-mono)]">{label}</p>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2">
          <span className="led-square" style={{ color: entry.color }} />
          <span>{entry.name}</span>
          <span className="ml-auto text-[var(--text)]">
            {typeof entry.value === 'number' ? entry.value.toFixed(2) : '--'} ft
          </span>
        </div>
      ))}
    </div>
  );
}

function StatBlock({ label, value, unit, className = '' }) {
  return (
    <div className="industrial-panel-subtle p-3 text-center">
      <p className="label-caps text-[var(--text-muted)]">{label}</p>
      <p className={`font-data text-2xl font-bold ${className}`}>{value != null ? value.toFixed(1) : '--'}</p>
      <p className="caption-mono text-[var(--data-mono)]">{unit}</p>
    </div>
  );
}

export default function MassBalanceChart({ chartHistory, massBalance, flags }) {
  const currentImplied = massBalance?.implied_level;
  const currentMeasured = massBalance?.measured_level;   // what the sensor indicates
  const currentActual = massBalance?.actual_level;       // physically-true level (ground truth)
  const currentDiscrepancy = massBalance?.discrepancy;
  const hasActual = currentActual != null;

  const flagList = useMemo(() => flags || massBalance?.flags || [], [flags, massBalance?.flags]);
  const [nowSeconds, setNowSeconds] = useState(() => Date.now() / 1000);

  useEffect(() => {
    const timer = window.setInterval(() => setNowSeconds(Date.now() / 1000), 30000);
    return () => window.clearInterval(timer);
  }, []);

  const highestSeverity = useMemo(() => {
    if (flagList.length === 0) return null;
    if (flagList.some((flag) => flag.severity === 'CRITICAL')) return 'CRITICAL';
    if (flagList.some((flag) => flag.severity === 'WARNING')) return 'WARNING';
    return 'INFO';
  }, [flagList]);

  // How long the physics has disagreed: earliest active flag to now.
  const divergenceMinutes = useMemo(() => {
    if (!flagList.length) return null;
    const stamps = flagList.map((f) => f.timestamp).filter((t) => typeof t === 'number');
    if (!stamps.length) return null;
    const oldest = Math.min(...stamps);
    const secs = nowSeconds - (oldest > 1e10 ? oldest / 1000 : oldest);
    return secs > 0 ? Math.round(secs / 60) : 0;
  }, [flagList, nowSeconds]);

  const yDomain = useMemo(() => {
    if (!chartHistory || chartHistory.length === 0) return ['auto', 'auto'];
    const allVals = chartHistory.flatMap((point) => [point.implied, point.measured, point.actual].filter((value) => value != null));
    if (allVals.length === 0) return ['auto', 'auto'];
    const min = Math.min(...allVals);
    const max = Math.max(...allVals);
    const pad = Math.max((max - min) * 0.15, 2);
    return [Math.floor(min - pad), Math.ceil(max + pad)];
  }, [chartHistory]);

  const severityClass = highestSeverity === 'CRITICAL'
    ? 'status-critical'
    : highestSeverity === 'WARNING'
    ? 'status-warning'
    : 'status-safe';

  return (
    <section className="industrial-panel h-full flex flex-col">
      <div className="industrial-panel-header">
        <h2 className="industrial-panel-title">Physics vs the Sensor: Implied Level vs Indicated Level</h2>
        {highestSeverity && (
          <span className={`industrial-badge ${severityClass}`}>{highestSeverity}</span>
        )}
      </div>

      <div className="industrial-body flex flex-col min-h-0 flex-1">
        {highestSeverity && divergenceMinutes != null && (
          <p className={`caption-mono mb-3 ${severityClass}`}>
            Physics has disagreed with the indicated level for ~{divergenceMinutes} min - the reading is not tracking the flow-implied inventory.
          </p>
        )}
        <div className={`grid ${hasActual ? 'grid-cols-2 md:grid-cols-4' : 'grid-cols-3'} gap-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)] mb-4`}>
          <StatBlock label="Implied (flow)" value={currentImplied} unit="ft" className="text-[var(--data-mono)]" />
          <StatBlock label="Indicated (sensor)" value={currentMeasured} unit="ft" className="text-[var(--primary)]" />
          {hasActual && (
            <StatBlock label="Actual (true)" value={currentActual} unit="ft" className="text-[var(--safe)]" />
          )}
          <StatBlock
            label="Delta"
            value={currentDiscrepancy}
            unit="ft"
            className={currentDiscrepancy > 5 ? 'status-critical' : currentDiscrepancy > 2 ? 'status-warning' : 'text-[var(--text)]'}
          />
        </div>

        <div className="h-[300px] w-full shrink-0 border border-[var(--border-strong)] bg-[var(--surface-base)]" style={{ minWidth: 0 }}>
          {chartHistory && chartHistory.length > 1 ? (
            <ResponsiveContainer width="100%" height="100%" minWidth={0} debounce={80}>
              <LineChart data={chartHistory} margin={{ top: 22, right: 24, left: 0, bottom: 14 }}>
                <CartesianGrid {...chartGrid} />
                <XAxis
                  dataKey="time"
                  tick={axisTick}
                  axisLine={axisLine}
                  tickLine={false}
                  minTickGap={48}
                />
                <YAxis
                  domain={yDomain}
                  tick={axisTick}
                  axisLine={axisLine}
                  tickLine={false}
                  width={44}
                />
                <Tooltip content={<ChartTooltip />} />
                <Line type="monotone" dataKey="implied" name="Implied (from flow)" stroke={chartColors.muted} strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="measured" name="Indicated (sensor)" stroke={chartColors.primary} strokeWidth={4} dot={false} isAnimationActive={false} />
                {hasActual && (
                  <Line type="monotone" dataKey="actual" name="Actual (true)" stroke={TRUST_COLOR.HIGH} strokeWidth={2} strokeDasharray="2 2" dot={false} isAnimationActive={false} />
                )}
                <Line type="monotone" dataKey="discrepancy" name="Discrepancy" stroke={TRUST_COLOR.LOW} strokeWidth={1.5} strokeDasharray="4 4" dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full grid place-items-center caption-mono text-[var(--data-mono)] text-center p-4">
              <div>
                <p className="font-semibold">Waiting for mass-balance history</p>
                <p className="text-[var(--text-muted)] mt-1">
                  {chartHistory?.length || 0} sample(s) available. Start the judge demo or wait for the live simulator stream to produce at least two samples.
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-5 mt-3 caption-mono">
          <span className="flex items-center gap-2"><span className="led-square text-[var(--data-mono)]" /> Implied Level</span>
          <span className="flex items-center gap-2"><span className="led-square status-safe" /> Actual Level</span>
          <span className="flex items-center gap-2"><span className="led-square status-warning" /> Discrepancy</span>
        </div>

        {highestSeverity && massBalance?.flags?.[0] && (
          <div className={`mt-3 border p-3 caption-mono ${severityClass}`} style={{ borderColor: 'currentColor' }}>
            {massBalance.flags[0].message}
          </div>
        )}

        {/* Honest method + engineer-owned parameters (no hidden magic numbers). */}
        {massBalance?.config && (
          <p className="mt-3 caption-mono text-[var(--text-dim)] leading-relaxed">
            Configurable single-vessel volumetric residual check / tolerance {massBalance.config.tolerance} ft /
            flow{'->'}level {massBalance.config.flow_to_level_rate} / {massBalance.config.assumptions}
          </p>
        )}
      </div>
    </section>
  );
}
