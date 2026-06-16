/**
 * chartTheme.js — single source of truth for data-visualization colors and
 * Recharts/SVG styling, aligned to the NAMUR NE107 design tokens in index.css.
 *
 * Why this exists: charts and hand-built SVGs previously hardcoded hex that
 * drifted from (and contradicted) the design tokens — e.g. a neon `#00FF41`
 * "nominal" green and pure `#FF0000` "failure" red, when the tokens are
 * `--safe: #00bfff` and `--critical: #ffb4ab`. A NE107-claiming HMI must speak
 * one color language. Resolve tokens to concrete hex once (SVG presentation
 * attributes set by Recharts don't reliably honor `var(--…)`), with the
 * canonical token values as fallbacks so colors are correct even pre-paint.
 */

function token(name, fallback) {
  if (typeof window === 'undefined' || !window.getComputedStyle) return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

// NAMUR NE107-aligned trust tiers → canonical token colors.
export const TRUST_COLOR = {
  HIGH: token('--safe', '#00bfff'),        // Good / Normal
  MEDIUM: token('--caution', '#c3c6cd'),   // Maintenance / Attention
  LOW: token('--warning', '#ffda66'),      // Out of Spec
  CRITICAL: token('--critical', '#ffb4ab'),// Failure
  UNKNOWN: token('--text-dim', '#87929b'),
};

export function trustColor(tier) {
  return TRUST_COLOR[String(tier || '').toUpperCase()] || TRUST_COLOR.HIGH;
}

// Map a 0–100 integrity percentage to the same tier palette.
export function pctColor(pct) {
  if (pct >= 80) return TRUST_COLOR.HIGH;
  if (pct >= 50) return TRUST_COLOR.MEDIUM;
  if (pct >= 20) return TRUST_COLOR.LOW;
  return TRUST_COLOR.CRITICAL;
}

// Shared chart palette (neutral structural colors).
export const chartColors = {
  axis: token('--text-dim', '#87929b'),
  grid: token('--border-subtle', '#2d333b'),
  axisLine: token('--border-strong', '#3d4850'),
  primary: token('--primary', '#8fd6ff'),
  text: token('--text', '#e1e2e7'),
  muted: token('--data-mono', '#bcc8d1'),
  surface: token('--surface-base', '#0b0e11'),
  card: token('--surface-panel', '#1d2023'),
};

// Spreadable Recharts configs so every chart shares identical axis/grid styling.
export const chartGrid = {
  stroke: chartColors.grid,
  strokeDasharray: '4 4',
  vertical: false,
};

export const axisTick = {
  fontSize: 11,
  fill: chartColors.axis,
  fontFamily: 'Geist, ui-monospace, monospace',
};

export const axisLine = { stroke: chartColors.axisLine };
