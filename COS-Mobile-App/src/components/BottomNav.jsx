import { useLocation, useNavigate } from 'react-router-dom';
import useStore from '../store';

const ALL_TABS = [
  { path: '/alarms',    icon: '⚠',  label: 'Alarms',    roles: ['Operator', 'Maintenance', 'Engineer', 'Manager', 'Auditor'], badge: 'alarms' },
  { path: '/incidents', icon: '◉',  label: 'Incidents', roles: ['Operator', 'Maintenance', 'Engineer', 'Manager', 'Auditor'] },
  { path: '/tasks',     icon: '☑',  label: 'Tasks',     roles: ['Operator', 'Maintenance', 'Engineer', 'Manager'] },
  { path: '/handover',  icon: '⇄',  label: 'Handover',  roles: ['Operator', 'Maintenance', 'Engineer', 'Manager', 'Auditor'] },
  { path: '/settings',  icon: '⚙',  label: 'Settings',  roles: ['Operator', 'Maintenance', 'Engineer', 'Manager', 'Auditor'] },
];

export default function BottomNav() {
  const role    = useStore((s) => s.authUser?.role ?? '');
  const alarms  = useStore((s) => s.alarms);
  const location  = useLocation();
  const navigate  = useNavigate();

  const unackedCount = alarms.filter((a) => !a.acked).length;
  const tabs = ALL_TABS.filter((t) => t.roles.includes(role));

  return (
    <nav className="mobile-bottom-nav" aria-label="Main navigation">
      {tabs.map((tab) => (
        <button
          key={tab.path}
          className={`mobile-nav-tab ${location.pathname === tab.path ? 'active' : ''}`}
          onClick={() => navigate(tab.path)}
          aria-current={location.pathname === tab.path ? 'page' : undefined}
        >
          <span className="mobile-nav-tab-icon" aria-hidden="true">{tab.icon}</span>
          {tab.badge === 'alarms' && unackedCount > 0 && (
            <span className="nav-badge">{unackedCount > 9 ? '9+' : unackedCount}</span>
          )}
          <span>{tab.label}</span>
        </button>
      ))}
    </nav>
  );
}
