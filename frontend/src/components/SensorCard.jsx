/**
 * SensorCard — PRD §5.2 Confidence Indicator Widget
 *
 * The visual core of ConfidenceOS. Shows:
 *   1. Raw reading value + unit
 *   2. Animated confidence bar (green→amber→orange→red)
 *   3. Confidence percentage
 *   4. One-line primary reason string
 *   5. Click to select (feeds HealthTimeline)
 */

// Tier → color scheme mapping
const TIER_COLORS = {
  HIGH:     { bar: 'from-emerald-500 to-emerald-400', border: 'border-emerald-500/30', glow: 'shadow-emerald-500/10', text: 'text-emerald-400', bg: 'bg-emerald-500/5',  dot: 'bg-emerald-400' },
  MEDIUM:   { bar: 'from-amber-500 to-yellow-400',    border: 'border-amber-500/30',   glow: 'shadow-amber-500/10',   text: 'text-amber-400',   bg: 'bg-amber-500/5',    dot: 'bg-amber-400'   },
  LOW:      { bar: 'from-orange-500 to-orange-400',    border: 'border-orange-500/30',  glow: 'shadow-orange-500/10',  text: 'text-orange-400',  bg: 'bg-orange-500/5',   dot: 'bg-orange-400'  },
  CRITICAL: { bar: 'from-red-600 to-red-400',          border: 'border-red-500/40',     glow: 'shadow-red-500/15',     text: 'text-red-400',     bg: 'bg-red-500/8',      dot: 'bg-red-400'     },
};

// Sensor type → display info
const SENSOR_LABELS = {
  level:       { label: 'Level',       icon: '📊' },
  flow_in:     { label: 'Inflow',      icon: '↗️' },
  flow_out:    { label: 'Outflow',     icon: '↘️' },
  pressure:    { label: 'Pressure',    icon: '🔴' },
  temperature: { label: 'Temperature', icon: '🌡️' },
  valve:       { label: 'Valve Pos.',  icon: '🔧' },
};

export default function SensorCard({ reading, confidence, isSelected, onSelect }) {
  if (!reading || !confidence) return null;

  const tier = confidence.tier || 'HIGH';
  const pct = confidence.confidence_pct ?? 100;
  const colors = TIER_COLORS[tier] || TIER_COLORS.HIGH;
  const sensorInfo = SENSOR_LABELS[reading.sensor_type] || { label: reading.sensor_type, icon: '📡' };

  // Primary reason string (first reason, truncated)
  const primaryReason = confidence.reasons?.[0] || 'All checks nominal.';

  return (
    <button
      onClick={() => onSelect?.(reading.sensor_id)}
      className={`
        group relative w-full text-left
        bg-gray-900/60 backdrop-blur-xl
        border ${isSelected ? 'border-cyan-500/60 ring-1 ring-cyan-500/20' : colors.border}
        rounded-2xl p-4
        shadow-lg ${colors.glow}
        hover:border-cyan-500/40 hover:shadow-xl
        transition-all duration-300 cursor-pointer
        focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500
      `}
      aria-label={`Sensor ${reading.sensor_id}: ${reading.value} ${reading.unit}, confidence ${pct}%`}
    >
      {/* Header: sensor ID + type */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-base">{sensorInfo.icon}</span>
          <span className="text-xs font-mono font-bold text-gray-300 tracking-wide">
            {reading.sensor_id}
          </span>
        </div>
        <span className={`text-[10px] font-semibold uppercase tracking-wider ${colors.text}`}>
          {tier}
        </span>
      </div>

      {/* Reading value */}
      <div className="flex items-baseline gap-2 mb-3">
        <span className="text-2xl font-extrabold text-gray-100 tabular-nums tracking-tight">
          {typeof reading.value === 'number' ? reading.value.toFixed(1) : '—'}
        </span>
        <span className="text-xs font-medium text-gray-500 uppercase">
          {reading.unit}
        </span>
      </div>

      {/* Confidence bar */}
      <div className="mb-2">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] text-gray-500 font-medium uppercase tracking-wider">
            Confidence
          </span>
          <span className={`text-xs font-bold tabular-nums ${colors.text}`}>
            {pct.toFixed(0)}%
          </span>
        </div>
        <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full bg-gradient-to-r ${colors.bar} transition-all duration-700 ease-out`}
            style={{ width: `${Math.max(2, pct)}%` }}
          />
        </div>
      </div>

      {/* Sub-scores mini indicators */}
      {confidence.sub_scores && (
        <div className="flex gap-1.5 mb-2.5">
          {[
            { key: 'calibration', label: 'CAL' },
            { key: 'stability', label: 'STB' },
            { key: 'cross_sensor', label: 'XSN' },
            { key: 'physical_plausibility', label: 'PHY' },
          ].map(({ key, label }) => {
            const val = confidence.sub_scores[key] ?? 1;
            const subColor = val >= 0.8 ? 'text-emerald-500' : val >= 0.5 ? 'text-amber-500' : 'text-red-500';
            return (
              <span
                key={key}
                className={`text-[9px] font-mono font-semibold ${subColor} opacity-70`}
                title={`${label}: ${(val * 100).toFixed(0)}%`}
              >
                {label}
              </span>
            );
          })}
        </div>
      )}

      {/* Primary reason */}
      <p className="text-[11px] text-gray-500 leading-snug line-clamp-2 group-hover:text-gray-400 transition-colors">
        {primaryReason}
      </p>

      {/* Selection indicator */}
      {isSelected && (
        <div className="absolute top-2 right-2">
          <span className="inline-block h-2 w-2 rounded-full bg-cyan-400 shadow-sm shadow-cyan-400/50 animate-pulse" />
        </div>
      )}
    </button>
  );
}
