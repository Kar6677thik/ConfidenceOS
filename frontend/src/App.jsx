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
import RuntimePlatform from './components/RuntimePlatform';
import StudioWorkspace from './components/StudioWorkspace';
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
  const { connected, timestamp } = useStore();
  const [clock, setClock] = useState(() => new Date());

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
        <span className={connected ? 'status-safe' : 'status-critical'}>
          {connected ? 'API Online' : 'API Offline'}
        </span>
        {timestamp && (
          <span className="hidden lg:block">
            Last Tick: {new Date(timestamp * 1000).toLocaleTimeString()}
          </span>
        )}
      </div>
    </footer>
  );
}

const SHORTCUTS = [
  ['1', 'Navigate to Runtime'],
  ['2', 'Navigate to Studio (Engineer / Manager only)'],
  ['3', 'Navigate to Shift Channel'],
  ['M', 'Toggle alarm mute'],
  ['?', 'Toggle this help overlay'],
];

// App root
export default function App() {
  const [showHelp, setShowHelp] = useState(false);
  const connect = useStore((s) => s.connect);

  // Establish WS at app mount so every view gets live data, not just Runtime.
  // connect() is idempotent (store guards on _ws), so RuntimePlatform calling
  // it again on mount is harmless.
  useEffect(() => {
    connect();
  }, [connect]);

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
