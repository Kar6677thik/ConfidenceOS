const TIER_META = {
  HIGH: {
    label: 'NOMINAL',
    className: 'status-safe',
    stroke: '#00FF41',
    points: '0,58 16,56 32,57 48,55 64,56 80,55 100,55',
  },
  MEDIUM: {
    label: 'DEGRADED',
    className: 'status-caution',
    stroke: '#FFD700',
    points: '0,56 16,55 32,51 48,47 64,46 80,42 100,40',
  },
  LOW: {
    label: 'LOW',
    className: 'status-warning',
    stroke: '#FFA500',
    points: '0,45 16,43 32,48 48,42 64,52 80,58 100,62',
  },
  CRITICAL: {
    label: 'CRITICAL',
    className: 'status-critical',
    stroke: '#FF0000',
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

const NAMUR_CLASS = {
  NORMAL: 'status-safe',
  MAINTENANCE_REQUIRED: 'status-caution',
  OUT_OF_SPECIFICATION: 'status-warning',
  FAILURE: 'status-critical',
  FUNCTION_CHECK: 'status-warning',
};

function getNamurLabel(pct) {
  if (pct < 20) return 'Failure (F)';
  if (pct < 50) return 'Out of Specification (S)';
  if (pct < 80) return 'Maintenance Required (M)';
  return 'Function Check (C)';
}

function getNamurClass(pct) {
  if (pct < 20) return 'status-critical';
  if (pct < 50) return 'status-warning';
  if (pct < 80) return 'status-caution';
  return 'status-safe';
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
  const namurLabel = getNamurLabel(pct);
  const namurClass = getNamurClass(pct);

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
        {confidence.sub_scores && (
          <div className="grid grid-cols-4 gap-1 caption-mono">
            {[
              ['CAL', confidence.sub_scores.calibration],
              ['STB', confidence.sub_scores.stability],
              ['XSN', confidence.sub_scores.cross_sensor],
              ['PHY', confidence.sub_scores.physical_plausibility],
            ].map(([label, val]) => {
              const cls = val >= 0.8 ? 'status-safe' : val >= 0.5 ? 'status-caution' : 'status-critical';
              return (
                <span key={label} className={`${cls} opacity-80`}>
                  {label}:{val != null ? Math.round(val * 100) : '--'}
                </span>
              );
            })}
          </div>
        )}
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
