/**
 * apiFetch — thin fetch wrapper that attaches auth headers to every request.
 *
 * Priority:
 *   1. Authorization: Bearer <jwt>  — when the user has logged in
 *   2. X-Role header fallback        — legacy demo mode without login
 *   3. X-API-Key                     — machine-client API key (optional)
 */
import useStore from '../store';

export default function apiFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  try {
    const { authToken, role } = useStore.getState();
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    } else if (role) {
      headers['X-Role'] = role;
    }
  } catch {
    /* store not ready — send without auth */
  }
  const apiKey = import.meta.env.VITE_CONFIDENCEOS_API_KEY;
  if (apiKey) headers['X-API-Key'] = apiKey;
  return fetch(path, { ...options, headers });
}
