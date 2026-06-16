/**
 * App.jsx - ConfidenceOS Root Router
 *
 * All page-level views are in frontend/src/views/.
 * Shared utility components remain in frontend/src/components/.
 */

import { useEffect, useState } from 'react';
import { Routes, Route } from 'react-router-dom';
import useStore from './store';

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

// App root
export default function App() {
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
    </div>
  );
}
