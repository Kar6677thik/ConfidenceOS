export function formatText(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function statusClass(value) {
  const status = String(value || '').toUpperCase();
  if (['PASS', 'READY', 'PUBLISHED', 'VALID', 'APPROVED', 'IGNORED'].includes(status)) return 'status-safe';
  if (['WARNING', 'PASS_WITH_WARNINGS', 'WARNINGS'].includes(status)) return 'status-warning';
  if (['FAILED', 'BLOCKING', 'BLOCKED', 'NOT_READY', 'CRITICAL'].includes(status)) return 'status-critical';
  if (['NOT_RUN', 'LOADING', 'WAIT', 'OPTIONAL'].includes(status)) return 'status-disabled';
  return 'text-[var(--data-mono)]';
}

export function asList(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  if (value == null || value === '') return [];
  return [value];
}

import apiFetch from '../../lib/apiFetch';

export async function fetchJson(url, options) {
  // Route through apiFetch so role-gated studio writes carry the Bearer token
  // (and X-API-Key when configured).
  const res = await apiFetch(url, options);
  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(`Request failed: ${res.status}`);
    err.payload = payload;
    throw err;
  }
  return payload;
}
