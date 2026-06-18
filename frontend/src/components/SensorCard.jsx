import { trustColor } from '../lib/chartTheme';

// Sparkline stroke colors are sourced from the NAMUR design tokens (chartTheme),
// not hardcoded - so the card matches the rest of the trust palette.
const TIER_META = {
  HIGH: {
    label: 'NOMINAL',
    className: 'status-safe',
    stroke: trustColor('HIGH'),
    points: '0,58 16,56 32,57 48,55 64,56 80,55 100,55',
  },
  MEDIUM: {
    label: 'DEGRADED',
    className: 'status-caution',
    stroke: trustColor('MEDIUM'),
    points: '0,56 16,55 32,51 48,47 64,46 80,42 100,40',
  },
  LOW: {
    label: 'LOW',
    className: 'status-warning',
    stroke: trustColor('LOW'),
    points: '0,45 16,43 32,48 48,42 64,52 80,58 100,62',
  },
  CRITICAL: {
    label: 'CRITICAL',
    className: 'status-critical',
    stroke: trustColor('CRITICAL'),
    points: '0,45 18,40 36,55 54,32 72,74 100,82',
  },
};

const SENSOR_LABELS = {
  level: 'Level',
  flow_in: 'Inflow',
  flow_out: 'Outflow',
  pressure: 'Pressure',
  temperature: 'Temperature',
  valve: 'Valve Position',
};

// NAMUR NE107 diagnostic state - sourced from the confidence engine's `namur_state`
// (confidence.py:_namur_state), so the card and the engine agree instead of the card
// re-deriving its own label from the percentage.
const NAMUR_STATE_META = {
  NORMAL:               { label: 'Normal (N)',               className: 'status-safe' },
  MAINTENANCE_REQUIRED: { label: 'Maintenance Required (M)', className: 'status-caution' },
  OUT_OF_SPECIFICATION: { label: 'Out of Specification (S)', className: 'status-warning' },
  FUNCTION_CHECK:       { label: 'Function Check (C)',       className: 'status-warning' },
  FAILURE:              { label: 'Failure (F)',              className: 'status-critical' },
};

// Fallback only when the engine did not supply a namur_state (e.g. replay frames).
function namurFromPct(pct) {
  if (pct < 20) return 'FAILURE';
  if (pct < 50) return 'OUT_OF_SPECIFICATION';
  if (pct < 80) return 'MAINTENANCE_REQUIRED';
  return 'NORMAL';
}

export default function SensorCard({ reading, confidence, isSelected, onSelect }) {
  if (!reading || !confidence) return null;

  const tier = confidence.tier || 'HIGH';
  const pct = Math.round(confidence.confidence_pct ?? 100);
  const meta = TIER_META[tier] || TIER_META.HIGH;
  const primaryEvidence = confidence.evidence?.find((item) => item.status !== 'OK');
  const primaryReason = primaryEvidence?.message || confidence.reasons?.[0] || 'Operating within design threshold.';
  const value = typeof reading.value === 'number' ? reading.value.toFixed(1) : '--';
  const sensorType = SENSOR_LABELS[reading.sensor_type] || reading.sensor_type || 'Sensor';
  const namurState = confidence.namur_state || namurFromPct(pct);
  const namurMeta = NAMUR_STATE_META[namurState] || NAMUR_STATE_META.NORMAL;
  const namurLabel = namurMeta.label;
  const namurClass = namurMeta.className;

  return (
    <button
      onClick={() => onSelect?.(reading.sensor_id)}
      className={`
        relative h-[244px] w-full text-left overflow-hidden bg-[var(--surface-panel)]
        border ${isSelected ? 'border-[var(--safe)]' : tier === 'HIGH' ? 'border-[var(--border-subtle)]' : `border-current ${meta.className}`}
        p-5 flex flex-col gap-4 hover:bg-[var(--surface-elevated)] focus:outline-none focus-visible:border-[var(--safe)]
      `}
      aria-label={`Sensor ${reading.sensor_id}: ${value} ${reading.unit}, confidence ${pct}%`}
    >
      <div className={`absolute left-0 top-0 h-1 w-full ${tier === 'HIGH' ? 'bg-transparent' : ''}`} style={{ backgroundColor: tier === 'HIGH' ? 'transparent' : meta.stroke, opacity: 0.35 }} />

      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-data text-[14px] font-bold text-[var(--text)]">{reading.sensor_id}</p>
          <p className="label-caps text-[var(--data-mono)] mt-1">{sensorType}</p>
        </div>
        <span className={`industrial-badge ${meta.className}`}>
          {meta.label} {pct}%
        </span>
      </div>

      <div className="flex items-center justify-between gap-2">
        <span className={`industrial-badge ${namurClass}`}>{namurLabel}</span>
        <span className="caption-mono text-[var(--data-mono)]">{confidence.dominant_factor || 'none'}</span>
      </div>

      <div className="flex items-baseline gap-3">
        <span className={`font-data text-[56px] leading-none font-bold ${tier === 'CRITICAL' ? 'status-critical' : tier === 'LOW' ? 'status-warning' : tier === 'MEDIUM' ? 'status-caution' : 'text-[var(--text)]'}`}>
          {value}
        </span>
        <span className="font-data text-[15px] text-[var(--text-muted)]">{reading.unit}</span>
      </div>

      <div className="h-14 border border-[var(--border-strong)] bg-[var(--surface-elevated)] relative overflow-hidden">
        <div
          className="absolute bottom-0 left-0 h-1/2 w-full"
          style={{ backgroundColor: meta.stroke, opacity: tier === 'HIGH' ? 0.03 : 0.12 }}
        />
        <svg className="absolute inset-0 h-full w-full" preserveAspectRatio="none" viewBox="0 0 100 100" aria-hidden="true">
          <polyline fill="none" points={meta.points} stroke={meta.stroke} strokeWidth={tier === 'HIGH' ? 1.5 : 2.5} />
        </svg>
      </div>

      <div className="mt-auto space-y-2">
        {/* Always render the four evidence sub-scores — a degraded or derived
            signal must never show blank slots. Missing values read as '--'. */}
        <div className="grid grid-cols-2 gap-1 caption-mono">
          {[
            ['CAL', confidence.sub_scores?.calibration],
            ['STB', confidence.sub_scores?.stability],
            ['XSN', confidence.sub_scores?.cross_sensor],
            ['PHY', confidence.sub_scores?.physical_plausibility],
          ].map(([label, val]) => {
            const cls = val == null ? 'text-[var(--text-dim)]'
              : val >= 0.8 ? 'status-safe' : val >= 0.5 ? 'status-caution' : 'status-critical';
            return (
              <span key={label} className={`${cls} opacity-80 whitespace-nowrap`}>
                {label}:{val != null ? Math.round(val * 100) : '--'}
              </span>
            );
          })}
        </div>
        <p className={`caption-mono line-clamp-2 ${tier === 'CRITICAL' ? 'status-critical' : tier === 'LOW' ? 'status-warning' : 'text-[var(--data-mono)]'}`}>
          {primaryReason}
        </p>
        {confidence.recommended_action && tier !== 'HIGH' && (
          <p className="caption-mono line-clamp-1 status-safe">
            Action: {confidence.recommended_action}
          </p>
        )}
      </div>

      {isSelected && <div className="absolute right-0 top-0 h-full w-1 bg-[var(--safe)]" />}
    </button>
  );
}
