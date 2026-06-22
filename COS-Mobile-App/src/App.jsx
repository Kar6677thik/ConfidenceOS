import { useEffect, useRef, useState } from 'react';
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import useStore from './store';
import BottomNav from './components/BottomNav';
import LoginView    from './views/LoginView';
import AlarmsView   from './views/AlarmsView';
import IncidentsView from './views/IncidentsView';
import TasksView    from './views/TasksView';
import HandoverView from './views/HandoverView';
import SettingsView from './views/SettingsView';

const ROLE_COLOR = {
  Operator:    '#22c55e',
  Maintenance: '#f97316',
  Engineer:    '#0a84ff',
  Manager:     '#a855f7',
  Auditor:     '#9ca3af',
};

const ROLE_HOME = {
  Operator:    '/alarms',
  Maintenance: '/tasks',
  Engineer:    '/tasks',
  Manager:     '/incidents',
  Auditor:     '/incidents',
};

function MobileHeader() {
  const authUser       = useStore((s) => s.authUser);
  const darkMode       = useStore((s) => s.darkMode);
  const connected      = useStore((s) => s.connected);
  const toggleDarkMode = useStore((s) => s.toggleDarkMode);
  const role = authUser?.role ?? '';

  return (
    <header className="mobile-header">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div>
          <div className="mobile-header-brand">ConfidenceOS</div>
          <div className="mobile-header-sub">Field</div>
        </div>
        {/* Live connection pip */}
        <span
          title={connected ? 'Live — connected to server' : 'Connecting…'}
          style={{
            width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
            background: connected ? 'var(--safe)' : 'var(--text-muted)',
            boxShadow: connected ? '0 0 0 2px rgba(47,107,47,0.3)' : 'none',
            transition: 'background 0.4s',
          }}
        />
      </div>
      <div className="mobile-header-right">
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: '0.05em',
            padding: '3px 8px',
            borderRadius: 4,
            border: `1px solid ${ROLE_COLOR[role] ?? 'var(--border)'}`,
            color: ROLE_COLOR[role] ?? 'var(--text-muted)',
            userSelect: 'none',
          }}
        >
          {role}
        </span>
        <button
          onClick={toggleDarkMode}
          style={{
            fontSize: 16,
            background: 'none',
            border: 'none',
            padding: '2px 4px',
            color: 'var(--text-muted)',
            lineHeight: 1,
          }}
          title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label="Toggle dark mode"
        >
          {darkMode ? '☀' : '☾'}
        </button>
      </div>
    </header>
  );
}

export default function App() {
  const authToken      = useStore((s) => s.authToken);
  const authUser       = useStore((s) => s.authUser);
  const darkMode       = useStore((s) => s.darkMode);
  const navigate       = useNavigate();
  const prevAuthRef    = useRef(null);

  // PWA install prompt
  const [installPrompt, setInstallPrompt] = useState(null);
  const [showPwaBanner, setShowPwaBanner] = useState(false);

  const connected           = useStore((s) => s.connected);
  const connect             = useStore((s) => s.connect);
  const fetchAlarms         = useStore((s) => s.fetchAlarms);
  const fetchTasks          = useStore((s) => s.fetchTasks);
  const fetchIncidents      = useStore((s) => s.fetchIncidents);
  const fetchHandover       = useStore((s) => s.fetchHandover);
  const notificationsEnabled = useStore((s) => s.notificationsEnabled);
  const enableNotifications = useStore((s) => s.enableNotifications);

  // Re-establish WebSocket + fetch all data after page refresh (auth is persisted, WS is not)
  useEffect(() => {
    if (authToken && !String(authToken).startsWith('demo-')) {
      connect();
      fetchAlarms();
      fetchTasks();
      fetchIncidents();
      fetchHandover();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Demo banner dismiss
  const [demoBannerDismissed, setDemoBannerDismissed] = useState(false);

  // Apply dark mode to document
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', darkMode ? 'dark' : 'light');
  }, [darkMode]);

  // Capture PWA install prompt
  useEffect(() => {
    const handler = (e) => {
      e.preventDefault();
      setInstallPrompt(e);
      setShowPwaBanner(true);
    };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  // Post-login redirect + auto notification prompt (like Android apps)
  useEffect(() => {
    if (authUser && !prevAuthRef.current) {
      navigate(ROLE_HOME[authUser.role] ?? '/alarms', { replace: true });
      // Ask for notification permission on first login if not already decided
      if (!notificationsEnabled && 'Notification' in window && Notification.permission === 'default') {
        setTimeout(() => enableNotifications(), 1500);
      }
    }
    prevAuthRef.current = authUser;
  }, [authUser, navigate, notificationsEnabled, enableNotifications]);

  if (!authToken) return <LoginView />;

  const handleInstall = async () => {
    if (!installPrompt) return;
    installPrompt.prompt();
    const { outcome } = await installPrompt.userChoice;
    if (outcome === 'accepted') {
      setShowPwaBanner(false);
      setInstallPrompt(null);
    }
  };

  return (
    <div className="mobile-app">
      <MobileHeader />

      {/* PWA install banner */}
      {showPwaBanner && (
        <div className="pwa-banner">
          <span>Add ConfidenceOS to your home screen for quick access</span>
          <button className="pwa-install-btn" onClick={handleInstall}>Install</button>
          <button className="pwa-dismiss-btn" onClick={() => setShowPwaBanner(false)} aria-label="Dismiss">×</button>
        </div>
      )}

      {/* Only show connecting banner when using a real token but WS isn't up yet */}
      {!demoBannerDismissed && !connected && authToken && !String(authToken).startsWith('demo-') && (
        <div className="demo-banner">
          <span>⚡ Connecting to server…</span>
          <button
            className="demo-banner-dismiss"
            onClick={() => setDemoBannerDismissed(true)}
            aria-label="Dismiss"
          >
            ×
          </button>
        </div>
      )}

      <main className="mobile-content">
        <Routes>
          <Route path="/"          element={<Navigate to="/alarms" replace />} />
          <Route path="/alarms"    element={<AlarmsView />} />
          <Route path="/incidents" element={<IncidentsView />} />
          <Route path="/tasks"     element={<TasksView />} />
          <Route path="/handover"  element={<HandoverView />} />
          <Route path="/settings"  element={<SettingsView />} />
          <Route path="*"          element={<Navigate to="/alarms" replace />} />
        </Routes>
      </main>

      <BottomNav />
    </div>
  );
}
