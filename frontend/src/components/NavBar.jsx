import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import useStore from '../store';

const ROLES = ['Operator', 'Maintenance', 'Engineer', 'Manager', 'Auditor'];

const NAV_ITEMS = [
  { path: '/runtime',    label: 'Runtime',       roles: ['Operator', 'Maintenance', 'Engineer', 'Manager', 'Auditor'] },
  { path: '/studio',     label: 'Studio',        roles: ['Engineer', 'Manager'] },
  { path: '/handover',   label: 'Shift Channel', roles: ['Operator', 'Maintenance', 'Engineer', 'Manager', 'Auditor'] },
];

const SUPPORT_ITEMS = [
  { path: '/integrity',  label: 'Instrument Integrity',   roles: ['Operator', 'Maintenance', 'Engineer', 'Manager', 'Auditor'] },
  { path: '/operator',   label: 'Operator Detail',        roles: ['Operator', 'Maintenance', 'Engineer', 'Manager'] },
  { path: '/predictions',label: 'Degradation Forecast',   roles: ['Operator', 'Maintenance', 'Engineer', 'Manager'] },
  { path: '/forensics',  label: 'Incident Replay',        roles: ['Engineer', 'Manager', 'Auditor'] },
  { path: '/graph',      label: 'Causal Graph',           roles: ['Engineer', 'Manager'] },
  { path: '/engineer',   label: 'Engineer Analysis',      roles: ['Engineer', 'Manager'] },
  { path: '/compliance', label: 'Compliance Report',      roles: ['Manager', 'Auditor'] },
  { path: '/sandbox',    label: 'Simulation Sandbox',     roles: ['Engineer'] },
];

function countActiveAlerts(confidence, massBalance, staleFlags) {
  const confidenceAlerts = (confidence || []).filter((item) => item.tier && item.tier !== 'HIGH').length;
  const massAlerts = massBalance?.flags?.length || 0;
  const staleAlerts = staleFlags?.length || 0;
  return confidenceAlerts + massAlerts + staleAlerts;
}

function worstTrustException(confidence, connected) {
  if (!connected) {
    return { label: 'Live trust state unavailable', status: 'status-critical' };
  }
  const rank = { QUARANTINED: 0, UNAVAILABLE: 1, DEGRADED: 2, SUBSTITUTED: 3, TRUSTED: 4, HIGH: 4 };
  const rows = (confidence || [])
    .map((item) => {
      const fallback = item.tier === 'LOW' || item.tier === 'CRITICAL' ? 'DEGRADED' : item.tier || 'TRUSTED';
      const trust = String(item.trust_state || fallback).toUpperCase();
      return { ...item, trust, rank: rank[trust] ?? 5 };
    })
    .sort((a, b) => a.rank - b.rank || (a.confidence_pct ?? 100) - (b.confidence_pct ?? 100));
  const lead = rows[0];
  if (!lead) {
    return { label: 'Awaiting live trust evidence', status: 'status-caution' };
  }
  if ((lead.rank ?? 5) <= 2) {
    return { label: `${lead.trust} ${lead.sensor_id || ''}`.trim(), status: lead.rank <= 1 ? 'status-critical' : 'status-warning' };
  }
  return { label: 'No active trust exceptions', status: 'status-safe' };
}

export default function NavBar() {
  const {
    connected,
    averageConfidence,
    role,
    setRole,
    confidence,
    massBalance,
    staleFlags,
  } = useStore();
  const location = useLocation();
  const navigate = useNavigate();
  const visibleItems = NAV_ITEMS.filter((item) => item.roles.includes(role));
  const supportItems = SUPPORT_ITEMS.filter((item) => item.roles.includes(role));
  const activeSupport = supportItems.some((item) => item.path === location.pathname) ? location.pathname : '';
  const alerts = countActiveAlerts(confidence, massBalance, staleFlags);
  const trustException = worstTrustException(confidence, connected);
  const healthClass = averageConfidence >= 80
    ? 'status-safe'
    : averageConfidence >= 50
    ? 'status-caution'
    : averageConfidence >= 20
    ? 'status-warning'
    : 'status-critical';

  return (
    <header className="top-nav">
      <div className="flex items-center gap-8 min-w-0">
        <NavLink to="/runtime" className="brand-mark shrink-0">
          ConfidenceOS
        </NavLink>
        <div className="hidden md:block h-8 w-px bg-[var(--border-strong)]" />
        <nav className="flex items-center gap-7 overflow-x-auto min-w-0">
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
              className="industrial-control bg-transparent max-w-[200px] shrink-0 opacity-70 hover:opacity-100 transition-opacity text-[var(--text-muted)]"
              aria-label="Support views"
              title="Secondary support views - not part of the primary demo path"
            >
              <option value="">Support Views</option>
              {supportItems.map((item) => (
                <option key={item.path} value={item.path}>{item.label}</option>
              ))}
            </select>
          )}
        </nav>
      </div>

      <div className="flex items-center gap-5 shrink-0">
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

        <div className={`caption-mono ${alerts > 0 ? 'status-critical' : trustException.status}`}>
          {alerts > 0 ? `${alerts} Trust Alert${alerts > 1 ? 's' : ''}` : trustException.label}
        </div>

        {location.pathname !== '/runtime' && location.pathname !== '/' && (
          <div className={`caption-mono ${healthClass}`}>
            Integrity {averageConfidence}%
          </div>
        )}

        <div className="flex items-center gap-2 caption-mono">
          <span className={`led-square ${connected ? 'status-safe dot-blink' : 'status-critical'}`} />
          <span>{connected ? 'LIVE' : 'OFFLINE'}</span>
        </div>
      </div>
    </header>
  );
}
