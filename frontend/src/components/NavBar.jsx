import { NavLink, useLocation } from 'react-router-dom';
import useStore from '../store';

const ROLES = ['Operator', 'Engineer', 'Manager', 'Auditor'];

const NAV_ITEMS = [
  { path: '/', label: 'Fleet', roles: ['Operator', 'Engineer', 'Manager', 'Auditor'] },
  { path: '/operator', label: 'Plant A', roles: ['Operator', 'Engineer', 'Manager'] },
  { path: '/predictions', label: 'Predictions', roles: ['Operator', 'Engineer', 'Manager'] },
  { path: '/forensics', label: 'Forensics', roles: ['Engineer', 'Manager', 'Auditor'] },
  { path: '/graph', label: 'Graph', roles: ['Engineer', 'Manager'] },
  { path: '/compliance', label: 'Compliance', roles: ['Manager', 'Auditor'] },
  { path: '/sandbox', label: 'Sandbox', roles: ['Engineer'] },
];

function countActiveAlerts(confidence, massBalance, staleFlags) {
  const confidenceAlerts = (confidence || []).filter((item) => item.tier && item.tier !== 'HIGH').length;
  const massAlerts = massBalance?.flags?.length || 0;
  const staleAlerts = staleFlags?.length || 0;
  return confidenceAlerts + massAlerts + staleAlerts;
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
  const visibleItems = NAV_ITEMS.filter((item) => item.roles.includes(role));
  const alerts = countActiveAlerts(confidence, massBalance, staleFlags);
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
        <NavLink to="/" className="brand-mark shrink-0">
          ConfidenceOS
        </NavLink>
        <div className="hidden md:block h-8 w-px bg-[var(--border-strong)]" />
        <nav className="flex items-center gap-7 overflow-x-auto">
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

        <div className={`caption-mono ${alerts > 0 ? 'status-critical' : 'status-safe'}`}>
          Active Alert Counter: {alerts}
        </div>

        {location.pathname !== '/' && (
          <div className={`caption-mono ${healthClass}`}>
            Health {averageConfidence}%
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
