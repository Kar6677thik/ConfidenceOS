/**
 * apiFetch — thin fetch wrapper that attaches auth headers to every request.
 *
 * Priority:
 *   1. Authorization: Bearer <jwt>  — when the user has logged in
 *   2. X-API-Key                     — machine-client API key (optional)
 */
import useStore from '../store';

function buildHeaders(options = {}) {
  const headers = { ...(options.headers || {}) };
  try {
    const { authToken } = useStore.getState();
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
  } catch {
    /* store not ready — send without auth */
  }
  const apiKey = import.meta.env.VITE_CONFIDENCEOS_API_KEY;
  if (apiKey) headers['X-API-Key'] = apiKey;
  return headers;
}

function isJwtFailure(payload) {
  const detail = String(payload?.detail || '').toLowerCase();
  return detail.includes('token invalid')
    || detail.includes('token expired')
    || detail.includes('signature')
    || detail.includes('not enough segments')
    || detail.includes('jwt');
}

export default async function apiFetch(path, options = {}) {
  const headers = buildHeaders(options);
  const response = await fetch(path, { ...options, headers });
  if (response.status !== 401) return response;

  let payload = null;
  try {
    payload = await response.clone().json();
  } catch {
    // Keep payload null when the backend did not return JSON.
  }

  const { authToken, logout } = useStore.getState();
  if (!authToken || !isJwtFailure(payload)) return response;

  // Backend JWT secrets can be ephemeral in demo deployments. If a token was
  // minted before a restart, clear it and let the caller surface the 401/login
  // state. Never retry by downgrading to a role header.
  logout();
  return response;
}
