/**
 * App.jsx - ConfidenceOS Root Router
 *
 * All page-level views are in frontend/src/views/.
 * Shared utility components remain in frontend/src/components/.
 */

import { useEffect, useState } from 'react';
import { Routes, Route } from 'react-router-dom';
import useStore from './store';
import useKeyboardShortcuts from './lib/useKeyboardShortcuts';

// Navigation
import NavBar from './components/NavBar';
import ErrorBoundary from './components/ErrorBoundary';
import AbnormalityLab from './components/AbnormalityLab';
import RuntimePlatform from './components/RuntimePlatform';
import StudioWorkspace from './components/StudioWorkspace';
import WorkQueue from './components/WorkQueue';
import ShiftChannel from './components/ShiftChannel';

// Secondary support views
import FleetOverview      from './views/FleetOverview';
import OperatorDashboard  from './views/OperatorDashboard';
import PredictiveTimeline from './views/PredictiveTimeline';
import ForensicsReplay    from './views/ForensicsReplay';
import CausalGraph        from './views/CausalGraph';
import CompliancePortal   from './views/CompliancePortal';
import SandboxSimulator   from './views/SandboxSimulator';
import EngineerDeepDive   from './views/EngineerDeepDive';

// Bottom status bar
function BottomStatus() {
  const { connected, timestamp, systemHealth, healthError, lastHealthAt } = useStore();
  const [clock, setClock] = useState(() => new Date());
  const [labOpen, setLabOpen] = useState(false);
  const readiness = systemHealth?.readiness_summary || (healthError ? 'api_unreachable' : 'unknown');
  const readinessLabel = readiness === 'ready'
    ? 'Runtime ready'
    : readiness === 'degraded'
    ? 'Runtime degraded'
    : readiness === 'blocked'
    ? 'Runtime blocked'
    : healthError
    ? 'API unreachable'
    : 'Runtime warming up';
  const readinessClass = readiness === 'ready'
    ? 'status-safe'
    : readiness === 'degraded' || readiness === 'unknown'
    ? 'status-warning'
    : 'status-critical';

  useEffect(() => {
    const timer = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <footer className="bottom-status">
      <span>ConfidenceOS read-only trust-aware HMI layer</span>
      <div className="flex items-center gap-6">
        <span className="hidden md:block">System Logs</span>
        <span>UTC: {clock.toLocaleTimeString()}</span>
        <span className={readinessClass} title={healthError || systemHealth?.readiness?.issues?.map((issue) => issue.message).join(' | ') || 'Backend readiness'}>
          {readinessLabel}
        </span>
        <span className={connected ? 'status-safe' : 'status-critical'}>
          {connected ? 'Live stream connected' : 'Live stream offline'}
        </span>
        {timestamp && (
          <span className="hidden lg:block">
            Last Tick: {new Date(timestamp * 1000).toLocaleTimeString()}
          </span>
        )}
        {lastHealthAt && (
          <span className="hidden xl:block">
            Health: {new Date(lastHealthAt).toLocaleTimeString()}
          </span>
        )}
        <button
          onClick={() => setLabOpen((v) => !v)}
          title="Simulation Lab (training source controls)"
          aria-label="Toggle Simulation Lab"
          className="flex items-center"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: labOpen ? 'var(--primary, #0a84ff)' : 'inherit', padding: 0 }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 3h6M9 3v6l-5 9a1 1 0 00.9 1.5h14.2A1 1 0 0020 18l-5-9V3" />
          </svg>
        </button>
      </div>
      {labOpen && <AbnormalityLab onClose={() => setLabOpen(false)} />}
    </footer>
  );
}

const SHORTCUTS = [
  ['1', 'Navigate to Runtime'],
  ['2', 'Navigate to Shift Channel'],
  ['3', 'Navigate to Studio (Engineer / Manager only)'],
  ['4', 'Open Verification Work Queue support view'],
  ['M', 'Toggle alarm mute'],
  ['?', 'Toggle this help overlay'],
];

// App root
export default function App() {
  const [showHelp, setShowHelp] = useState(false);
  const connect = useStore((s) => s.connect);
  const fetchSystemHealth = useStore((s) => s.fetchSystemHealth);

  // Establish WS at app mount so every view gets live data, not just Runtime.
  // connect() is idempotent (store guards on _ws), so RuntimePlatform calling
  // it again on mount is harmless.
  useEffect(() => {
    connect();
  }, [connect]);

  useEffect(() => {
    fetchSystemHealth();
    const timer = setInterval(fetchSystemHealth, 10000);
    return () => clearInterval(timer);
  }, [fetchSystemHealth]);

  useKeyboardShortcuts({ onHelpToggle: () => setShowHelp((v) => !v) });

  // Close help overlay on Escape
  useEffect(() => {
    if (!showHelp) return;
    function onEsc(e) { if (e.key === 'Escape') setShowHelp(false); }
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [showHelp]);

  return (
    <div className="industrial-app">
      <NavBar />
      <main className="industrial-main">
        <ErrorBoundary>
        <Routes>
          {/* Main workspace platform routes */}
          <Route path="/"            element={<RuntimePlatform />} />
          <Route path="/runtime"     element={<RuntimePlatform />} />
          <Route path="/work-queue"  element={<WorkQueue />} />
          <Route path="/studio"      element={<StudioWorkspace />} />
          <Route path="/handover"    element={<ShiftChannel />} />

          {/* Modular analytical views */}
          <Route path="/integrity"  element={<FleetOverview />} />
          <Route path="/operator"   element={<OperatorDashboard />} />
          <Route path="/predictions" element={<PredictiveTimeline />} />
          <Route path="/forensics"   element={<ForensicsReplay />} />
          <Route path="/graph"       element={<CausalGraph />} />
          <Route path="/compliance"  element={<CompliancePortal />} />
          <Route path="/sandbox"     element={<SandboxSimulator />} />
          <Route path="/engineer"    element={<EngineerDeepDive />} />
        </Routes>
        </ErrorBoundary>
      </main>
      <BottomStatus />

      {/* Keyboard shortcuts help overlay */}
      {showHelp && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.72)' }}
          onClick={() => setShowHelp(false)}
        >
          <div
            className="industrial-card p-6 max-w-sm w-full mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <span className="text-[var(--text)] font-semibold">Keyboard Shortcuts</span>
              <button
                className="caption-mono text-[var(--text-muted)] hover:text-[var(--text)]"
                onClick={() => setShowHelp(false)}
                aria-label="Close shortcuts overlay"
              >
                ESC
              </button>
            </div>
            <div className="space-y-3">
              {SHORTCUTS.map(([key, desc]) => (
                <div key={key} className="flex items-start gap-4">
                  <kbd className="industrial-badge font-mono shrink-0 text-[var(--text)] px-2 py-0.5 min-w-[2rem] text-center">
                    {key}
                  </kbd>
                  <span className="caption-mono text-[var(--text-muted)]">{desc}</span>
                </div>
              ))}
            </div>
            <p className="caption-mono text-[var(--text-muted)] mt-4 pt-3 border-t border-[var(--border)]">
              Shortcuts are disabled while typing in inputs.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
