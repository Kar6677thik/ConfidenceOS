/**
 * TrendSparkline — embedded trend from existing store data.
 *
 * ABB guideline: embedded trends for key parameters with timeframe label
 * and current-value dot. Uses existing chartHistory/confidence history —
 * no new endpoints. data items may be numbers or {value} / {y} objects.
 */
import { trustColor } from '../../lib/chartTheme';
import { formatLiveValue } from '../../lib/hmiFormat';

export default function TrendSparkline({
  data,
  tier = 'HIGH',
  currentValue,
  unit,
  timeframeLabel = '1h',
  width = 100,
  height = 40,
  className = '',
}) {
  const stroke = trustColor(tier);

  if (!data || data.length < 2) {
    return (
      <div
        className={`hmi-value-cell flex items-center justify-center ${className}`}
        style={{ width, height, minWidth: width }}
        aria-hidden="true"
      >
        <span className="caption-mono text-[var(--text-dim)] text-[10px]">—</span>
      </div>
    );
  }

  const values = data.map((d) =>
    typeof d === 'number' ? d : (d?.value ?? d?.y ?? 0)
  );
  const min   = Math.min(...values);
  const max   = Math.max(...values);
  const range = max - min || 1;

  const pad   = 4;
  const plotW = width - pad * 2;
  const plotH = height - pad * 2;

  const points = values
    .map((v, i) => {
      const x = pad + (i / (values.length - 1)) * plotW;
      const y = pad + (1 - (v - min) / range) * plotH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  const lastX = pad + plotW;
  const lastY = pad + (1 - (values[values.length - 1] - min) / range) * plotH;

  return (
    <div className={`relative flex-shrink-0 ${className}`} style={{ width, height }}>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        aria-hidden="true"
        style={{ display: 'block' }}
      >
        <polyline fill="none" points={points} stroke={stroke} strokeWidth={1.5} opacity={0.85} />
        <circle cx={lastX} cy={lastY} r={2.5} fill={stroke} />
      </svg>
      <div className="absolute bottom-0 right-0 left-0 flex items-center justify-between px-1 pb-0.5 pointer-events-none">
        {currentValue != null && (
          <span className="caption-mono text-[10px] leading-none" style={{ color: stroke }}>
            {formatLiveValue(currentValue)}{unit ? ` ${unit}` : ''}
          </span>
        )}
        <span className="caption-mono text-[10px] leading-none text-[var(--text-dim)] ml-auto">
          {timeframeLabel}
        </span>
      </div>
    </div>
  );
}
