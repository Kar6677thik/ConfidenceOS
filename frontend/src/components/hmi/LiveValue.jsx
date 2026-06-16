/**
 * LiveValue — formatted live sensor/process value.
 *
 * ABB guideline: function code prefix, formatted number (decimal discipline),
 * unit suffix; rendered on --surface-value (lighter bg, per dark-bg rule).
 */
import { formatLiveValue } from '../../lib/hmiFormat';

export default function LiveValue({ value, unit, functionCode, className = '' }) {
  const formatted = formatLiveValue(value);
  return (
    <span className={`hmi-value-cell inline-flex items-baseline gap-1 ${className}`}>
      {functionCode && (
        <span className="label-caps text-[var(--text-dim)] mr-0.5 text-[10px]">{functionCode}</span>
      )}
      <span className="font-data tabular-nums text-[var(--text)]">{formatted}</span>
      {unit && (
        <span className="caption-mono text-[var(--text-muted)] ml-0.5 text-[11px]">{unit}</span>
      )}
    </span>
  );
}
