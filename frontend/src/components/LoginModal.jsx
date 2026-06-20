/**
 * LoginModal — JWT login form for ConfidenceOS.
 *
 * Shows as an overlay when the user is not authenticated.
 * On success, token is stored in Zustand; the modal disappears.
 * Demo credentials are shown to reduce friction in demo sessions.
 */
import { useState } from 'react';
import useStore from '../store';

const DEMO_CREDS = [
  { label: 'Operator',    username: 'operator', password: 'ConfidenceOS-Op-2025' },
  { label: 'Engineer',    username: 'engineer', password: 'ConfidenceOS-Eng-2025' },
  { label: 'Maintenance', username: 'maint',    password: 'ConfidenceOS-Maint-2025' },
  { label: 'Manager',     username: 'manager',  password: 'ConfidenceOS-Mgr-2025' },
  { label: 'Auditor',     username: 'auditor',  password: 'ConfidenceOS-Aud-2025' },
];

export default function LoginModal() {
  const login = useStore((s) => s.login);
  const authLoading = useStore((s) => s.authLoading);
  const authError = useStore((s) => s.authError);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    await login(username, password);
  };

  const fillDemo = (cred) => {
    setUsername(cred.username);
    setPassword(cred.password);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.80)' }}
    >
      <div
        className="industrial-card p-6 w-full max-w-sm mx-4"
        style={{ border: '1px solid var(--border)' }}
      >
        <div className="mb-5">
          <div className="text-[var(--text)] font-semibold text-base mb-1">ConfidenceOS</div>
          <div className="caption-mono text-[var(--text-muted)]">Sign in to continue</div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="caption-mono text-[var(--text-muted)] block mb-1">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
              style={{
                width: '100%',
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 4,
                padding: '6px 8px',
                color: 'var(--text)',
                fontFamily: 'var(--font-mono, monospace)',
                fontSize: 13,
              }}
            />
          </div>
          <div>
            <label className="caption-mono text-[var(--text-muted)] block mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              style={{
                width: '100%',
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 4,
                padding: '6px 8px',
                color: 'var(--text)',
                fontFamily: 'var(--font-mono, monospace)',
                fontSize: 13,
              }}
            />
          </div>

          {authError && (
            <div className="caption-mono status-critical">{authError}</div>
          )}

          <button
            type="submit"
            disabled={authLoading}
            style={{
              width: '100%',
              padding: '8px 0',
              background: 'var(--primary, #0a84ff)',
              border: 'none',
              borderRadius: 4,
              color: '#fff',
              fontFamily: 'var(--font-mono, monospace)',
              fontSize: 13,
              cursor: authLoading ? 'wait' : 'pointer',
              opacity: authLoading ? 0.7 : 1,
            }}
          >
            {authLoading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="mt-4">
          <div className="caption-mono text-[var(--text-muted)] mb-2">Demo quick-fill</div>
          <div className="flex flex-wrap gap-2">
            {DEMO_CREDS.map((c) => (
              <button
                key={c.label}
                onClick={() => fillDemo(c)}
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 3,
                  padding: '3px 8px',
                  color: 'var(--text-muted)',
                  fontFamily: 'var(--font-mono, monospace)',
                  fontSize: 11,
                  cursor: 'pointer',
                }}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
