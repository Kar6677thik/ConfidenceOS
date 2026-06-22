import { useState } from 'react';
import useStore from '../store';

const ROLE_COLOR = {
  Operator:    '#22c55e',
  Maintenance: '#f97316',
  Engineer:    '#0a84ff',
  Manager:     '#a855f7',
  Auditor:     '#9ca3af',
};

function Toggle({ on, onToggle }) {
  return (
    <button
      className={`toggle-track ${on ? 'on' : 'off'}`}
      onClick={onToggle}
      aria-checked={on}
      role="switch"
    >
      <span className="toggle-thumb" />
    </button>
  );
}

export default function SettingsView() {
  const authUser            = useStore((s) => s.authUser);
  const darkMode            = useStore((s) => s.darkMode);
  const toggleDarkMode      = useStore((s) => s.toggleDarkMode);
  const logout              = useStore((s) => s.logout);
  const alarms              = useStore((s) => s.alarms);
  const tasks               = useStore((s) => s.tasks);
  const connected           = useStore((s) => s.connected);
  const notificationsEnabled = useStore((s) => s.notificationsEnabled);
  const enableNotifications = useStore((s) => s.enableNotifications);
  const disableNotifications = useStore((s) => s.disableNotifications);

  const [notifLoading, setNotifLoading] = useState(false);
  const [notifMsg, setNotifMsg]         = useState('');

  const handleNotifToggle = async () => {
    setNotifLoading(true);
    setNotifMsg('');
    if (notificationsEnabled) {
      await disableNotifications();
      setNotifMsg('Notifications turned off.');
    } else {
      if (!('Notification' in window) || !('serviceWorker' in navigator)) {
        setNotifMsg('Not supported in this browser.');
        setNotifLoading(false);
        return;
      }
      const result = await enableNotifications();
      if (result === 'granted')  setNotifMsg('Notifications enabled!');
      if (result === 'denied')   setNotifMsg('Permission denied. Enable in browser settings.');
      if (result === 'error')    setNotifMsg('Something went wrong. Try again.');
    }
    setNotifLoading(false);
  };

  const role = authUser?.role ?? '';
  const unacked = alarms.filter((a) => !a.acked).length;
  const pending = tasks.filter((t) => t.status === 'PENDING').length;

  return (
    <div>
      {/* Profile card */}
      <div className="section-label">Account</div>
      <div className="mobile-card">
        <div className="mobile-card-body">
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 44,
              height: 44,
              borderRadius: '50%',
              background: `${ROLE_COLOR[role] ?? 'var(--primary)'}22`,
              border: `2px solid ${ROLE_COLOR[role] ?? 'var(--primary)'}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 18,
              fontWeight: 700,
              color: ROLE_COLOR[role] ?? 'var(--primary)',
              flexShrink: 0,
            }}>
              {authUser?.username?.[0]?.toUpperCase() ?? '?'}
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>
                {authUser?.username}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 3 }}>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: '0.05em',
                    padding: '2px 8px',
                    borderRadius: 4,
                    border: `1px solid ${ROLE_COLOR[role] ?? 'var(--border)'}`,
                    color: ROLE_COLOR[role] ?? 'var(--text-muted)',
                  }}
                >
                  {role}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Quick stats */}
      <div className="section-label">Current Status</div>
      <div className="mobile-card">
        <div className="settings-row">
          <div>
            <div className="settings-row-label">Unacknowledged Alarms</div>
            <div className="settings-row-sub">Requires your attention</div>
          </div>
          <span style={{ fontSize: 18, fontWeight: 700, color: unacked > 0 ? 'var(--alarm-p1)' : 'var(--safe)' }}>
            {unacked}
          </span>
        </div>
        <div className="settings-row">
          <div>
            <div className="settings-row-label">Pending Tasks</div>
            <div className="settings-row-sub">In your work queue</div>
          </div>
          <span style={{ fontSize: 18, fontWeight: 700, color: pending > 0 ? 'var(--warning)' : 'var(--safe)' }}>
            {pending}
          </span>
        </div>
      </div>

      {/* Preferences */}
      <div className="section-label">Preferences</div>
      <div className="mobile-card">
        <div className="settings-row">
          <div>
            <div className="settings-row-label">Dark Mode</div>
            <div className="settings-row-sub">For low-light environments</div>
          </div>
          <Toggle on={darkMode} onToggle={toggleDarkMode} />
        </div>
        <div className="settings-row">
          <div>
            <div className="settings-row-label">Push Notifications</div>
            <div className="settings-row-sub">
              {notifLoading
                ? 'Requesting permission…'
                : notifMsg || 'Alarms and incidents direct to your phone'}
            </div>
          </div>
          <Toggle on={notificationsEnabled} onToggle={handleNotifToggle} />
        </div>
      </div>

      {/* App info */}
      <div className="section-label">About</div>
      <div className="mobile-card">
        <div className="settings-row">
          <div className="settings-row-label">Mode</div>
          {connected
            ? <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--safe)', background: 'rgba(47,107,47,0.08)', padding: '3px 9px', borderRadius: 4, border: '1px solid rgba(47,107,47,0.25)' }}>Live</span>
            : <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--primary)', background: 'rgba(0,90,160,0.08)', padding: '3px 9px', borderRadius: 4, border: '1px solid rgba(0,90,160,0.2)' }}>Demo</span>
          }
        </div>
        <div className="settings-row">
          <div className="settings-row-label">Version</div>
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>1.0.0</span>
        </div>
        <div className="settings-row">
          <div>
            <div className="settings-row-label">Read-only system</div>
            <div className="settings-row-sub">Does not write control commands or operate field devices</div>
          </div>
        </div>
      </div>

      {/* Sign out */}
      <button className="settings-sign-out-btn" onClick={logout}>
        Sign out
      </button>

      <div style={{ height: 8 }} />
    </div>
  );
}
