import { NavLink, useLocation } from 'react-router-dom';
import useStore from '../store';

const ROLES = ['Operator', 'Engineer', 'Manager', 'Auditor'];

const NAV_ITEMS = [
  { path: '/', label: 'Fleet', icon: '◆', roles: ['Operator', 'Engineer', 'Manager', 'Auditor'] },
  { path: '/operator', label: 'Operator', icon: '◉', roles: ['Operator', 'Engineer', 'Manager'] },
  { path: '/predictions', label: 'Predictions', icon: '◇', roles: ['Operator', 'Engineer', 'Manager'] },
  { path: '/forensics', label: 'Forensics', icon: '◈', roles: ['Engineer', 'Manager', 'Auditor'] },
  { path: '/graph', label: 'Graph', icon: '⬡', roles: ['Engineer', 'Manager'] },
  { path: '/compliance', label: 'Compliance', icon: '◫', roles: ['Manager', 'Auditor'] },
  { path: '/sandbox', label: 'Sandbox', icon: '⬢', roles: ['Engineer'] },
];

export default function NavBar() {
  const { connected, averageConfidence, role, setRole, plantId } = useStore();
  const location = useLocation();

  const visibleItems = NAV_ITEMS.filter(item => item.roles.includes(role));

  // Health color
  const healthColor = averageConfidence >= 80
    ? 'text-emerald-400'
    : averageConfidence >= 50
    ? 'text-amber-400'
    : averageConfidence >= 20
    ? 'text-orange-400'
    : 'text-red-400';

  return (
    <header className="flex items-center justify-between px-4 py-2 bg-gray-900/90 backdrop-blur-xl border-b border-gray-800/50 shrink-0 z-50">
      {/* Left: Logo */}
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-extrabold tracking-tight text-gray-100">
          Confidence<span className="text-cyan-400">OS</span>
        </h1>
        <div className="flex items-center gap-1.5">
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${connected ? 'bg-emerald-400 dot-blink' : 'bg-red-400'}`} />
          <span className="text-[10px] text-gray-500 font-medium">
            {connected ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
      </div>

      {/* Center: Nav tabs */}
      <nav className="flex items-center gap-0.5">
        {visibleItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) => `
              flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200
              ${isActive
                ? 'bg-cyan-500/15 text-cyan-400 shadow-sm shadow-cyan-500/10'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
              }
            `}
          >
            <span className="text-[10px]">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Right: Role + Health */}
      <div className="flex items-center gap-4">
        {/* Role selector */}
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="bg-gray-800/60 border border-gray-700/50 rounded-lg px-2.5 py-1 text-xs text-gray-300 font-medium focus:outline-none focus:ring-1 focus:ring-cyan-500/50 cursor-pointer"
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>

        {/* Health score (only show when on plant page) */}
        {location.pathname !== '/' && (
          <div className="text-right">
            <p className="text-[9px] text-gray-500 uppercase tracking-wider font-semibold">Health</p>
            <p className={`text-lg font-extrabold tabular-nums leading-none ${healthColor}`}>
              {averageConfidence}%
            </p>
          </div>
        )}
      </div>
    </header>
  );
}
