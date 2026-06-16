/**
 * hmiFormat.js — ABB HMI display utilities
 *
 * Pure functions, no imports, no side effects. Referenced by HMI components
 * to enforce consistent live-value formatting and redundant status coding
 * per ABB Operator workplace guidelines (ISO 11064-5 / EEMUA 191).
 */

/**
 * ABB decimal discipline: ≥100 → 0 decimal, 10–99.9 → 1, <10 → 2.
 * Ensures tabular alignment and avoids false precision.
 */
export function formatLiveValue(value) {
  if (value == null || !Number.isFinite(Number(value))) return '--';
  const n = Number(value);
  if (Math.abs(n) >= 100) return n.toFixed(0);
  if (Math.abs(n) >= 10) return n.toFixed(1);
  return n.toFixed(2);
}

/**
 * Redundant shape coding (color + shape) per ABB guidelines.
 * CRITICAL → ◆ (filled diamond), LOW → ▲ (triangle),
 * MEDIUM → ▼ (inverted triangle), HIGH/NORMAL → ○ (open circle).
 */
export function priorityGlyph(tier) {
  const map = {
    CRITICAL: '◆',
    LOW:      '▲',
    MEDIUM:   '▼',
    HIGH:     '○',
    NORMAL:   '○',
  };
  return map[String(tier || '').toUpperCase()] || '○';
}

/**
 * Redundant letter coding per ABB guidelines.
 * CRITICAL → C, LOW → L, MEDIUM → M, HIGH/NORMAL → N.
 */
export function priorityLetter(tier) {
  const map = { CRITICAL: 'C', LOW: 'L', MEDIUM: 'M', HIGH: 'N', NORMAL: 'N' };
  return map[String(tier || '').toUpperCase()] || 'N';
}
