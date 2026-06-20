/**
 * LoginModal — JWT login form for ConfidenceOS.
 *
 * Redesigned with role-focused branding: color-coded role pills,
 * one-click auto-submit, and clear role-access descriptions.
 */
import { useState } from 'react';
import useStore from '../store';

const ROLE_COLORS = {
  Operator:    { bg: '#16a34a', border: '#15803d', text: '#fff', dot: '#4ade80' },
  Maintenance: { bg: '#ea580c', border: '#c2410c', text: '#fff', dot: '#fb923c' },
  Engineer:    { bg: '#0a84ff', border: '#0071e3', text: '#fff', dot: '#60a5fa' },
  Manager:     { bg: '#9333ea', border: '#7e22ce', text: '#fff', dot: '#c084fc' },
  Auditor:     { bg: '#4b5563', border: '#374151', text: '#fff', dot: '#9ca3af' },
};

const DEMO_CREDS = [
  {
    label: 'Operator',
    username: 'operator',
    password: 'ConfidenceOS-Op-2025',
    access: 'Runtime · Shift Channel · Work Queue',
  },
  {
    label: 'Maintenance',
    username: 'maint',
    password: 'ConfidenceOS-Maint-2025',
    access: 'Runtime · Shift Channel · Work Queue',
  },
  {
    label: 'Engineer',
    username: 'engineer',
    password: 'ConfidenceOS-Eng-2025',
    access: 'Studio · Analysis · Sandbox · all above',
  },
  {
    label: 'Manager',
    username: 'manager',
    password: 'ConfidenceOS-Mgr-2025',
    access: 'Studio · Compliance · all above',
  },
  {
    label: 'Auditor',
    username: 'auditor',
    password: 'ConfidenceOS-Aud-2025',
    access: 'Forensics · Compliance · read-only',
  },
];

export default function LoginModal({ onDismiss }) {
  const login = useStore((s) => s.login);
  const authLoading = useStore((s) => s.authLoading);
  const authError = useStore((s) => s.authError);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [hoveredRole, setHoveredRole] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    await login(username, password);
  };

  const handleRolePill = async (cred) => {
    setUsername(cred.username);
    setPassword(cred.password);
    await login(cred.username, cred.password);
  };

  const inputStyle = {
    width: '100%',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 4,
    padding: '7px 10px',
    color: 'var(--text)',
    fontFamily: 'var(--font-mono, monospace)',
    fontSize: 13,
    outline: 'none',
    transition: 'border-color 0.15s',
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.82)' }}
    >
      <div
        className="industrial-card w-full max-w-sm mx-4"
        style={{
          border: '1px solid var(--border)',
          boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
          overflow: 'hidden',
          maxHeight: 'calc(100vh - 32px)',
          overflowY: 'auto',
        }}
      >
        {/* Header band */}
        <div
          style={{
            background: 'var(--surface)',
            borderBottom: '1px solid var(--border)',
            padding: '16px 20px 14px',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 6,
              background: 'var(--primary, #0a84ff)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <div>
            <div style={{ fontFamily: 'var(--font-mono, monospace)', fontWeight: 700, fontSize: 14, color: 'var(--text)', letterSpacing: '0.02em' }}>
              ConfidenceOS
            </div>
            <div style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>
              Plant Operations Access
            </div>
          </div>
        </div>

        <div style={{ padding: '18px 20px 20px' }}>
          {/* Role pills — one-click sign in */}
          <div style={{ marginBottom: 18 }}>
            <div style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
              Quick sign-in by role
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {DEMO_CREDS.map((c) => {
                const colors = ROLE_COLORS[c.label];
                const isHovered = hoveredRole === c.label;
                return (
                  <button
                    key={c.label}
                    onClick={() => handleRolePill(c)}
                    onMouseEnter={() => setHoveredRole(c.label)}
                    onMouseLeave={() => setHoveredRole(null)}
                    disabled={authLoading}
                    title={c.access}
                    style={{
                      background: isHovered ? colors.bg : 'transparent',
                      border: `1px solid ${colors.border}`,
                      borderRadius: 4,
                      padding: '4px 10px',
                      color: isHovered ? colors.text : colors.bg,
                      fontFamily: 'var(--font-mono, monospace)',
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: authLoading ? 'wait' : 'pointer',
                      opacity: authLoading ? 0.6 : 1,
                      transition: 'all 0.12s',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 5,
                    }}
                  >
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: isHovered ? colors.dot : colors.bg, flexShrink: 0, display: 'inline-block' }} />
                    {c.label}
                  </button>
                );
              })}
            </div>
            {hoveredRole && (
              <div style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 10, color: 'var(--text-muted)', marginTop: 6, paddingLeft: 2 }}>
                {DEMO_CREDS.find(c => c.label === hoveredRole)?.access}
              </div>
            )}
          </div>

          {/* Divider */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
            <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            <span style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.05em' }}>OR SIGN IN MANUALLY</span>
            <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
          </div>

          {/* Manual form */}
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div>
              <label style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
                style={inputStyle}
                onFocus={(e) => { e.target.style.borderColor = 'var(--primary, #0a84ff)'; e.target.style.outline = '2px solid rgba(10,132,255,0.25)'; e.target.style.outlineOffset = '0px'; }}
                onBlur={(e) => { e.target.style.borderColor = 'var(--border)'; e.target.style.outline = 'none'; }}
              />
            </div>
            <div>
              <label style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                style={inputStyle}
                onFocus={(e) => { e.target.style.borderColor = 'var(--primary, #0a84ff)'; e.target.style.outline = '2px solid rgba(10,132,255,0.25)'; e.target.style.outlineOffset = '0px'; }}
                onBlur={(e) => { e.target.style.borderColor = 'var(--border)'; e.target.style.outline = 'none'; }}
              />
            </div>

            {authError && (
              <div style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 11, color: 'var(--critical, #ff453a)', padding: '6px 8px', background: 'rgba(255,69,58,0.08)', borderRadius: 3, border: '1px solid rgba(255,69,58,0.25)' }}>
                {authError}
              </div>
            )}

            <button
              type="submit"
              disabled={authLoading}
              style={{
                width: '100%',
                padding: '9px 0',
                background: 'var(--primary, #0a84ff)',
                border: 'none',
                borderRadius: 4,
                color: '#fff',
                fontFamily: 'var(--font-mono, monospace)',
                fontSize: 13,
                fontWeight: 600,
                cursor: authLoading ? 'wait' : 'pointer',
                opacity: authLoading ? 0.7 : 1,
                letterSpacing: '0.02em',
              }}
            >
              {authLoading ? 'Signing in…' : 'Sign in'}
            </button>

            {onDismiss && (
              <button
                type="button"
                onClick={onDismiss}
                disabled={authLoading}
                style={{
                  width: '100%',
                  padding: '7px 0',
                  background: 'transparent',
                  border: '1px solid var(--border)',
                  borderRadius: 4,
                  color: 'var(--text-muted)',
                  fontFamily: 'var(--font-mono, monospace)',
                  fontSize: 12,
                  cursor: authLoading ? 'wait' : 'pointer',
                  opacity: authLoading ? 0.7 : 1,
                }}
              >
                Browse without signing in
              </button>
            )}
          </form>

          <div style={{ marginTop: 14, fontFamily: 'var(--font-mono, monospace)', fontSize: 10, color: 'var(--text-muted)', textAlign: 'center', lineHeight: 1.5 }}>
            Your role determines which workspaces are available to you.
          </div>
        </div>
      </div>
    </div>
  );
}
