/**
 * StatusTag — replaces bare color-only badges/pips.
 *
 * ABB guideline: alarm priority must be redundant — color + shape or letter.
 * Renders: [glyph] [letter] — [label]
 */
import { priorityGlyph, priorityLetter } from '../../lib/hmiFormat';

const TIER_COLOR = {
  CRITICAL: 'var(--alarm-p1)',
  LOW:      'var(--alarm-p3)',
  MEDIUM:   'var(--alarm-p2)',
  HIGH:     'var(--text-dim)',
  NORMAL:   'var(--text-dim)',
};

export default function StatusTag({ tier, label, className = '' }) {
  const t     = String(tier || 'HIGH').toUpperCase();
  const color = TIER_COLOR[t] || 'var(--text-dim)';
  const glyph = priorityGlyph(t);
  const letter = priorityLetter(t);
  const text  = label || t;

  return (
    <span
      className={`inline-flex items-center gap-1 label-caps border rounded-sm px-1.5 py-0.5 flex-shrink-0 ${className}`}
      style={{ color, borderColor: `${color}60` }}
    >
      <span className="hmi-status-glyph">{glyph}</span>
      <span>{letter} — {text}</span>
    </span>
  );
}
