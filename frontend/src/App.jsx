import { useEffect, useState, useMemo } from 'react';
import useStore from './store';
import SensorCard from './components/SensorCard';
import MassBalanceChart from './components/MassBalanceChart';
import HealthTimeline from './components/HealthTimeline';
import HandoverBrief from './components/HandoverBrief';
import StartupBanner from './components/StartupBanner';
import FlagBar from './components/FlagBar';

/**
 * App — ConfidenceOS Dashboard (Module 7)
 *
 * PRD §5.1 layout:
 *   Top bar:    Plant name | Mode | Time | Health score | Toggle
 *   Left 40%:   Sensor grid (6 cards)
 *   Center 35%: Mass-balance chart (3 live lines)
 *   Right 25%:  Health timeline + Handover brief
 *   Bottom:     Active flags bar
 */

// ── Top Bar ──────────────────────────────────────────────────────────────────

function TopBar({ mode, averageConfidence, connected }) {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const isStartup = mode?.is_active ?? false;
  const modeName = mode?.mode ?? 'NORMAL';

  // Health score color
  const healthColor = averageConfidence >= 80 ? 'text-emerald-400'
    : averageConfidence >= 50 ? 'text-amber-400'
    : averageConfidence >= 20 ? 'text-orange-400'
    : 'text-red-400';

  return (
    <header className="no-print flex items-center justify-between px-6 py-3 bg-gray-900/80 backdrop-blur-xl border-b border-gray-800/50">
      {/* Left: Plant name + connection */}
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-extrabold tracking-tight text-gray-100">
          Confidence<span className="text-cyan-400">OS</span>
        </h1>
        <div className="flex items-center gap-1.5">
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${connected ? 'bg-emerald-400 dot-blink' : 'bg-red-400'}`} />
          <span className="text-[10px] text-gray-600 font-medium">
            {connected ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
      </div>

      {/* Center: Mode + Time */}
      <div className="flex items-center gap-6">
        {/* Mode badge */}
        <span className={`
          text-[11px] font-bold px-3 py-1 rounded-full border uppercase tracking-wider
          ${isStartup
            ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
            : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
          }
        `}>
          {modeName}
        </span>

        {/* System time */}
        <div className="text-center">
          <p className="text-xs font-mono text-gray-400 tabular-nums">
            {time.toLocaleTimeString()}
          </p>
          <p className="text-[10px] text-gray-600 font-mono">
            {time.toLocaleDateString()}
          </p>
        </div>
      </div>

      {/* Right: Health score */}
      <div className="flex items-center gap-4">
        <div className="text-right">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">
            Plant Health
          </p>
          <p className={`text-xl font-extrabold tabular-nums ${healthColor}`}>
            {averageConfidence}%
          </p>
        </div>
      </div>
    </header>
  );
}

// ── Sensor Grid (Left Panel) ────────────────────────────────────────────────

function SensorGrid({ readings, confidence, selectedSensorId, onSelectSensor }) {
  // Map confidence by sensor_id for quick lookup
  const confMap = useMemo(() => {
    const map = {};
    for (const c of confidence) {
      map[c.sensor_id] = c;
    }
    return map;
  }, [confidence]);

  return (
    <div className="grid grid-cols-2 gap-3 auto-rows-min">
      {readings.map((r) => (
        <SensorCard
          key={r.sensor_id}
          reading={r}
          confidence={confMap[r.sensor_id]}
          isSelected={selectedSensorId === r.sensor_id}
          onSelect={onSelectSensor}
        />
      ))}
    </div>
  );
}

// ── Right Panel (Health + Handover) ─────────────────────────────────────────

function RightPanel({ selectedSensorId }) {
  return (
    <div className="flex flex-col gap-4 h-full overflow-y-auto scrollbar-thin pr-1">
      <HealthTimeline sensorId={selectedSensorId} />
      <HandoverBrief />
    </div>
  );
}

// ── Main App ────────────────────────────────────────────────────────────────

function App() {
  const {
    connect,
    connected,
    readings,
    confidence,
    massBalance,
    mode,
    staleFlags,
    averageConfidence,
    chartHistory,
    selectedSensorId,
    selectSensor,
    toggleStartupMode,
    acknowledgeStale,
  } = useStore();

  // Connect WebSocket on mount
  useEffect(() => {
    connect();
  }, [connect]);

  const isStartup = mode?.is_active ?? false;

  return (
    <div className="h-screen w-screen flex flex-col bg-gray-950 text-gray-100 bg-grid-pattern overflow-hidden">
      {/* Top Bar */}
      <TopBar
        mode={mode}
        averageConfidence={averageConfidence}
        connected={connected}
      />

      {/* Startup Banner (conditionally shown) */}
      <div className="no-print px-4 pt-3">
        <StartupBanner
          isActive={isStartup}
          onToggle={toggleStartupMode}
          staleFlags={staleFlags}
          onAcknowledge={acknowledgeStale}
        />
      </div>

      {/* Main 3-column layout */}
      <main className="flex-1 min-h-0 grid grid-cols-12 gap-4 px-4 py-3 overflow-hidden">
        {/* Left panel: Sensor Grid (40% ≈ 5 cols) */}
        <section className="col-span-5 overflow-y-auto scrollbar-thin pr-1">
          <SensorGrid
            readings={readings}
            confidence={confidence}
            selectedSensorId={selectedSensorId}
            onSelectSensor={selectSensor}
          />
        </section>

        {/* Center panel: Mass-Balance Chart (35% ≈ 4 cols) */}
        <section className="col-span-4 min-h-0">
          <MassBalanceChart
            chartHistory={chartHistory}
            massBalance={massBalance}
            flags={massBalance?.flags}
          />
        </section>

        {/* Right panel: Health Timeline + Handover (25% ≈ 3 cols) */}
        <section className="col-span-3 min-h-0 overflow-hidden">
          <RightPanel selectedSensorId={selectedSensorId} />
        </section>
      </main>

      {/* Bottom: Flag Bar */}
      <footer className="no-print px-4 pb-3">
        <FlagBar
          confidence={confidence}
          massBalance={massBalance}
          staleFlags={staleFlags}
        />
      </footer>
    </div>
  );
}

export default App;
