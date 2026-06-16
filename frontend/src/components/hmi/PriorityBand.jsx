/**
 * PriorityBand — persistent top-of-Runtime alarm safe area.
 *
 * ABB guideline: alarm band at top, most eye-catching, no overlap.
 * Redundant coding: color + shape glyph + priority letter (never color-only).
 * Reads worst trust tier from the live store; no props required.
 */
import useStore from '../../store';
import { priorityGlyph, priorityLetter } from '../../lib/hmiFormat';

const TIER_RANK  = { CRITICAL: 0, LOW: 1, MEDIUM: 2, HIGH: 3 };
const TIER_COLOR = {
  CRITICAL: 'var(--alarm-p1)',
  LOW:      'var(--alarm-p3)',
  MEDIUM:   'var(--alarm-p2)',
  HIGH:     'var(--text-dim)',
};

function findWorstTier(confidence) {
  const nonNominal = (confidence || []).filter((c) => c.tier && c.tier !== 'HIGH');
  if (!nonNominal.length) return null;
  return nonNominal.sort((a, b) => (TIER_RANK[a.tier] ?? 4) - (TIER_RANK[b.tier] ?? 4))[0];
}

export default function PriorityBand() {
  const { confidence, massBalance, connected } = useStore();

  if (!connected) {
    return (
      <div className="hmi-priority-band" style={{ borderBottomColor: 'var(--alarm-p1)' }}>
        <span className="hmi-status-glyph font-bold text-[var(--alarm-p1)]">◆</span>
        <span className="label-caps font-bold text-[var(--alarm-p1)]">C — Live trust state unavailable</span>
        <div className="ml-auto">
          <span className="label-caps text-[var(--alarm-p1)]">OFFLINE</span>
        </div>
      </div>
    );
  }

  const worst = findWorstTier(confidence);
  const mbFlags = massBalance?.flags?.length || 0;
  const nonNominalCount = (confidence || []).filter((c) => c.tier && c.tier !== 'HIGH').length;
  const allClear = !worst && mbFlags === 0;

  if (allClear) {
    return (
      <div className="hmi-priority-band">
        <span className="hmi-status-glyph text-[var(--text-dim)]">○</span>
        <span className="label-caps text-[var(--text-dim)]">N — No active trust exceptions</span>
      </div>
    );
  }

  const tier  = worst?.tier || 'MEDIUM';
  const color = TIER_COLOR[tier] || 'var(--text-dim)';
  const glyph = priorityGlyph(tier);
  const letter = priorityLetter(tier);

  return (
    <div className="hmi-priority-band" style={{ borderBottomColor: color }}>
      <span className="hmi-status-glyph font-bold" style={{ color }}>{glyph}</span>
      <span className="label-caps font-bold" style={{ color }}>{letter} —</span>
      <span className="label-caps" style={{ color }}>
        {worst
          ? `${worst.tier}${worst.sensor_id ? ` · ${worst.sensor_id}` : ''}`
          : 'Mass-balance anomaly'}
      </span>
      {nonNominalCount > 1 && (
        <span className="label-caps text-[var(--text-muted)]">
          ({nonNominalCount} sensors below threshold)
        </span>
      )}
      {mbFlags > 0 && (
        <span className="label-caps" style={{ color: 'var(--alarm-p2)' }}>
          · {mbFlags} MB flag{mbFlags > 1 ? 's' : ''}
        </span>
      )}
      <div className="ml-auto" />
    </div>
  );
}
