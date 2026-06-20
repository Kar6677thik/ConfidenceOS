/**
 * LoginPage — Full-page authentication gate for ConfidenceOS.
 *
 * Replaces the LoginModal overlay. Nothing renders behind this;
 * the entire viewport is this page until login succeeds.
 */
import { useState } from 'react';
import useStore from '../store';

const ROLE_COLORS = {
  Operator:    { accent: '#22c55e', border: '#16a34a', dark: '#14532d' },
  Maintenance: { accent: '#f97316', border: '#ea580c', dark: '#7c2d12' },
  Engineer:    { accent: '#0a84ff', border: '#0071e3', dark: '#1e3a5f' },
  Manager:     { accent: '#a855f7', border: '#9333ea', dark: '#581c87' },
  Auditor:     { accent: '#9ca3af', border: '#6b7280', dark: '#374151' },
};

const DEMO_CREDS = [
  { label: 'Operator',    username: 'operator', password: 'ConfidenceOS-Op-2025',   access: 'Runtime · Work Queue · Shift Channel' },
  { label: 'Maintenance', username: 'maint',    password: 'ConfidenceOS-Maint-2025', access: 'Runtime · Work Queue · Shift Channel' },
  { label: 'Engineer',    username: 'engineer', password: 'ConfidenceOS-Eng-2025',   access: 'Studio · Analysis · Sandbox · all above' },
  { label: 'Manager',     username: 'manager',  password: 'ConfidenceOS-Mgr-2025',   access: 'Studio · Compliance · all above' },
  { label: 'Auditor',     username: 'auditor',  password: 'ConfidenceOS-Aud-2025',   access: 'Forensics · Compliance · read-only' },
];

const FEATURES = [
  { icon: '◈', text: 'Trust-aware sensor scoring' },
  { icon: '⊕', text: 'Physics-based mass balance' },
  { icon: '⇄', text: 'Shift handover intelligence' },
  { icon: '◉', text: 'ISA-18.2 alarm management' },
  { icon: '▦', text: 'Compliance audit trail' },
];

export default function LoginPage() {
  const login = useStore((s) => s.login);
  const authLoading = useStore((s) => s.authLoading);
  const authError = useStore((s) => s.authError);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [activeRole, setActiveRole] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    await login(username, password);
  };

  const handleRolePill = async (cred) => {
    setActiveRole(cred.label);
    setUsername(cred.username);
    setPassword(cred.password);
    await login(cred.username, cred.password);
    setActiveRole(null);
  };

  const inputStyle = {
    width: '100%',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 6,
    padding: '10px 12px',
    color: 'var(--text)',
    fontFamily: 'var(--font-mono, monospace)',
    fontSize: 13,
    outline: 'none',
    transition: 'border-color 0.15s',
    boxSizing: 'border-box',
  };

  return (
    <div
      style={{
        display: 'flex',
        height: '100vh',
        width: '100vw',
        overflow: 'hidden',
        fontFamily: 'var(--font-mono, monospace)',
      }}
    >
      {/* ── Left branding panel ────────────────────────────────── */}
      <div
        style={{
          width: '42%',
          minWidth: 280,
          background: 'var(--surface)',
          borderRight: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          padding: '48px 40px',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Subtle grid pattern overlay */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage:
              'linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px)',
            backgroundSize: '32px 32px',
            opacity: 0.25,
            pointerEvents: 'none',
          }}
        />

        {/* Logo + wordmark */}
        <div style={{ position: 'relative', zIndex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 48 }}>
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: 8,
                background: 'var(--primary, #0a84ff)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text)', letterSpacing: '0.03em' }}>
                ConfidenceOS
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: 1 }}>
                Plant Operations Platform
              </div>
            </div>
          </div>

          {/* Tagline */}
          <div style={{ marginBottom: 40 }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', lineHeight: 1.35, marginBottom: 12 }}>
              Trust-aware HMI overlay for industrial process control
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.7 }}>
              Read-only advisory system. Scores sensor reliability, detects mass-balance divergence, and surfaces shift-critical information — without writing control commands.
            </div>
          </div>

          {/* Feature list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 40 }}>
            {FEATURES.map(({ icon, text }) => (
              <div key={text} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ color: 'var(--primary, #0a84ff)', fontSize: 14, width: 16, textAlign: 'center', flexShrink: 0 }}>
                  {icon}
                </span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div style={{ marginTop: 'auto', position: 'relative', zIndex: 1 }}>
          <div
            style={{
              padding: '12px 16px',
              background: 'rgba(10,132,255,0.07)',
              border: '1px solid rgba(10,132,255,0.2)',
              borderRadius: 6,
              fontSize: 11,
              color: 'var(--text-muted)',
              lineHeight: 1.6,
            }}
          >
            <span style={{ color: 'var(--primary, #0a84ff)', fontWeight: 600 }}>Read-only system.</span>{' '}
            ConfidenceOS does not write control commands, change setpoints, or operate field devices. All outputs are decision-support only.
          </div>
          <div style={{ marginTop: 16, fontSize: 10, color: 'var(--text-muted)', opacity: 0.6 }}>
            v2.0.0 · ConfidenceOS
          </div>
        </div>
      </div>

      {/* ── Right login panel ──────────────────────────────────── */}
      <div
        style={{
          flex: 1,
          background: 'var(--bg, #f0f0f0)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '40px 32px',
          overflowY: 'auto',
        }}
      >
        <div style={{ width: '100%', maxWidth: 400 }}>
          {/* Heading */}
          <div style={{ marginBottom: 32 }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>
              Sign in to your workspace
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>
              Your role determines which workspaces and tools are available to you.
            </div>
          </div>

          {/* Quick role sign-in */}
          <div style={{ marginBottom: 28 }}>
            <div
              style={{
                fontSize: 10,
                color: 'var(--text-muted)',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                marginBottom: 12,
              }}
            >
              Quick sign-in by role
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {DEMO_CREDS.map((cred) => {
                const colors = ROLE_COLORS[cred.label];
                const isActive = activeRole === cred.label;
                return (
                  <button
                    key={cred.label}
                    onClick={() => handleRolePill(cred)}
                    disabled={authLoading}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      padding: '10px 14px',
                      background: isActive ? colors.accent : 'var(--surface)',
                      border: `1px solid ${isActive ? colors.accent : colors.border}`,
                      borderRadius: 6,
                      cursor: authLoading ? 'wait' : 'pointer',
                      opacity: authLoading && !isActive ? 0.5 : 1,
                      transition: 'all 0.12s',
                      textAlign: 'left',
                      width: '100%',
                    }}
                  >
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: isActive ? '#fff' : colors.accent,
                        flexShrink: 0,
                      }}
                    />
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        color: isActive ? '#fff' : colors.accent,
                        fontFamily: 'var(--font-mono, monospace)',
                        minWidth: 90,
                        flexShrink: 0,
                      }}
                    >
                      {isActive && authLoading ? 'Signing in…' : cred.label}
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        color: isActive ? 'rgba(255,255,255,0.75)' : 'var(--text-muted)',
                        fontFamily: 'var(--font-mono, monospace)',
                      }}
                    >
                      {cred.access}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Divider */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
            <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            <span style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.06em' }}>OR SIGN IN MANUALLY</span>
            <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
          </div>

          {/* Manual form */}
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 5 }}>
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
                style={inputStyle}
                onFocus={(e) => { e.target.style.borderColor = 'var(--primary, #0a84ff)'; e.target.style.boxShadow = '0 0 0 3px rgba(10,132,255,0.15)'; }}
                onBlur={(e) => { e.target.style.borderColor = 'var(--border)'; e.target.style.boxShadow = 'none'; }}
              />
            </div>
            <div>
              <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 5 }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                style={inputStyle}
                onFocus={(e) => { e.target.style.borderColor = 'var(--primary, #0a84ff)'; e.target.style.boxShadow = '0 0 0 3px rgba(10,132,255,0.15)'; }}
                onBlur={(e) => { e.target.style.borderColor = 'var(--border)'; e.target.style.boxShadow = 'none'; }}
              />
            </div>

            {authError && (
              <div
                style={{
                  fontSize: 12,
                  color: 'var(--critical, #ff453a)',
                  padding: '8px 12px',
                  background: 'rgba(255,69,58,0.08)',
                  border: '1px solid rgba(255,69,58,0.25)',
                  borderRadius: 4,
                  fontFamily: 'var(--font-mono, monospace)',
                }}
              >
                {authError}
              </div>
            )}

            <button
              type="submit"
              disabled={authLoading}
              style={{
                width: '100%',
                padding: '11px 0',
                background: 'var(--primary, #0a84ff)',
                border: 'none',
                borderRadius: 6,
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
          </form>
        </div>
      </div>
    </div>
  );
}
