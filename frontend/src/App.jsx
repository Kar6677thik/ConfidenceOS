import { useEffect, useMemo, useState } from 'react';
import { Routes, Route, useNavigate } from 'react-router-dom';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import useStore from './store';
import SensorCard from './components/SensorCard';
import MassBalanceChart from './components/MassBalanceChart';
import HealthTimeline from './components/HealthTimeline';
import HandoverBrief from './components/HandoverBrief';
import StartupBanner from './components/StartupBanner';
import FlagBar from './components/FlagBar';
import QueryPanel from './components/QueryPanel';
import NavBar from './components/NavBar';

const SENSOR_IDS = ['LT-5100', 'FI-2010', 'FO-2020', 'PT-3100', 'TT-4100', 'ZT-6100'];
const PLANT_IDS = ['plant-a', 'plant-b', 'plant-c'];

function PageFrame({ children }) {
  return (
    <div className="min-h-0 flex-1 overflow-hidden bg-gray-950 text-gray-100 bg-grid-pattern">
      {children}
    </div>
  );
}

function Panel({ title, action, children, className = '' }) {
  return (
    <section className={`bg-gray-900/60 border border-gray-800/70 rounded-lg p-4 ${className}`}>
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="text-xs font-bold uppercase tracking-wider text-gray-300">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function statusStyle(status) {
  if (status === 'CRITICAL') return 'text-red-400 bg-red-500/10 border-red-500/30';
  if (status === 'WARNING' || status === 'STARTUP') return 'text-amber-400 bg-amber-500/10 border-amber-500/30';
  return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30';
}

function SensorGrid({ readings, confidence, selectedSensorId, onSelectSensor }) {
  const confMap = useMemo(() => {
    const map = {};
    for (const c of confidence) map[c.sensor_id] = c;
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

function PredictionCard({ prediction }) {
  if (!prediction) {
    return <p className="text-xs text-gray-500">Select a sensor to view forecast data.</p>;
  }
  return (
    <div className="space-y-2 text-xs text-gray-400">
      <div className="flex items-center justify-between">
        <span className="font-mono text-cyan-300">{prediction.sensor_id}</span>
        <span className="text-gray-500">{prediction.model_type || 'unknown'} / {prediction.model_fit || 'insufficient'}</span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded bg-gray-800/60 p-2">
          <p className="text-[10px] uppercase text-gray-500">LOW in</p>
          <p className="text-lg font-bold text-amber-300">{prediction.time_to_low_hours ?? 'N/A'}h</p>
        </div>
        <div className="rounded bg-gray-800/60 p-2">
          <p className="text-[10px] uppercase text-gray-500">CRITICAL in</p>
          <p className="text-lg font-bold text-red-300">{prediction.time_to_critical_hours ?? 'N/A'}h</p>
        </div>
      </div>
      <p>{prediction.recommended_action || prediction.action || 'No recommendation available.'}</p>
    </div>
  );
}

function EngineerDeepDive({ selectedSensorId, confidence }) {
  const { plantId } = useStore();
  const [adaptive, setAdaptive] = useState(null);
  const selected = confidence.find((c) => c.sensor_id === selectedSensorId);

  useEffect(() => {
    fetch(`/api/adaptive-thresholds/${plantId}`)
      .then((res) => res.json())
      .then(setAdaptive)
      .catch(() => setAdaptive(null));
  }, [plantId]);

  if (!selectedSensorId) {
    return <p className="text-xs text-gray-500">Select a sensor for engineering detail.</p>;
  }

  const envelope = adaptive?.envelopes?.[selectedSensorId];
  const subs = selected?.sub_scores || {};

  return (
    <div className="space-y-3 text-xs">
      <div className="grid grid-cols-4 gap-2">
        {Object.entries({
          CAL: subs.calibration,
          STB: subs.stability,
          XSN: subs.cross_sensor,
          PHY: subs.physical_plausibility,
        }).map(([label, value]) => (
          <div key={label} className="rounded bg-gray-800/60 p-2 text-center">
            <p className="text-[10px] text-gray-500">{label}</p>
            <p className="font-bold text-gray-200">{value != null ? `${Math.round(value * 100)}%` : 'N/A'}</p>
          </div>
        ))}
      </div>
      <div className="rounded bg-gray-800/50 p-3">
        <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">Adaptive Envelope</p>
        {envelope ? (
          <p className="text-gray-300">
            Mean {envelope.mean}, band {envelope.normal_min} to {envelope.normal_max} from {envelope.sample_count} samples.
          </p>
        ) : (
          <p className="text-gray-500">Insufficient clean history for learned envelope.</p>
        )}
      </div>
    </div>
  );
}

function OperatorDashboard() {
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
    predictions,
    fetchPredictions,
    plantId,
    role,
  } = useStore();

  useEffect(() => {
    connect();
  }, [connect]);

  useEffect(() => {
    fetchPredictions(plantId);
  }, [fetchPredictions, plantId]);

  const selectedPrediction = predictions?.[selectedSensorId];

  return (
    <PageFrame>
      <div className="h-full flex flex-col overflow-hidden">
        <div className="px-4 pt-3">
          <div className="flex items-center justify-between gap-4 bg-gray-900/50 border border-gray-800/60 rounded-lg px-4 py-3">
            <div>
              <p className="text-[10px] uppercase tracking-wider text-gray-500">Active Plant</p>
              <h1 className="text-lg font-bold text-gray-100">{plantId}</h1>
            </div>
            <div className="flex items-center gap-4">
              <span className={`text-[10px] font-bold px-2 py-1 rounded border ${connected ? 'text-emerald-400 border-emerald-500/30' : 'text-red-400 border-red-500/30'}`}>
                {connected ? 'LIVE' : 'OFFLINE'}
              </span>
              <div className="text-right">
                <p className="text-[10px] uppercase tracking-wider text-gray-500">Plant Health</p>
                <p className="text-2xl font-black text-cyan-300">{averageConfidence}%</p>
              </div>
            </div>
          </div>
        </div>

        <div className="px-4 pt-3">
          <StartupBanner
            isActive={mode?.is_active ?? false}
            onToggle={toggleStartupMode}
            staleFlags={staleFlags}
            onAcknowledge={acknowledgeStale}
          />
        </div>

        <main className="flex-1 min-h-0 grid grid-cols-12 gap-4 px-4 py-3 overflow-hidden">
          <section className="col-span-4 overflow-y-auto scrollbar-thin pr-1">
            <SensorGrid
              readings={readings}
              confidence={confidence}
              selectedSensorId={selectedSensorId}
              onSelectSensor={selectSensor}
            />
          </section>
          <section className="col-span-4 min-h-0">
            <MassBalanceChart chartHistory={chartHistory} massBalance={massBalance} flags={massBalance?.flags} />
          </section>
          <section className="col-span-4 min-h-0 overflow-y-auto scrollbar-thin pr-1 space-y-4">
            <Panel title="Predictive Forecast">
              <PredictionCard prediction={selectedPrediction} />
            </Panel>
            {role === 'Engineer' && (
              <Panel title="Engineer Deep-Dive">
                <EngineerDeepDive selectedSensorId={selectedSensorId} confidence={confidence} />
              </Panel>
            )}
            <HealthTimeline sensorId={selectedSensorId} />
            <QueryPanel />
            <HandoverBrief />
          </section>
        </main>

        <footer className="px-4 pb-3">
          <FlagBar confidence={confidence} massBalance={massBalance} staleFlags={staleFlags} />
        </footer>
      </div>
    </PageFrame>
  );
}

function FleetOverviewPage() {
  const { fleetData, fleetLoading, fetchFleet, setPlantId } = useStore();
  const [trend, setTrend] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    fetchFleet();
    fetch('/api/fleet/history?hours=24')
      .then((res) => res.json())
      .then((data) => setTrend(data.trend || []))
      .catch(() => setTrend([]));
    const timer = setInterval(fetchFleet, 5000);
    return () => clearInterval(timer);
  }, [fetchFleet]);

  const openPlant = (plantId) => {
    setPlantId(plantId);
    navigate('/operator');
  };

  return (
    <PageFrame>
      <div className="h-full overflow-y-auto p-5 space-y-5 scrollbar-thin">
        <div className="flex items-end justify-between">
          <div>
            <p className="text-xs text-cyan-400 font-semibold uppercase tracking-wider">Fleet Overview</p>
            <h1 className="text-2xl font-black text-gray-100">Enterprise risk ranking</h1>
          </div>
          <span className="text-xs text-gray-500">{fleetLoading ? 'Refreshing...' : `${fleetData.length} plants online`}</span>
        </div>

        <div className="grid grid-cols-3 gap-4">
          {fleetData.map((plant) => (
            <button
              key={plant.plant_id}
              onClick={() => openPlant(plant.plant_id)}
              className="text-left bg-gray-900/70 border border-gray-800 hover:border-cyan-500/40 rounded-lg p-4 transition-colors"
            >
              <div className="flex items-center justify-between mb-3">
                <span className={`text-[10px] font-bold px-2 py-1 rounded border ${statusStyle(plant.status)}`}>{plant.status}</span>
                <span className="text-xs text-gray-500">Rank #{plant.risk_rank}</span>
              </div>
              <h2 className="text-lg font-bold text-gray-100">{plant.name}</h2>
              <p className="text-xs text-gray-500 mb-4">{plant.location} / {plant.type}</p>
              <div className="grid grid-cols-3 gap-2 mb-4">
                <div><p className="text-[10px] text-gray-500">Health</p><p className="text-xl font-black text-emerald-300">{plant.health_pct}%</p></div>
                <div><p className="text-[10px] text-gray-500">Risk</p><p className="text-xl font-black text-amber-300">{plant.risk_score}</p></div>
                <div><p className="text-[10px] text-gray-500">Flags</p><p className="text-xl font-black text-red-300">{plant.active_flags}</p></div>
              </div>
              <ul className="space-y-1 min-h-12">
                {(plant.top_issues || []).slice(0, 3).map((issue, idx) => (
                  <li key={idx} className="text-xs text-gray-400 truncate">{issue}</li>
                ))}
                {(!plant.top_issues || plant.top_issues.length === 0) && <li className="text-xs text-gray-600">No active issues.</li>}
              </ul>
            </button>
          ))}
        </div>

        <Panel title="24h Fleet Health Trend">
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trend}>
                <XAxis dataKey="timestamp" tick={{ fontSize: 10, fill: '#6b7280' }} minTickGap={40} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#6b7280' }} />
                <Tooltip />
                {PLANT_IDS.map((pid, idx) => (
                  <Line key={pid} type="monotone" dataKey={pid} dot={false} stroke={['#22d3ee', '#34d399', '#f59e0b'][idx]} strokeWidth={2} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>
    </PageFrame>
  );
}

function PredictiveTimelinePage() {
  const { plantId, predictions, predictionsLoading, fetchPredictions } = useStore();

  useEffect(() => {
    fetchPredictions(plantId);
  }, [fetchPredictions, plantId]);

  const rows = Object.values(predictions || {});
  const actionQueue = rows
    .filter((p) => p.time_to_low_hours != null || p.time_to_critical_hours != null)
    .sort((a, b) => (a.time_to_critical_hours ?? a.time_to_low_hours ?? 99) - (b.time_to_critical_hours ?? b.time_to_low_hours ?? 99));

  return (
    <PageFrame>
      <div className="h-full overflow-y-auto p-5 space-y-5 scrollbar-thin">
        <div className="flex items-end justify-between">
          <div>
            <p className="text-xs text-cyan-400 font-semibold uppercase tracking-wider">Predictive Maintenance</p>
            <h1 className="text-2xl font-black text-gray-100">Next 12 hours for {plantId}</h1>
          </div>
          <button onClick={() => fetchPredictions(plantId)} className="px-3 py-2 rounded bg-cyan-500/15 text-cyan-300 text-xs font-semibold">
            {predictionsLoading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        <Panel title="Predictive Timeline">
          <div className="space-y-3">
            {rows.map((p) => {
              const low = Math.min(12, p.time_to_low_hours ?? 12);
              const crit = Math.min(12, p.time_to_critical_hours ?? 12);
              return (
                <div key={p.sensor_id} className="grid grid-cols-[90px_1fr_160px] items-center gap-3 text-xs">
                  <span className="font-mono text-gray-300">{p.sensor_id}</span>
                  <div className="h-6 rounded bg-gray-800 overflow-hidden flex">
                    <div className="bg-emerald-500/70" style={{ width: `${(low / 12) * 100}%` }} />
                    {p.time_to_low_hours != null && <div className="bg-amber-500/70" style={{ width: `${Math.max(0, (crit - low) / 12) * 100}%` }} />}
                    {p.time_to_critical_hours != null && <div className="bg-red-500/80 flex-1" />}
                  </div>
                  <span className="text-gray-500">{p.model_type} / {p.model_fit}</span>
                </div>
              );
            })}
            {rows.length === 0 && <p className="text-sm text-gray-500">Waiting for confidence history.</p>}
          </div>
        </Panel>

        <Panel title="Action Queue">
          <div className="space-y-2">
            {actionQueue.map((p) => (
              <div key={p.sensor_id} className="rounded bg-gray-800/50 p-3">
                <p className="text-sm font-bold text-gray-200">{p.sensor_id}</p>
                <p className="text-xs text-gray-400">{p.recommended_action || p.action}</p>
              </div>
            ))}
            {actionQueue.length === 0 && <p className="text-sm text-gray-500">No sensors currently forecast to cross a lower tier.</p>}
          </div>
        </Panel>
      </div>
    </PageFrame>
  );
}

function ForensicsPage() {
  const [presets, setPresets] = useState([]);
  const [data, setData] = useState(null);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [mode, setMode] = useState('confidenceos');

  useEffect(() => {
    fetch('/api/forensics/presets')
      .then((res) => res.json())
      .then((payload) => setPresets(payload.presets || []));
  }, []);

  useEffect(() => {
    fetch('/api/forensics/presets/texas-city')
      .then((res) => res.json())
      .then((payload) => {
        setData(payload);
        setIndex(0);
      });
  }, []);

  useEffect(() => {
    if (!playing || !data?.timeline?.length) return undefined;
    const timer = setInterval(() => {
      setIndex((prev) => (prev + 1 >= data.timeline.length ? 0 : prev + 1));
    }, 650);
    return () => clearInterval(timer);
  }, [playing, data]);

  const frame = data?.timeline?.[index];
  const readings = frame
    ? Object.entries(frame.readings).map(([sensor_id, value]) => ({ sensor_id, ...value }))
    : [];
  const confidence = frame
    ? Object.entries(frame.confidence).map(([sensor_id, value]) => ({ sensor_id, reasons: [], sub_scores: {}, ...value }))
    : [];
  const chartHistory = (data?.timeline || []).slice(0, index + 1).map((point) => ({
    time: `${point.minute}m`,
    implied: point.mass_balance.implied_level,
    measured: point.mass_balance.measured_level,
    discrepancy: point.mass_balance.discrepancy,
  }));

  return (
    <PageFrame>
      <div className="h-full grid grid-cols-[280px_1fr_320px] gap-4 p-5 overflow-hidden">
        <Panel title="Replay Controls" className="overflow-y-auto scrollbar-thin">
          <div className="space-y-3">
            {presets.map((preset) => (
              <button key={preset.id} className="w-full text-left rounded bg-gray-800/50 p-3 text-xs text-gray-300">
                <span className="block font-bold text-gray-100">{preset.name}</span>
                {preset.description}
              </button>
            ))}
            <button onClick={() => setPlaying((v) => !v)} className="w-full rounded bg-cyan-500/20 text-cyan-300 py-2 text-sm font-bold">
              {playing ? 'Pause' : 'Play'} at 30x
            </button>
            <label className="block text-xs text-gray-500">
              Timeline
              <input
                type="range"
                min="0"
                max={Math.max(0, (data?.timeline?.length || 1) - 1)}
                value={index}
                onChange={(e) => setIndex(Number(e.target.value))}
                className="w-full"
              />
            </label>
            <div className="flex gap-2">
              <button onClick={() => setMode('confidenceos')} className={`flex-1 rounded py-2 text-xs ${mode === 'confidenceos' ? 'bg-cyan-500/20 text-cyan-300' : 'bg-gray-800 text-gray-500'}`}>ConfidenceOS</button>
              <button onClick={() => setMode('traditional')} className={`flex-1 rounded py-2 text-xs ${mode === 'traditional' ? 'bg-cyan-500/20 text-cyan-300' : 'bg-gray-800 text-gray-500'}`}>Traditional</button>
            </div>
          </div>
        </Panel>

        <div className="min-h-0 space-y-4 overflow-y-auto scrollbar-thin">
          <Panel title={`Replay Dashboard ${frame ? `T+${frame.minute}m` : ''}`}>
            <div className="grid grid-cols-3 gap-3">
              {readings.map((reading) => {
                const conf = confidence.find((c) => c.sensor_id === reading.sensor_id);
                return mode === 'traditional' ? (
                  <div key={reading.sensor_id} className="rounded bg-gray-800/60 p-3">
                    <p className="font-mono text-xs text-gray-400">{reading.sensor_id}</p>
                    <p className="text-2xl font-black text-gray-100">{reading.value} <span className="text-xs">{reading.unit}</span></p>
                  </div>
                ) : (
                  <SensorCard key={reading.sensor_id} reading={reading} confidence={conf} />
                );
              })}
            </div>
          </Panel>
          <div className="h-96">
            <MassBalanceChart chartHistory={chartHistory} massBalance={frame?.mass_balance} flags={frame?.mass_balance?.flags} />
          </div>
        </div>

        <Panel title="Incident Annotations" className="overflow-y-auto scrollbar-thin">
          <div className="space-y-3">
            {(data?.annotations || []).map((note) => (
              <div key={note.minute} className={`rounded border p-3 ${frame && note.minute <= frame.minute ? 'border-cyan-500/40 bg-cyan-500/10' : 'border-gray-800 bg-gray-800/30'}`}>
                <p className="text-xs font-bold text-gray-200">T+{note.minute}m {note.title}</p>
                <p className="text-xs text-gray-500">{note.body}</p>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </PageFrame>
  );
}

function CompliancePage() {
  const { plantId } = useStore();
  const [hours, setHours] = useState(24);
  const [reportType, setReportType] = useState('full');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/compliance/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plant_id: plantId, hours: Number(hours), report_type: reportType }),
      });
      setReport(await res.json());
    } finally {
      setLoading(false);
    }
  };

  const download = () => {
    if (!report?.pdf_base64) return;
    const bytes = Uint8Array.from(atob(report.pdf_base64), (c) => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = report.pdf_filename || 'confidenceos_report.pdf';
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <PageFrame>
      <div className="h-full grid grid-cols-[320px_1fr] gap-4 p-5 overflow-hidden">
        <Panel title="Report Configuration">
          <div className="space-y-3">
            <label className="block text-xs text-gray-400">Period hours
              <input value={hours} onChange={(e) => setHours(e.target.value)} type="number" className="mt-1 w-full rounded bg-gray-800 border border-gray-700 px-3 py-2" />
            </label>
            <label className="block text-xs text-gray-400">Report type
              <select value={reportType} onChange={(e) => setReportType(e.target.value)} className="mt-1 w-full rounded bg-gray-800 border border-gray-700 px-3 py-2">
                <option value="full">Full Audit</option>
                <option value="alarm">Alarm Management Only</option>
                <option value="sensor">Sensor Reliability Only</option>
                <option value="handover">Shift Handover Log Only</option>
              </select>
            </label>
            <button onClick={generate} className="w-full rounded bg-cyan-500/20 py-2 text-sm font-bold text-cyan-300">{loading ? 'Generating...' : 'Generate Report'}</button>
            <button onClick={download} disabled={!report?.pdf_base64} className="w-full rounded bg-gray-800 py-2 text-sm font-bold text-gray-300 disabled:opacity-40">Download PDF</button>
          </div>
        </Panel>
        <Panel title="Report Preview" className="overflow-y-auto scrollbar-thin">
          {report ? (
            <div className="space-y-4 text-sm text-gray-300">
              <div>
                <h1 className="text-2xl font-black text-gray-100">Compliance Report</h1>
                <p className="text-gray-500">{report.plant_name} / {report.period_hours} hours / signed demo artifact</p>
              </div>
              <pre className="whitespace-pre-wrap rounded bg-gray-800/50 p-4 text-xs">
{JSON.stringify(report.sections, null, 2)}
              </pre>
            </div>
          ) : (
            <p className="text-sm text-gray-500">Generate a report to preview audit sections and download the PDF artifact.</p>
          )}
        </Panel>
      </div>
    </PageFrame>
  );
}

function CausalGraphPage() {
  const { plantId } = useStore();
  const [graph, setGraph] = useState(null);

  useEffect(() => {
    fetch(`/api/graph/${plantId}`)
      .then((res) => res.json())
      .then(setGraph)
      .catch(() => setGraph(null));
  }, [plantId]);

  const nodes = graph?.nodes || [];
  const positions = {};
  nodes.forEach((node, idx) => {
    positions[node.id] = { x: 120 + (idx % 3) * 230, y: 90 + Math.floor(idx / 3) * 180 };
  });

  return (
    <PageFrame>
      <div className="h-full grid grid-cols-[1fr_360px] gap-4 p-5 overflow-hidden">
        <Panel title="Causal Graph">
          <svg viewBox="0 0 760 460" className="w-full h-[520px] bg-gray-950 rounded border border-gray-800">
            {(graph?.edges || []).map((edge) => {
              const a = positions[edge.source];
              const b = positions[edge.target];
              if (!a || !b) return null;
              return <line key={`${edge.source}-${edge.target}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={edge.is_propagating ? '#f97316' : '#374151'} strokeWidth={edge.is_active ? 4 : 2} />;
            })}
            {nodes.map((node) => {
              const p = positions[node.id];
              const fill = node.tier === 'CRITICAL' ? '#ef4444' : node.tier === 'LOW' ? '#f97316' : node.tier === 'MEDIUM' ? '#f59e0b' : '#10b981';
              return (
                <g key={node.id}>
                  <circle cx={p.x} cy={p.y} r="42" fill={fill} opacity="0.2" stroke={fill} strokeWidth="2" />
                  <text x={p.x} y={p.y - 4} textAnchor="middle" fill="#e5e7eb" fontSize="14" fontWeight="700">{node.id}</text>
                  <text x={p.x} y={p.y + 16} textAnchor="middle" fill="#9ca3af" fontSize="11">{node.confidence_pct}%</text>
                </g>
              );
            })}
          </svg>
        </Panel>
        <Panel title="Root Cause Narrative" className="overflow-y-auto scrollbar-thin">
          <p className="text-sm text-gray-300 leading-relaxed">{graph?.narrative || 'No graph data yet.'}</p>
          <div className="mt-4 space-y-2">
            {(graph?.causal_chains || []).map((chain, idx) => (
              <div key={idx} className="rounded bg-gray-800/50 p-3 text-xs text-gray-400">{chain.join(' -> ')}</div>
            ))}
          </div>
        </Panel>
      </div>
    </PageFrame>
  );
}

function SandboxPage() {
  const { plantId } = useStore();
  const [form, setForm] = useState({ sensor_id: 'LT-5100', failure_mode: 'calibration_drift', severity: 'moderate', duration_hours: 6 });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/sandbox/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plant_id: plantId, ...form, duration_hours: Number(form.duration_hours) }),
      });
      setResult(await res.json());
    } finally {
      setLoading(false);
    }
  };

  const chartData = result?.results?.map((r) => ({ time: r.time_hours, confidence: r.confidence_pct, discrepancy: r.mass_balance?.discrepancy })) || [];

  return (
    <PageFrame>
      <div className="h-full grid grid-cols-[320px_1fr] gap-4 p-5 overflow-hidden">
        <Panel title="Sandbox Controls">
          <div className="space-y-3">
            <select value={form.sensor_id} onChange={(e) => setForm({ ...form, sensor_id: e.target.value })} className="w-full rounded bg-gray-800 border border-gray-700 px-3 py-2 text-sm">
              {SENSOR_IDS.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
            <select value={form.failure_mode} onChange={(e) => setForm({ ...form, failure_mode: e.target.value })} className="w-full rounded bg-gray-800 border border-gray-700 px-3 py-2 text-sm">
              <option value="calibration_drift">Calibration drift</option>
              <option value="stuck_reading">Stuck reading</option>
              <option value="sg_mismatch">Specific gravity mismatch</option>
              <option value="command_state_decoupling">Command-state decoupling</option>
            </select>
            <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })} className="w-full rounded bg-gray-800 border border-gray-700 px-3 py-2 text-sm">
              <option value="mild">Mild</option>
              <option value="moderate">Moderate</option>
              <option value="severe">Severe</option>
            </select>
            <input value={form.duration_hours} onChange={(e) => setForm({ ...form, duration_hours: e.target.value })} type="number" className="w-full rounded bg-gray-800 border border-gray-700 px-3 py-2 text-sm" />
            <button onClick={run} className="w-full rounded bg-amber-500/20 py-2 text-sm font-bold text-amber-300">{loading ? 'Running...' : 'Run Sandbox'}</button>
          </div>
        </Panel>
        <Panel title="Sandbox Results">
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#6b7280' }} />
                <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
                <Tooltip />
                <Line dataKey="confidence" stroke="#22d3ee" dot={false} />
                <Line dataKey="discrepancy" stroke="#f97316" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          {result && <p className="mt-3 text-xs text-gray-500">{result.sample_count} samples generated without touching live plant data.</p>}
        </Panel>
      </div>
    </PageFrame>
  );
}

function App() {
  return (
    <div className="h-screen w-screen flex flex-col bg-gray-950 text-gray-100 overflow-hidden">
      <NavBar />
      <Routes>
        <Route path="/" element={<FleetOverviewPage />} />
        <Route path="/operator" element={<OperatorDashboard />} />
        <Route path="/predictions" element={<PredictiveTimelinePage />} />
        <Route path="/forensics" element={<ForensicsPage />} />
        <Route path="/graph" element={<CausalGraphPage />} />
        <Route path="/compliance" element={<CompliancePage />} />
        <Route path="/sandbox" element={<SandboxPage />} />
      </Routes>
    </div>
  );
}

export default App;
