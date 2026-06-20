/**
 * apiFetch — thin fetch wrapper that attaches the operator-asserted role
 * (X-Role) and, when configured, an API key (X-API-Key) to a request.
 *
 * Use this for any call to a role-gated or mutating endpoint so server-side
 * enforcement (backend/auth.py) has the headers it needs. When no API key is
 * configured (the default demo build) behaviour is identical to plain fetch.
 */
import useStore from '../store';

export default function apiFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  try {
    const role = useStore.getState().role;
    if (role) headers['X-Role'] = role;
  } catch {
    /* store not ready — send without role */
  }
  const apiKey = import.meta.env.VITE_CONFIDENCEOS_API_KEY;
  if (apiKey) headers['X-API-Key'] = apiKey;
  return fetch(path, { ...options, headers });
}
