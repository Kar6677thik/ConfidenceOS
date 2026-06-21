import { useState, useEffect } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import useStore from '../store';
import { isMuted as isAlarmMuted, setMuted as setAlarmMuted, onMuteChange } from '../lib/alarmSound';
import { countActiveAlerts, worstTrustException } from './navBarUtils';

const ROLES = ['Operator', 'Maintenance', 'Engineer', 'Manager', 'Auditor'];

const ROLE_COLOR = {
  Operator:    '#22c55e',
  Maintenance: '#f97316',
  Engineer:    '#0a84ff',
  Manager:     '#a855f7',
  Auditor:     '#6b7280',
};
const ROLE_BORDER = {
  Operator:    '#16a34a',
  Maintenance: '#ea580c',
  Engineer:    '#0071e3',
  Manager:     '#9333ea',
  Auditor:     '#4b5563',
};

const NAV_ITEMS = [
  { path: '/runtime',    label: 'Runtime',       roles: ['Operator', 'Maintenance', 'Engineer', 'Manager', 'Auditor'] },
  { path: '/studio',     label: 'Studio',        roles: ['Engineer', 'Manager'] },
  { path: '/handover',   label: 'Shift Channel', roles: ['Operator', 'Maintenance', 'Engineer', 'Manager', 'Auditor'] },
];

const SUPPORT_ITEMS = [
  { path: '/work-queue', label: 'Verification Work Queue', status: 'live', priority: 1, roles: ['Operator', 'Maintenance', 'Engineer', 'Manager', 'Auditor'] },
  { path: '/integrity',  label: 'Instrument Integrity',   status: 'support', priority: 2, roles: ['Operator', 'Maintenance', 'Engineer', 'Manager', 'Auditor'] },
  { path: '/operator',   label: 'Operator Detail',        status: 'support', priority: 3, roles: ['Operator', 'Maintenance', 'Engineer', 'Manager'] },
  { path: '/predictions',label: 'Degradation Forecast',   status: 'limited', priority: 4, roles: ['Operator', 'Maintenance', 'Engineer', 'Manager'] },
  { path: '/forensics',  label: 'Incident Replay',        status: 'training', priority: 5, roles: ['Engineer', 'Manager', 'Auditor'] },
  { path: '/graph',      label: 'Causal Graph',           status: 'support', priority: 6, roles: ['Engineer', 'Manager'] },
  { path: '/engineer',   label: 'Engineer Analysis',      status: 'support', priority: 7, roles: ['Engineer', 'Manager'] },
  { path: '/compliance', label: 'Compliance Report',      status: 'support', priority: 8, roles: ['Manager', 'Auditor'] },
  { path: '/sandbox',    label: 'Simulation Sandbox',     status: 'training', priority: 9, roles: ['Engineer'] },
];

export default function NavBar() {
  const {
    connected,
    averageConfidence,
    role,
    setRole,
    confidence,
    massBalance,
    staleFlags,
    systemHealth,
    healthError,
    authUser,
    authToken,
    logout,
    unackedAlarms,
  } = useStore();
  const location = useLocation();
  const navigate = useNavigate();

  const [muted, setMutedState] = useState(() => isAlarmMuted());
  useEffect(() => onMuteChange(setMutedState), []);
  const visibleItems = NAV_ITEMS.filter((item) => item.roles.includes(role));
  const supportItems = SUPPORT_ITEMS
    .filter((item) => item.roles.includes(role))
    .sort((a, b) => (a.priority || 99) - (b.priority || 99));
  const activeSupport = supportItems.some((item) => item.path === location.pathname) ? location.pathname : '';
  const alerts = countActiveAlerts(confidence, massBalance, staleFlags);
  const trustException = worstTrustException(confidence, connected);
  const readiness = systemHealth?.readiness_summary || (healthError ? 'api_unreachable' : 'unknown');
  const runtimeReady = readiness === 'ready';
  const readinessLabel = readiness === 'ready'
    ? 'Runtime ready'
    : readiness === 'degraded'
    ? 'Runtime degraded'
    : readiness === 'blocked'
    ? 'Runtime blocked'
    : healthError
    ? 'API unreachable'
    : 'Runtime warming';
  const readinessClass = readiness === 'ready'
    ? 'status-safe'
    : readiness === 'degraded' || readiness === 'unknown'
    ? 'status-warning'
    : 'status-critical';
  const healthClass = averageConfidence >= 80
    ? 'status-safe'
    : averageConfidence >= 50
    ? 'status-caution'
    : averageConfidence >= 20
    ? 'status-warning'
    : 'status-critical';

  return (
    <header className="top-nav">
      <div className="flex items-center gap-4 min-w-0">
        <NavLink to="/runtime" className="brand-mark shrink-0">
          ConfidenceOS
        </NavLink>
        <div className="hidden md:block h-8 w-px bg-[var(--border-strong)]" />
        <nav className="flex items-center gap-4 overflow-x-auto overflow-y-hidden min-w-0">
          {visibleItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
          {supportItems.length > 0 && (
            <select
              value={activeSupport}
              onChange={(event) => {
                if (event.target.value) navigate(event.target.value);
              }}
              className="industrial-control bg-transparent max-w-[168px] shrink-0 opacity-70 hover:opacity-100 transition-opacity text-[var(--text-muted)]"
              aria-label="Support views"
              title="Secondary support views"
            >
              <option value="">Support Views</option>
              {supportItems.map((item) => (
                <option key={item.path} value={item.path}>{item.label} - {item.status}</option>
              ))}
            </select>
          )}
        </nav>
      </div>

      <div className="flex items-center gap-3 shrink min-w-0 overflow-hidden">
        {authToken && authUser ? (
          <span
            className="caption-mono"
            style={{
              padding: '3px 9px',
              borderRadius: 4,
              fontWeight: 600,
              fontSize: 11,
              letterSpacing: '0.04em',
              border: `1px solid ${ROLE_BORDER[authUser.role] ?? '#555'}`,
              color: ROLE_COLOR[authUser.role] ?? 'var(--text-muted)',
              background: 'transparent',
              userSelect: 'none',
            }}
            title={`Signed in as ${authUser.username} (${authUser.role})`}
          >
            {authUser.role}
          </span>
        ) : (
          <select
            value={role}
            onChange={(event) => setRole(event.target.value)}
            className="industrial-control bg-transparent"
            aria-label="Role switcher"
          >
            {ROLES.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        )}

        <div className={`caption-mono shrink-0 ${alerts > 0 ? 'status-critical' : trustException.status}`}>
          {alerts > 0 ? `${alerts} Trust Alert${alerts > 1 ? 's' : ''}` : trustException.label}
        </div>
        {unackedAlarms > 0 && (
          <div className="caption-mono status-critical" title="ISA-18.2 unacknowledged alarms — use /api/alarms to acknowledge">
            {unackedAlarms} Unack Alarm{unackedAlarms > 1 ? 's' : ''}
          </div>
        )}

        {!runtimeReady && (
          <div
            className={`caption-mono shrink-0 ${readinessClass}`}
            title={healthError || systemHealth?.readiness?.issues?.map((issue) => issue.message).join(' | ') || 'Runtime readiness'}
          >
            {readinessLabel}
          </div>
        )}

        {location.pathname !== '/runtime' && location.pathname !== '/' && (
          <div className={`caption-mono shrink-0 ${healthClass}`}>
            Integrity {averageConfidence}%
          </div>
        )}

        <button
          onClick={() => setAlarmMuted(!muted)}
          className="industrial-control shrink-0 px-2"
          title={muted ? 'Alarm muted - click or press M to unmute' : 'Alarm sound on - click or press M to mute'}
          aria-label={muted ? 'Unmute alarm' : 'Mute alarm'}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '16px', lineHeight: 1 }}>
            {muted ? 'volume_off' : 'volume_up'}
          </span>
        </button>

        <div className="flex items-center gap-2 caption-mono shrink-0">
          <span className={`led-square ${connected ? 'status-safe dot-blink' : 'status-critical'}`} />
          <span>{connected ? 'LIVE' : 'OFFLINE'}</span>
        </div>

        <div className="flex items-center gap-2 caption-mono shrink-0" title={`Signed in as ${authUser?.username}`}>
          <span className="text-[var(--text-muted)] hidden 2xl:inline">{authUser?.username}</span>
          <button
            onClick={logout}
            className="industrial-control shrink-0 px-2"
            title="Sign out"
            aria-label="Sign out"
            style={{ fontSize: 11 }}
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
