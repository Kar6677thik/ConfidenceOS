import { describe, it, expect } from 'vitest';
import { pctColor, trustColor, TRUST_COLOR } from '../lib/chartTheme';

// In jsdom, CSS custom properties return empty string, so TRUST_COLOR
// values resolve to their hardcoded fallbacks.
describe('TRUST_COLOR fallbacks (jsdom — no CSS vars)', () => {
  it('defines all four tiers with non-empty fallback hex', () => {
    expect(TRUST_COLOR.HIGH).toBeTruthy();
    expect(TRUST_COLOR.MEDIUM).toBeTruthy();
    expect(TRUST_COLOR.LOW).toBeTruthy();
    expect(TRUST_COLOR.CRITICAL).toBeTruthy();
  });

  it('four tiers are all distinct colors', () => {
    const colors = [TRUST_COLOR.HIGH, TRUST_COLOR.MEDIUM, TRUST_COLOR.LOW, TRUST_COLOR.CRITICAL];
    expect(new Set(colors).size).toBe(4);
  });
});

describe('pctColor thresholds', () => {
  it('maps >= 80 to HIGH', () => {
    expect(pctColor(80)).toBe(TRUST_COLOR.HIGH);
    expect(pctColor(85)).toBe(TRUST_COLOR.HIGH);
    expect(pctColor(100)).toBe(TRUST_COLOR.HIGH);
  });

  it('maps 50–79 to MEDIUM', () => {
    expect(pctColor(50)).toBe(TRUST_COLOR.MEDIUM);
    expect(pctColor(60)).toBe(TRUST_COLOR.MEDIUM);
    expect(pctColor(79)).toBe(TRUST_COLOR.MEDIUM);
  });

  it('maps 20–49 to LOW', () => {
    expect(pctColor(20)).toBe(TRUST_COLOR.LOW);
    expect(pctColor(30)).toBe(TRUST_COLOR.LOW);
    expect(pctColor(49)).toBe(TRUST_COLOR.LOW);
  });

  it('maps < 20 to CRITICAL', () => {
    expect(pctColor(19)).toBe(TRUST_COLOR.CRITICAL);
    expect(pctColor(10)).toBe(TRUST_COLOR.CRITICAL);
    expect(pctColor(0)).toBe(TRUST_COLOR.CRITICAL);
  });
});

describe('trustColor tier mapping', () => {
  it('returns the correct color for each named tier', () => {
    expect(trustColor('HIGH')).toBe(TRUST_COLOR.HIGH);
    expect(trustColor('MEDIUM')).toBe(TRUST_COLOR.MEDIUM);
    expect(trustColor('LOW')).toBe(TRUST_COLOR.LOW);
    expect(trustColor('CRITICAL')).toBe(TRUST_COLOR.CRITICAL);
  });

  it('is case-insensitive', () => {
    expect(trustColor('high')).toBe(TRUST_COLOR.HIGH);
    expect(trustColor('critical')).toBe(TRUST_COLOR.CRITICAL);
  });

  it("maps 'UNKNOWN' tier to the UNKNOWN color (not HIGH)", () => {
    expect(trustColor('UNKNOWN')).toBe(TRUST_COLOR.UNKNOWN);
  });

  it('falls back to HIGH for null/undefined/unrecognized tier', () => {
    expect(trustColor(null)).toBe(TRUST_COLOR.HIGH);
    expect(trustColor(undefined)).toBe(TRUST_COLOR.HIGH);
    expect(trustColor('GARBAGE')).toBe(TRUST_COLOR.HIGH);
  });
});
