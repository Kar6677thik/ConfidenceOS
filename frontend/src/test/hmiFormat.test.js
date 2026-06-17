import { describe, it, expect } from 'vitest';
import { formatLiveValue, priorityGlyph, priorityLetter } from '../lib/hmiFormat';

describe('formatLiveValue', () => {
  it('returns 0 decimal places for values >= 100', () => {
    expect(formatLiveValue(150.7)).toBe('151');
    expect(formatLiveValue(100)).toBe('100');
    expect(formatLiveValue(999.9)).toBe('1000');
  });

  it('returns 1 decimal place for values 10–99.9', () => {
    expect(formatLiveValue(75.34)).toBe('75.3');
    expect(formatLiveValue(10)).toBe('10.0');
    expect(formatLiveValue(99.9)).toBe('99.9');
  });

  it('returns 2 decimal places for values < 10', () => {
    expect(formatLiveValue(5.678)).toBe('5.68');
    expect(formatLiveValue(0.5)).toBe('0.50');
    expect(formatLiveValue(9.999)).toBe('10.00');
  });

  it('returns "--" for null, undefined, NaN, non-numeric', () => {
    expect(formatLiveValue(null)).toBe('--');
    expect(formatLiveValue(undefined)).toBe('--');
    expect(formatLiveValue(NaN)).toBe('--');
    expect(formatLiveValue('abc')).toBe('--');
  });

  it('handles negative values with same decimal discipline', () => {
    expect(formatLiveValue(-150)).toBe('-150');
    expect(formatLiveValue(-50.5)).toBe('-50.5');
    expect(formatLiveValue(-5.5)).toBe('-5.50');
  });
});

describe('priorityGlyph', () => {
  it('maps each tier to its shape glyph', () => {
    expect(priorityGlyph('CRITICAL')).toBe('◆');
    expect(priorityGlyph('LOW')).toBe('▲');
    expect(priorityGlyph('MEDIUM')).toBe('▼');
    expect(priorityGlyph('HIGH')).toBe('○');
    expect(priorityGlyph('NORMAL')).toBe('○');
  });

  it('is case-insensitive', () => {
    expect(priorityGlyph('critical')).toBe('◆');
    expect(priorityGlyph('medium')).toBe('▼');
  });

  it('defaults to open circle for unknown tier', () => {
    expect(priorityGlyph('UNKNOWN')).toBe('○');
    expect(priorityGlyph(null)).toBe('○');
    expect(priorityGlyph(undefined)).toBe('○');
  });
});

describe('priorityLetter', () => {
  it('maps each tier to its letter code', () => {
    expect(priorityLetter('CRITICAL')).toBe('C');
    expect(priorityLetter('LOW')).toBe('L');
    expect(priorityLetter('MEDIUM')).toBe('M');
    expect(priorityLetter('HIGH')).toBe('N');
    expect(priorityLetter('NORMAL')).toBe('N');
  });

  it('is case-insensitive', () => {
    expect(priorityLetter('critical')).toBe('C');
    expect(priorityLetter('low')).toBe('L');
  });

  it('defaults to N for unknown tier', () => {
    expect(priorityLetter('UNKNOWN')).toBe('N');
    expect(priorityLetter(null)).toBe('N');
  });
});
