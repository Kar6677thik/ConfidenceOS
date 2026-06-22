import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching';
import { NavigationRoute, registerRoute } from 'workbox-routing';
import { NetworkFirst } from 'workbox-strategies';

// Injected by vite-plugin-pwa at build time
precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

// SPA fallback — serve index.html for all navigation requests
registerRoute(
  new NavigationRoute(
    new NetworkFirst({ cacheName: 'cfos-nav' }),
    { denylist: [/^\/api\//] },
  ),
);

// Skip waiting immediately when a new SW is available
self.addEventListener('message', (e) => {
  if (e.data?.type === 'SKIP_WAITING') self.skipWaiting();
});

// ── Push notification handler ──────────────────────────────────────────────
self.addEventListener('push', (event) => {
  let payload = {};
  try { payload = event.data?.json() ?? {}; } catch {}

  const title    = payload.title    ?? 'ConfidenceOS Alert';
  const body     = payload.body     ?? 'New plant event requires attention.';
  const priority = payload.priority ?? 'P3';
  const url      = payload.url      ?? '/alarms';

  const options = {
    body,
    icon:  '/icon-192.png',
    badge: '/icon-192.png',
    tag:   payload.tag ?? 'cfos-alert',     // groups duplicate notifications
    renotify: true,
    data: { url },
    requireInteraction: priority === 'P1', // P1 stays until dismissed
    actions: [
      { action: 'view',    title: 'View' },
      { action: 'dismiss', title: 'Dismiss' },
    ],
    vibrate: priority === 'P1' ? [200, 100, 200, 100, 200] : [200],
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// ── Notification click handler ─────────────────────────────────────────────
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  if (event.action === 'dismiss') return;

  const targetUrl = event.notification.data?.url ?? '/alarms';

  event.waitUntil(
    clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((list) => {
        // Focus existing window if already open
        const existing = list.find((c) => 'focus' in c);
        if (existing) {
          existing.navigate(targetUrl);
          return existing.focus();
        }
        return clients.openWindow(targetUrl);
      }),
  );
});
