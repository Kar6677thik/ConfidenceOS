import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  MOCK_ALARMS,
  MOCK_INCIDENTS,
  MOCK_HANDOVER_DEBT,
  MOCK_TASKS,
  MOCK_HANDOVER,
  DEMO_CREDS,
} from './mock/data';

const API          = 'https://cfosbd.karthiksurkanti.in';
const WS           = 'wss://cfosbd.karthiksurkanti.in/ws';
const VAPID_PUBLIC = 'BO4lfShf4rqt3QxHaAdoeyO1DwccHqHzXptI9LGH4IqmOddgaTZ1cHa9wR6fM7dNyIv9lzjMsOQFXIURTywrrM0';

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64  = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw     = atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

function decodeJwt(token) {
  try {
    const b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(b64));
  } catch {
    return {};
  }
}

const USERNAME_ROLE = {
  operator: 'Operator',
  maint:    'Maintenance',
  engineer: 'Engineer',
  manager:  'Manager',
  auditor:  'Auditor',
};

// Demo tokens are prefixed "demo-" — never sent to the backend
const isRealToken = (t) => Boolean(t && !String(t).startsWith('demo-'));

let wsInstance = null;

const useStore = create(
  persist(
    (set, get) => ({
      // ── Auth ──
      authToken:   null,
      authUser:    null,
      authLoading: false,
      authError:   null,

      // ── Prefs ──
      darkMode: false,
      notificationsEnabled: false,

      // ── Live state ──
      connected: false,

      // ── Data (mock by default; replaced by live data after real login) ──
      alarms:      MOCK_ALARMS.map((a) => ({ ...a })),
      incidents:   MOCK_INCIDENTS,
      handoverDebt: MOCK_HANDOVER_DEBT,
      tasks:       MOCK_TASKS.map((t) => ({ ...t })),
      handoverData: MOCK_HANDOVER,

      // ── Login ──
      async login(username, password) {
        set({ authLoading: true, authError: null });

        // 1. Check demo credentials locally — always works offline
        const demoCred = DEMO_CREDS.find(
          (c) => c.username === username && c.password === password,
        );
        if (demoCred) {
          await new Promise((r) => setTimeout(r, 350));
          set({
            authLoading: false,
            authError:   null,
            authToken:   `demo-${Date.now()}`,
            authUser:    { username, role: demoCred.label },
          });
          // Silently upgrade to real JWT in background (no UI disruption)
          get()._upgradeToRealToken(username, password, demoCred.label);
          return;
        }

        // 2. Non-demo credentials — hit the real backend
        try {
          const res = await fetch(`${API}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ username, password }),
          });
          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            set({ authLoading: false, authError: err.detail || 'Invalid credentials.' });
            return;
          }
          const data = await res.json();
          const decoded = decodeJwt(data.access_token ?? '');
          const role = data.role ?? decoded.role ?? decoded.user_role ?? USERNAME_ROLE[username] ?? 'Operator';
          set({
            authLoading: false,
            authError:   null,
            authToken:   data.access_token,
            authUser:    { username: data.username ?? decoded.sub ?? username, role },
          });
          get().connect();
          get().fetchAlarms();
          get().fetchTasks();
          get().fetchIncidents();
          get().fetchHandover();
        } catch {
          set({ authLoading: false, authError: 'Cannot reach server. Check your connection.' });
        }
      },

      // Background JWT upgrade — fires after demo login succeeds
      async _upgradeToRealToken(username, password, role) {
        try {
          const res = await fetch(`${API}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ username, password }),
          });
          if (!res.ok) return;
          const data = await res.json();
          if (!data.access_token) return;
          const decoded = decodeJwt(data.access_token);
          const realRole = data.role ?? decoded.role ?? decoded.user_role ?? role;
          set((s) => ({
            authToken: data.access_token,
            authUser:  { ...s.authUser, role: realRole },
          }));
          get().connect();
          get().fetchAlarms();
          get().fetchTasks();
          get().fetchIncidents();
          get().fetchHandover();
        } catch {
          // Backend down — stay in demo mode, user is already on the right screen
        }
      },

      logout() {
        if (wsInstance) { wsInstance.close(); wsInstance = null; }
        set({
          authToken:   null,
          authUser:    null,
          authError:   null,
          connected:   false,
          alarms:      MOCK_ALARMS.map((a) => ({ ...a })),
          incidents:   MOCK_INCIDENTS,
          handoverDebt: MOCK_HANDOVER_DEBT,
          tasks:       MOCK_TASKS.map((t) => ({ ...t })),
        });
      },

      // ── WebSocket — only opens with a real JWT, not demo tokens ──
      connect() {
        if (wsInstance) { wsInstance.close(); wsInstance = null; }
        const token = get().authToken;
        if (!isRealToken(token)) return; // skip for demo tokens

        try {
          const ws = new WebSocket(`${WS}?token=${token}`);
          wsInstance = ws;

          ws.onopen  = () => set({ connected: true });
          ws.onerror = () => {};

          ws.onmessage = (e) => {
            try {
              const msg = JSON.parse(e.data);
              const updates = {};
              if (msg.unacked_alarms !== undefined) {
                const prev = get().alarms.filter((a) => !a.acked).length;
                if (msg.unacked_alarms !== prev) get().fetchAlarms();
              }
              if (Array.isArray(msg.incidents))              updates.incidents    = msg.incidents;
              if (Array.isArray(msg.handover_debt?.entries)) updates.handoverDebt = msg.handover_debt.entries;
              if (Object.keys(updates).length) set(updates);
            } catch {}
          };

          ws.onclose = () => {
            set({ connected: false });
            wsInstance = null;
            // Only retry if still holding a real token
            setTimeout(() => {
              if (isRealToken(get().authToken)) get().connect();
            }, 5000);
          };
        } catch {
          set({ connected: false });
        }
      },

      // ── Fetch alarm list ──
      async fetchAlarms() {
        const token = get().authToken;
        if (!isRealToken(token)) return; // mock data is already set
        try {
          const res = await fetch(`${API}/api/alarms`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!res.ok) return;
          const data = await res.json();
          const raw = Array.isArray(data) ? data : (data.alarms ?? []);
          const alarms = raw.map((a) => ({
            id:       a.id ?? a.alarm_id ?? String(Math.random()),
            tag:      a.tag ?? a.sensor_id ?? a.source ?? 'UNKNOWN',
            desc:     a.description ?? a.message ?? a.desc ?? 'Alarm',
            priority: a.priority ?? (a.level === 'critical' ? 'P1' : a.level === 'warning' ? 'P2' : 'P3'),
            area:     a.area ?? a.plant_id ?? '—',
            raisedAt: a.raised_at
              ? new Date(a.raised_at).getTime()
              : (a.timestamp ? a.timestamp * 1000 : Date.now()),
            acked: a.acked ?? a.acknowledged ?? false,
          }));
          set({ alarms });
        } catch {}
      },

      // ── Acknowledge ──
      async acknowledgeAlarm(id) {
        set((s) => ({ alarms: s.alarms.map((a) => (a.id === id ? { ...a, acked: true } : a)) }));
        const token = get().authToken;
        if (!isRealToken(token)) return;
        try {
          await fetch(`${API}/api/alarms/acknowledge`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ alarm_id: id }),
          });
        } catch {}
      },

      acknowledgeAll() {
        get().alarms.filter((a) => !a.acked).forEach((a) => get().acknowledgeAlarm(a.id));
      },

      // ── Tasks ──
      async fetchTasks() {
        const token = get().authToken;
        if (!isRealToken(token)) return;
        try {
          const res = await fetch(`${API}/api/verification-tasks`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!res.ok) return;
          const data = await res.json();
          const raw = Array.isArray(data) ? data : (data.tasks ?? []);
          const STATE_MAP = { ACCEPTED: 'DONE', REQUESTED: 'PENDING', EXPIRED: 'DONE' };
          const tasks = raw.map((t) => ({
            id:     t.task_id ?? t.token_id ?? String(Math.random()),
            tag:    t.sensor_id ?? 'UNKNOWN',
            desc:   t.verification_method ?? t.verification_type ?? 'Field verification',
            role:   t.assigned_role ?? 'Maintenance',
            status: STATE_MAP[t.state] ?? t.state ?? 'PENDING',
            dueIn:  t.valid_until
              ? (() => {
                  const mins = Math.round((t.valid_until * 1000 - Date.now()) / 60000);
                  if (mins <= 0) return 'Overdue';
                  if (mins < 60) return `${mins}m`;
                  return `${Math.round(mins / 60)}h`;
                })()
              : '—',
          }));
          set({ tasks });
        } catch {}
      },

      async completeTask(id) {
        set((s) => ({ tasks: s.tasks.map((t) => (t.id === id ? { ...t, status: 'DONE' } : t)) }));
        const token = get().authToken;
        if (!isRealToken(token)) return;
        try {
          await fetch(`${API}/api/verification-tasks/state`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_id: id, state: 'ACCEPTED' }),
          });
        } catch {}
      },

      // ── Incidents ──
      async fetchIncidents() {
        const token = get().authToken;
        if (!isRealToken(token)) return;
        try {
          const res = await fetch(`${API}/api/shift-channel`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!res.ok) return;
          const data = await res.json();
          const raw = Array.isArray(data.incidents) ? data.incidents : [];
          if (raw.length > 0) set({ incidents: raw });
        } catch {}
      },

      // ── Handover ──
      async fetchHandover() {
        const token = get().authToken;
        if (!isRealToken(token)) return;
        try {
          const [debtRes, briefRes] = await Promise.all([
            fetch(`${API}/api/handover/debt`, { headers: { Authorization: `Bearer ${token}` } }),
            fetch(`${API}/api/handover/latest`, { headers: { Authorization: `Bearer ${token}` } }),
          ]);

          if (debtRes.ok) {
            const debtData = await debtRes.json();
            const rawDebt = Array.isArray(debtData.entries)
              ? debtData.entries
              : Array.isArray(debtData)
              ? debtData
              : [];
            if (rawDebt.length > 0) {
              set({
                handoverDebt: rawDebt.map((e) => ({
                  id:        e.id ?? String(Math.random()),
                  topic:     e.topic ?? e.description ?? e.sensor_id ?? 'Open item',
                  urgency:   e.urgency ?? (e.severity === 'high' ? 'High' : e.severity === 'medium' ? 'Medium' : 'Low'),
                  fromShift: e.from_shift ?? e.shift ?? 'Previous shift',
                })),
              });
            }
          }

          if (briefRes.ok) {
            const briefData = await briefRes.json();
            const brief = briefData.brief ?? briefData;
            if (brief && brief.shift) {
              set({
                handoverData: {
                  shift:           brief.shift ?? brief.shift_name ?? MOCK_HANDOVER.shift,
                  supervisor:      brief.supervisor ?? brief.operator ?? MOCK_HANDOVER.supervisor,
                  startTime:       brief.start_time ?? brief.startTime ?? MOCK_HANDOVER.startTime,
                  openItems:       Array.isArray(brief.open_items)
                    ? brief.open_items.map((item, i) => ({
                        urgency: item.urgency ?? 'Medium',
                        text:    item.text ?? item.description ?? String(item),
                      }))
                    : MOCK_HANDOVER.openItems,
                  equipmentStatus: Array.isArray(brief.equipment_status)
                    ? brief.equipment_status.map((eq) => ({
                        tag:    eq.tag ?? eq.sensor_id ?? 'UNKNOWN',
                        area:   eq.area ?? '—',
                        status: eq.status ?? 'safe',
                      }))
                    : MOCK_HANDOVER.equipmentStatus,
                  notes: brief.notes ?? brief.summary ?? MOCK_HANDOVER.notes,
                },
              });
            }
          }
        } catch {}
      },

      // ── Prefs ──
      toggleDarkMode() {
        set((s) => ({ darkMode: !s.darkMode }));
      },

      // ── Push notifications ──
      async enableNotifications() {
        try {
          const permission = await Notification.requestPermission();
          if (permission !== 'granted') return 'denied';

          const reg = await navigator.serviceWorker.ready;
          const existing = await reg.pushManager.getSubscription();
          const sub = existing ?? await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC),
          });

          const token = get().authToken;
          if (isRealToken(token)) {
            await fetch(`${API}/api/push/subscribe`, {
              method: 'POST',
              headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
              body: JSON.stringify(sub),
            }).catch(() => {});
          }

          set({ notificationsEnabled: true });
          return 'granted';
        } catch {
          return 'error';
        }
      },

      async disableNotifications() {
        try {
          const reg = await navigator.serviceWorker.ready;
          const sub = await reg.pushManager.getSubscription();
          if (sub) await sub.unsubscribe();
        } catch {}
        set({ notificationsEnabled: false });
      },
    }),
    {
      name: 'cfos-field-v1',
      partialize: (s) => ({
        authToken:            s.authToken,
        authUser:             s.authUser,
        darkMode:             s.darkMode,
        notificationsEnabled: s.notificationsEnabled,
      }),
    },
  ),
);

export default useStore;
