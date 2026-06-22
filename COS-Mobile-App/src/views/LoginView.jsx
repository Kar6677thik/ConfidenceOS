import { useState } from 'react';
import useStore from '../store';
import { DEMO_CREDS } from '../mock/data';

const ROLE_COLORS = {
  Operator:    { accent: '#22c55e', border: '#16a34a' },
  Maintenance: { accent: '#f97316', border: '#ea580c' },
  Engineer:    { accent: '#0a84ff', border: '#0071e3' },
  Manager:     { accent: '#a855f7', border: '#9333ea' },
  Auditor:     { accent: '#9ca3af', border: '#6b7280' },
};

const FEATURES = [
  { icon: '⚠', text: 'ISA-18.2 alarm triage' },
  { icon: '◉', text: 'Active incident tracking' },
  { icon: '☑', text: 'Field verification tasks' },
  { icon: '⇄', text: 'Shift handover brief' },
];

export default function LoginView() {
  const login = useStore((s) => s.login);
  const authLoading = useStore((s) => s.authLoading);
  const authError = useStore((s) => s.authError);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [activeRole, setActiveRole] = useState(null);

  const handleRolePill = async (cred) => {
    setActiveRole(cred.label);
    await login(cred.username, cred.password);
    setActiveRole(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    await login(username, password);
  };

  return (
    <div className="login-page">

      {/* ── Branding panel (left on desktop, top strip on mobile) ── */}
      <div className="login-brand-panel">
        <div className="login-brand-grid" />

        {/* Desktop brand content */}
        <div className="login-brand-content" style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 40 }}>
            <div style={{ width: 38, height: 38, borderRadius: 8, background: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            </div>
            <div>
              <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', letterSpacing: '0.02em' }}>ConfidenceOS</div>
              <div style={{ fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: 1 }}>Field Mobile</div>
            </div>
          </div>

          <div style={{ marginBottom: 32 }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text)', lineHeight: 1.35, marginBottom: 10 }}>
              Plant operations in your pocket
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.65 }}>
              Real-time alarms, incident tracking, and shift handover — optimised for field use.
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {FEATURES.map(({ icon, text }) => (
              <div key={text} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ color: 'var(--primary)', fontSize: 13, width: 16, textAlign: 'center', flexShrink: 0 }}>{icon}</span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{text}</span>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 'auto', padding: '12px 14px', background: 'rgba(0,90,160,0.07)', border: '1px solid rgba(0,90,160,0.18)', borderRadius: 6, fontSize: 10, color: 'var(--text-muted)', lineHeight: 1.6 }}>
            <span style={{ color: 'var(--primary)', fontWeight: 600 }}>Read-only advisory.</span>{' '}
            Does not write control commands or operate field devices.
          </div>
        </div>

        {/* Mobile compact header */}
        <div className="login-brand-compact" style={{ position: 'relative', zIndex: 1 }}>
          <div style={{ width: 32, height: 32, borderRadius: 6, background: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>ConfidenceOS</div>
            <div style={{ fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.07em', textTransform: 'uppercase' }}>Field Mobile</div>
          </div>
        </div>
      </div>

      {/* ── Form panel ── */}
      <div className="login-form-panel">
        <div className="login-form-inner">
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text)', marginBottom: 5 }}>Sign in</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.55 }}>
              Your role determines which views are available to you.
            </div>
          </div>

          {/* Role quick-sign-in */}
          <div style={{ marginBottom: 6 }}>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.07em', textTransform: 'uppercase', marginBottom: 10, fontWeight: 600 }}>
              Quick sign-in by role
            </div>
            {DEMO_CREDS.map((cred) => {
              const colors = ROLE_COLORS[cred.label];
              const isActive = activeRole === cred.label;
              return (
                <button
                  key={cred.label}
                  className="login-role-btn"
                  onClick={() => handleRolePill(cred)}
                  disabled={authLoading}
                  style={{
                    borderColor: isActive ? colors.accent : colors.border,
                    background: isActive ? colors.accent : 'var(--bg-elevated)',
                    cursor: authLoading ? 'wait' : 'pointer',
                    opacity: authLoading && !isActive ? 0.5 : 1,
                  }}
                >
                  <span
                    className="login-role-dot"
                    style={{ background: isActive ? '#fff' : colors.accent }}
                  />
                  <span
                    className="login-role-name"
                    style={{ color: isActive ? '#fff' : colors.accent }}
                  >
                    {isActive && authLoading ? 'Signing in…' : cred.label}
                  </span>
                  <span
                    className="login-role-access"
                    style={{ color: isActive ? 'rgba(255,255,255,0.75)' : undefined }}
                  >
                    {cred.access}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Divider */}
          <div className="login-divider">
            <div className="login-divider-line" />
            <span className="login-divider-text">OR SIGN IN MANUALLY</span>
            <div className="login-divider-line" />
          </div>

          {/* Manual form */}
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 5 }}>Username</label>
              <input
                className="login-input"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
                placeholder="e.g. operator"
              />
            </div>
            <div>
              <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 5 }}>Password</label>
              <input
                className="login-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                placeholder="••••••••"
              />
            </div>

            {authError && (
              <div className="login-error">{authError}</div>
            )}

            <button
              type="submit"
              className="login-submit-btn"
              disabled={authLoading}
            >
              {authLoading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
