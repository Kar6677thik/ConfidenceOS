import { useEffect, useMemo, useState } from 'react';
import { Routes, Route, useNavigate } from 'react-router-dom';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
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
import IncidentQueue from './components/IncidentQueue';
import EvidenceStack from './components/EvidenceStack';
import IncidentTimeline from './components/IncidentTimeline';
import ScoreSensitivityPanel from './components/ScoreSensitivityPanel';
import VerificationTokens from './components/VerificationTokens';
import HandoverDebtLedger from './components/HandoverDebtLedger';
import ConfidenceDebtPanel from './components/ConfidenceDebtPanel';
import TrustDependencyGraph from './components/TrustDependencyGraph';
import RuntimePlatform from './components/RuntimePlatform';
import StudioWorkspace from './components/StudioWorkspace';
import ShiftChannel from './components/ShiftChannel';

const SENSOR_IDS = ['LT-5100', 'FI-2010', 'FO-2020', 'PT-3100', 'TT-4100', 'ZT-6100'];
const PLANT_IDS = ['plant-a', 'plant-b', 'plant-c'];

function PageFrame({ children }) {
  return <div className="industrial-page">{children}</div>;
}

function Panel({ title, action, children, className = '', bodyClassName = 'industrial-body' }) {
  return (
    <section className={`industrial-panel ${className}`}>
      <div className="industrial-panel-header">
        <h2 className="industrial-panel-title">{title}</h2>
        {action}
      </div>
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

function statusClass(status) {
  const normalized = String(status || '').toUpperCase();
  if (normalized === 'CRITICAL') return 'status-critical';
  if (normalized === 'WARNING' || normalized === 'STARTUP' || normalized === 'MEDIUM') return 'status-warning';
  if (normalized === 'LOW' || normalized === 'LOW RISK' || normalized === 'OK' || normalized === 'NOMINAL') return 'status-safe';
  return 'text-[var(--data-mono)]';
}

function healthClass(value) {
  if (value >= 80) return 'status-safe';
  if (value >= 50) return 'status-caution';
  if (value >= 20) return 'status-warning';
  return 'status-critical';
}

function IndustrialTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <p className="mb-2">{label}</p>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="flex items-center gap-2">
          <span className="led-square" style={{ color: entry.color }} />
          <span>{entry.name || entry.dataKey}</span>
          <span className="ml-auto">{typeof entry.value === 'number' ? entry.value.toFixed(1) : entry.value}</span>
        </div>
      ))}
    </div>
  );
}

function SensorGrid({ readings, confidence, selectedSensorId, onSelectSensor, columns = 'grid-cols-3' }) {
  const confMap = useMemo(() => {
    const map = {};
    for (const item of confidence) map[item.sensor_id] = item;
    return map;
  }, [confidence]);

  return (
    <div className={`industrial-grid-shell ${columns}`}>
      {readings.map((reading) => (
        <SensorCard
          key={reading.sensor_id}
          reading={reading}
          confidence={confMap[reading.sensor_id]}
          isSelected={selectedSensorId === reading.sensor_id}
          onSelect={onSelectSensor}
        />
      ))}
    </div>
  );
}

function PredictionCard({ prediction }) {
  if (!prediction) {
    return <p className="caption-mono text-[var(--data-mono)]">Select a sensor to view confidence degradation forecast data.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="font-data status-safe">{prediction.sensor_id}</span>
        <span className="caption-mono text-[var(--data-mono)]">{prediction.model_type || 'unknown'} / {prediction.model_fit || 'insufficient'}</span>
      </div>
      <div className="industrial-grid-shell grid-cols-2">
        <div className="industrial-panel-subtle p-3">
          <p className="label-caps text-[var(--text-muted)]">LOW confidence in</p>
          <p className="font-data text-3xl status-warning">{prediction.time_to_low_hours ?? 'N/A'}h</p>
        </div>
        <div className="industrial-panel-subtle p-3">
          <p className="label-caps text-[var(--text-muted)]">Verification required in</p>
          <p className="font-data text-3xl status-critical">{prediction.time_to_critical_hours ?? 'N/A'}h</p>
        </div>
      </div>
      <p className="caption-mono text-[var(--data-mono)]">{prediction.recommended_action || prediction.action || 'No recommendation available.'}</p>
    </div>
  );
}

function EngineerDeepDive({ selectedSensorId, confidence }) {
  const { plantId } = useStore();
  const [adaptive, setAdaptive] = useState(null);
  const selected = confidence.find((item) => item.sensor_id === selectedSensorId);

  useEffect(() => {
    fetch(`/api/adaptive-thresholds/${plantId}`)
      .then((res) => res.json())
      .then(setAdaptive)
      .catch(() => setAdaptive(null));
  }, [plantId]);

  if (!selectedSensorId) {
    return <p className="caption-mono text-[var(--data-mono)]">Select a sensor for engineering detail.</p>;
  }

  const envelope = adaptive?.envelopes?.[selectedSensorId];
  const subs = selected?.sub_scores || {};

  return (
    <div className="space-y-4">
      <div className="industrial-grid-shell grid-cols-4">
        {Object.entries({
          CAL: subs.calibration,
          STB: subs.stability,
          XSN: subs.cross_sensor,
          PHY: subs.physical_plausibility,
        }).map(([label, value]) => (
          <div key={label} className="industrial-panel-subtle p-3 text-center">
            <p className="label-caps text-[var(--text-muted)]">{label}</p>
            <p className={`font-data text-xl ${value >= 0.8 ? 'status-safe' : value >= 0.5 ? 'status-warning' : 'status-critical'}`}>
              {value != null ? `${Math.round(value * 100)}%` : 'N/A'}
            </p>
          </div>
        ))}
      </div>
      <div className="industrial-panel-subtle p-3">
        <p className="label-caps text-[var(--text-muted)] mb-2">Adaptive Envelope</p>
        {envelope ? (
          <p className="caption-mono text-[var(--data-mono)]">
            Mean {envelope.mean}, band {envelope.normal_min} to {envelope.normal_max}, {envelope.sample_count} samples.
          </p>
        ) : (
          <p className="caption-mono text-[var(--data-mono)]">Insufficient clean history for learned envelope.</p>
        )}
      </div>
    </div>
  );
}

function LeftRail() {
  return (
    <aside className="left-rail">
      <div className="py-4">
        {['TL', 'GR', 'SB', 'SG'].map((item, index) => (
          <div key={item} className={`rail-button caption-mono ${index === 0 ? 'active' : ''}`}>{item}</div>
        ))}
      </div>
      <div className="py-4">
        <div className="rail-button caption-mono">SET</div>
        <div className="rail-button caption-mono">?</div>
      </div>
    </aside>
  );
}

function ContextStrip({ context, incidents = [], incidentTimeline = [] }) {
  if (!context) return null;
  const cls = statusClass(context.severity);
  const inference = context.inferred_mode || context.mode_inference;
  const leadIncident = incidents?.[0];
  const collapse = leadIncident?.alarm_collapse;
  const collapsedCount = collapse?.raw_signal_count ?? leadIncident?.source_flags?.length;
  return (
    <div className="industrial-panel mb-[1px]">
      <div className="industrial-panel-header py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-3 mb-2">
            <span className={`industrial-badge ${cls}`}>{context.state || 'STEADY_STATE'}</span>
            <span className="caption-mono text-[var(--data-mono)]">{context.layout_hint || 'standard_monitoring'}</span>
            {inference?.rule_id && <span className="caption-mono text-[var(--data-mono)]">{inference.rule_id}</span>}
          </div>
          <p className="caption-mono text-[var(--text)] truncate">{context.operator_focus || 'No active operator focus.'}</p>
          {leadIncident && (
            <div className="mt-2 flex flex-wrap items-center gap-2 caption-mono">
              <span className="status-warning">{leadIncident.title}</span>
              {collapsedCount != null && <span className="text-[var(--data-mono)]">collapsed from {collapsedCount} signals</span>}
              {!!incidentTimeline.length && <span className="text-[var(--data-mono)]">{incidentTimeline.length} timeline events</span>}
            </div>
          )}
        </div>
        {!!context.priority_sensors?.length && (
          <div className="flex flex-wrap justify-end gap-2 max-w-[320px]">
            {context.priority_sensors.map((sensorId) => (
              <span key={sensorId} className="industrial-badge text-[var(--data-mono)]">{sensorId}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function AssetIntegrationStrip({ plantId }) {
  const [metadata, setMetadata] = useState(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetch('/api/asset-model').then((res) => (res.ok ? res.json() : null)),
      fetch('/api/integration/read-only-layer').then((res) => (res.ok ? res.json() : null)),
    ])
      .then(([assetPayload, integrationPayload]) => {
        if (active) setMetadata({ asset: assetPayload?.asset_model, integration: integrationPayload });
      })
      .catch(() => {
        if (active) setMetadata(null);
      });
    return () => {
      active = false;
    };
  }, []);

  if (!metadata?.asset && !metadata?.integration) return null;

  const equipment = metadata.asset?.equipment || {};
  const relationship = (equipment.relationships || []).find((item) => item.type === 'mass_balance_validation') || {};
  const provider = metadata.integration?.active_providers?.[plantId] || {};
  const sensorCount = equipment.sensor_tags?.length || 0;
  const validationText = relationship.source_tags?.length
    ? `${relationship.source_tags.join(' + ')} validates ${relationship.validated_tag}`
    : 'metadata relationship unavailable';

  return (
    <div className="industrial-panel mb-[1px]">
      <div className="industrial-body grid grid-cols-1 md:grid-cols-3 gap-[1px] bg-[var(--border-strong)]">
        <div className="bg-[var(--surface-panel)] p-3">
          <p className="label-caps text-[var(--text-muted)]">Asset Metadata</p>
          <p className="caption-mono text-[var(--text)] mt-1">{equipment.equipment_id || 'V-5100'} / {sensorCount} tags</p>
        </div>
        <div className="bg-[var(--surface-panel)] p-3">
          <p className="label-caps text-[var(--text-muted)]">Self-Configured Check</p>
          <p className="caption-mono text-[var(--text)] mt-1">{validationText}</p>
        </div>
        <div className="bg-[var(--surface-panel)] p-3">
          <p className="label-caps status-safe">Shadow Mode</p>
          <p className="caption-mono text-[var(--text)] mt-1">
            {provider.display_name || 'TagProvider'} / {provider.control_writes_enabled === false ? 'no control writes' : 'read-only'}
          </p>
        </div>
      </div>
    </div>
  );
}

function asList(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  if (value == null || value === '') return [];
  return [value];
}

function formatStressValue(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function StressValueList({ values, empty = 'Not available' }) {
  const rows = asList(values);
  if (rows.length === 0) {
    return <p className="caption-mono text-[var(--data-mono)]">{empty}</p>;
  }
  return (
    <div className="space-y-2">
      {rows.slice(0, 6).map((value) => (
        <p key={value} className="caption-mono text-[var(--text)]">{formatStressValue(value)}</p>
      ))}
    </div>
  );
}

function StressRow({ label, tone = 'text-[var(--text-muted)]', children }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-[220px_1fr] gap-[1px] bg-[var(--border-strong)]">
      <div className="bg-[var(--surface-lowest)] p-4">
        <p className={`label-caps ${tone}`}>{label}</p>
      </div>
      <div className="bg-[var(--surface-panel)] p-4 min-w-0">
        {children}
      </div>
    </div>
  );
}

function StressModeLayout({
  connected,
  plantId,
  context,
  incidents,
  confidence,
  massBalance,
  incidentTimeline,
}) {
  const leadIncident = incidents?.[0];
  const contract = leadIncident?.action_contract || {};
  const collapse = leadIncident?.alarm_collapse;
  const collapsedCount = collapse?.raw_signal_count ?? leadIncident?.source_flags?.length;
  const doNotTrust = asList(contract.do_not_use).length
    ? contract.do_not_use
    : leadIncident?.affected_sensors || context?.priority_sensors || [];
  const firstSafeAction = contract.first_safe_action || leadIncident?.first_action || context?.operator_focus;
  const evidenceRefs = leadIncident?.evidence_refs || [];
  const degradedEvidence = (confidence || [])
    .filter((item) => item.tier && item.tier !== 'HIGH')
    .map((item) => `${item.sensor_id}: ${item.confidence_pct}% confidence (${item.tier})`);
  const massBalanceEvidence = (massBalance?.flags || [])
    .map((flag) => flag.message || `Mass-balance discrepancy ${flag.discrepancy}`);
  const evidenceRows = [
    ...evidenceRefs.map((item) => `${item.sensor_id}: ${item.message || item.category}`),
    ...massBalanceEvidence,
    ...degradedEvidence,
  ];

  return (
    <main className="min-w-0 overflow-y-auto scrollbar-thin bg-[var(--surface-base)] p-[1px]">
      <section className="industrial-panel min-h-full">
        <div className="industrial-panel-header">
          <div className="min-w-0">
            <p className="label-caps text-[var(--text-muted)]">Stress Mode / {plantId}</p>
            <h1 className="industrial-panel-title truncate">{leadIncident?.title || context?.state || 'Abnormal Situation'}</h1>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <span className={`industrial-badge ${connected ? 'status-safe' : 'status-critical'}`}>{connected ? 'LIVE' : 'OFFLINE'}</span>
            <span className={`industrial-badge ${statusClass(context?.severity)}`}>{context?.severity || 'WARNING'}</span>
          </div>
        </div>

        <div className="industrial-body">
          <div className="space-y-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
            <StressRow label="Abnormal Situation" tone="status-warning">
              <p className="caption-mono text-[var(--text)]">{leadIncident?.summary || context?.operator_focus || 'Abnormal plant context active.'}</p>
              {collapsedCount != null && (
                <p className="caption-mono text-[var(--data-mono)] mt-2">Collapsed from {collapsedCount} signals</p>
              )}
              {!!leadIncident?.root_trigger && (
                <p className="caption-mono text-[var(--data-mono)] mt-2">Hypothesis: {formatStressValue(leadIncident.root_trigger)}</p>
              )}
            </StressRow>

            <StressRow label="Do Not Trust" tone="status-critical">
              <StressValueList values={doNotTrust} empty="No blocked instrument trust restriction reported." />
            </StressRow>

            <StressRow label="Use Instead" tone="status-safe">
              <StressValueList values={contract.trusted_substitutes} empty="Use manual field verification or adjacent validated references." />
            </StressRow>

            <StressRow label="First Safe Action" tone="status-safe">
              <StressValueList values={firstSafeAction} empty="Verify evidence before taking the next operating action." />
            </StressRow>

            <StressRow label="Exit Condition">
              <StressValueList values={contract.exit_conditions} empty="No exit condition reported yet." />
            </StressRow>

            <StressRow label="Evidence" tone="status-warning">
              <StressValueList values={evidenceRows} empty="No structured evidence reported yet." />
              <div className="mt-4">
                <IncidentTimeline events={incidentTimeline} compact />
              </div>
            </StressRow>
          </div>
        </div>
      </section>
    </main>
  );
}

function OperatorSupportView() {
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
    plantContext,
    incidents,
    incidentTimeline,
  } = useStore();

  useEffect(() => {
    connect();
  }, [connect]);

  useEffect(() => {
    fetchPredictions(plantId);
  }, [fetchPredictions, plantId]);

  const selectedPrediction = predictions?.[selectedSensorId];
  const isStressMode = ['WARNING', 'CRITICAL'].includes(String(plantContext?.severity || '').toUpperCase());

  return (
    <PageFrame>
      <div className="h-full flex overflow-hidden">
        <LeftRail />
        {isStressMode ? (
          <div className="flex-1 min-w-0 bg-[var(--border-strong)] overflow-hidden">
            <StressModeLayout
              connected={connected}
              plantId={plantId}
              context={plantContext}
              incidents={incidents}
              confidence={confidence}
              massBalance={massBalance}
              incidentTimeline={incidentTimeline}
            />
          </div>
        ) : (
          <div className="flex-1 min-w-0 grid grid-cols-[1fr_360px] bg-[var(--border-strong)] gap-[1px] overflow-hidden">
          <main className="min-w-0 overflow-y-auto scrollbar-thin bg-[var(--surface-base)] p-[1px]">
            <div className="industrial-panel mb-[1px]">
              <div className="industrial-panel-header">
                <div>
                  <p className="label-caps text-[var(--text-muted)]">Active Plant</p>
                  <h1 className="industrial-panel-title">{plantId}</h1>
                </div>
                <div className="flex items-center gap-5">
                  <span className={`industrial-badge ${connected ? 'status-safe' : 'status-critical'}`}>{connected ? 'LIVE' : 'OFFLINE'}</span>
                  <span className={`font-data text-4xl font-bold ${healthClass(averageConfidence)}`}>{averageConfidence}%</span>
                </div>
              </div>
            </div>

            <ContextStrip context={plantContext} incidents={incidents} incidentTimeline={incidentTimeline} />

            <AssetIntegrationStrip plantId={plantId} />

            <div className="mb-[1px]">
              <StartupBanner
                isActive={mode?.is_active ?? false}
                onToggle={toggleStartupMode}
                staleFlags={staleFlags}
                onAcknowledge={acknowledgeStale}
              />
            </div>

            <SensorGrid
              readings={readings}
              confidence={confidence}
              selectedSensorId={selectedSensorId}
              onSelectSensor={selectSensor}
            />

            <div className="h-[430px] mt-[1px]">
              <MassBalanceChart chartHistory={chartHistory} massBalance={massBalance} flags={massBalance?.flags} />
            </div>

            <div className="mt-[1px]">
              {Array.isArray(incidents) ? (
                <IncidentQueue incidents={incidents} confidence={confidence} massBalance={massBalance} staleFlags={staleFlags} />
              ) : (
                <FlagBar confidence={confidence} massBalance={massBalance} staleFlags={staleFlags} />
              )}
            </div>
          </main>

          <aside className="min-w-0 bg-[var(--surface-panel)] overflow-y-auto scrollbar-thin">
            <div className="h-[520px]">
              <QueryPanel />
            </div>
            <Panel title="Confidence Degradation Forecast" className="border-t-0">
              <PredictionCard prediction={selectedPrediction} />
            </Panel>
            {role === 'Engineer' && (
              <Panel title="Engineer Deep-Dive" className="border-t-0">
                <EngineerDeepDive selectedSensorId={selectedSensorId} confidence={confidence} />
              </Panel>
            )}
            {role === 'Engineer' && <ScoreSensitivityPanel selectedSensorId={selectedSensorId} />}
            <EvidenceStack selectedSensorId={selectedSensorId} confidence={confidence} incidents={incidents} />
            <VerificationTokens selectedSensorId={selectedSensorId} confidence={confidence} />
            <IncidentTimeline events={incidentTimeline} />
            <HandoverDebtLedger />
            <HealthTimeline sensorId={selectedSensorId} />
            <HandoverBrief />
          </aside>
          </div>
        )}
      </div>
    </PageFrame>
  );
}

function InstrumentIntegrityOverviewPage() {
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

  const openPlant = (id) => {
    setPlantId(id);
    navigate('/operator');
  };

  return (
    <PageFrame>
      <div className="page-scroll p-8">
        <header className="mb-10">
          <h1 className="text-[56px] leading-none font-extrabold text-[var(--text)]">Instrument Integrity Overview</h1>
          <p className="mt-4 text-xl text-[var(--text-muted)]">Read-only trust layer beside existing HMI/DCS for {fleetData.length || 3} active plants</p>
        </header>

        <div className="industrial-grid-shell grid-cols-1 md:grid-cols-3 mb-12">
          {fleetData.map((plant) => {
            const cls = statusClass(plant.status);
            return (
              <button
                key={plant.plant_id}
                onClick={() => openPlant(plant.plant_id)}
                className={`text-left bg-[var(--surface-panel)] p-8 min-h-[360px] border-t-2 hover:bg-[var(--surface-elevated)] ${cls}`}
                style={{ borderTopColor: 'currentColor' }}
              >
                <div className="flex items-start justify-between gap-4 mb-8">
                  <div>
                    <h2 className="text-2xl font-bold text-[var(--text)] mb-3">{plant.name}</h2>
                    <span className={`industrial-badge ${cls}`}>{plant.status}</span>
                  </div>
                  <span className={`font-data text-6xl font-bold ${healthClass(plant.health_pct)}`}>{plant.health_pct}%</span>
                </div>

                <div className="mb-8">
                  <h3 className="label-caps text-[var(--text-muted)] mb-3">Operating Basis Issues</h3>
                  <ul className="space-y-3">
                    {(plant.top_issues || []).slice(0, 3).map((issue) => (
                      <li key={issue} className="caption-mono text-[var(--text)] flex items-center gap-3">
                        <span className={`led-square ${cls}`} />
                        {issue}
                      </li>
                    ))}
                    {(!plant.top_issues || plant.top_issues.length === 0) && (
                      <li className="caption-mono text-[var(--text-muted)] flex items-center gap-3">
                        <span className="led-square text-[var(--disabled)]" />
                        Normal operation
                      </li>
                    )}
                  </ul>
                </div>

                <div className="mt-auto">
                  <h3 className="label-caps text-[var(--text-muted)] mb-3">4H Integrity Sparkline</h3>
                  <svg className="w-full h-16" preserveAspectRatio="none" viewBox="0 0 200 40" aria-hidden="true">
                    <polyline
                      fill="none"
                      points={plant.health_pct < 50 ? '0,15 30,22 60,30 90,36 120,28 150,34 200,26' : plant.health_pct < 80 ? '0,18 30,14 60,22 90,18 120,26 150,20 200,24' : '0,8 30,12 60,8 90,14 120,10 150,8 200,10'}
                      stroke={plant.health_pct < 50 ? '#FF0000' : plant.health_pct < 80 ? '#FFA500' : '#00FF41'}
                      strokeWidth="3"
                    />
                  </svg>
                </div>
              </button>
            );
          })}
        </div>

        <Panel title="Instrument Integrity Trend (24h)">
          <div className="h-80 border border-[var(--border-strong)] bg-[#090b0c]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trend} margin={{ top: 24, right: 24, left: 0, bottom: 14 }}>
                <CartesianGrid stroke="#2D3139" strokeDasharray="4 4" vertical={false} />
                <XAxis dataKey="timestamp" tick={{ fontSize: 12, fill: '#A0AEC0', fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: '#414752' }} tickLine={false} minTickGap={40} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: '#A0AEC0', fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: '#414752' }} tickLine={false} />
                <Tooltip content={<IndustrialTooltip />} />
                {PLANT_IDS.map((pid, index) => (
                  <Line key={pid} type="monotone" dataKey={pid} name={pid} dot={false} stroke={['#FF0000', '#FFA500', '#00FF41'][index]} strokeWidth={3} isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          {fleetLoading && <p className="caption-mono text-[var(--data-mono)] mt-3">Refreshing fleet data...</p>}
        </Panel>
      </div>
    </PageFrame>
  );
}

function ConfidenceDebtPage() {
  const { plantId, predictions, predictionsLoading, fetchPredictions } = useStore();

  useEffect(() => {
    fetchPredictions(plantId);
  }, [fetchPredictions, plantId]);

  const rows = Object.values(predictions || {});
  const actionQueue = rows
    .filter((prediction) => prediction.time_to_low_hours != null || prediction.time_to_critical_hours != null)
    .sort((a, b) => (a.time_to_critical_hours ?? a.time_to_low_hours ?? 99) - (b.time_to_critical_hours ?? b.time_to_low_hours ?? 99));

  return (
    <PageFrame>
      <div className="page-scroll p-8 space-y-8">
        <header className="flex items-end justify-between">
          <div>
            <p className="label-caps status-safe">Confidence Debt Maintenance</p>
            <h1 className="text-4xl font-bold">Confidence Debt / {plantId}</h1>
          </div>
          <button onClick={() => fetchPredictions(plantId)} className="industrial-control status-safe">
            {predictionsLoading ? 'Refreshing...' : 'Refresh'}
          </button>
        </header>

        <ConfidenceDebtPanel />

        <Panel title="Confidence Degradation Forecast">
          <div className="space-y-3">
            {rows.map((prediction) => {
              const low = Math.min(12, prediction.time_to_low_hours ?? 12);
              const crit = Math.min(12, prediction.time_to_critical_hours ?? 12);
              return (
                <div key={prediction.sensor_id} className="grid grid-cols-[120px_1fr_210px] items-center gap-4 caption-mono">
                  <span className="text-[var(--text)]">{prediction.sensor_id}</span>
                  <div className="h-8 flex border border-[var(--border-strong)] bg-[var(--surface-elevated)]">
                    <div className="bg-[var(--safe)] opacity-80" style={{ width: `${(low / 12) * 100}%` }} />
                    {prediction.time_to_low_hours != null && <div className="bg-[var(--warning)] opacity-80" style={{ width: `${Math.max(0, (crit - low) / 12) * 100}%` }} />}
                    {prediction.time_to_critical_hours != null && <div className="bg-[var(--critical)] opacity-80 flex-1" />}
                  </div>
                  <span className="text-[var(--data-mono)]">{prediction.model_type} / {prediction.model_fit}</span>
                </div>
              );
            })}
            {rows.length === 0 && <p className="caption-mono text-[var(--data-mono)]">Waiting for confidence history.</p>}
          </div>
        </Panel>

        <Panel title="Maintenance Operating Basis">
          <div className="space-y-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
            {actionQueue.map((prediction) => (
              <div key={prediction.sensor_id} className="industrial-panel-subtle p-4">
                <p className="font-data status-warning">{prediction.sensor_id}</p>
                <p className="caption-mono text-[var(--data-mono)] mt-2">{prediction.recommended_action || prediction.action}</p>
              </div>
            ))}
            {actionQueue.length === 0 && <p className="industrial-panel-subtle p-4 caption-mono text-[var(--data-mono)]">No sensors currently forecast to cross a lower confidence tier.</p>}
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
  const progress = data?.timeline?.length ? (index / Math.max(1, data.timeline.length - 1)) * 100 : 0;

  return (
    <PageFrame>
      <div className="h-full flex flex-col overflow-hidden">
        <div className="h-[90px] shrink-0 bg-[var(--surface-panel)] border-b border-[var(--warning)] px-5 flex items-center gap-6">
          <span className="industrial-badge bg-[var(--warning)] text-[var(--surface-base)] border-[var(--warning)]">Counterfactual Timeline</span>
          <span className="caption-mono status-warning">Texas City Incident</span>
          <button onClick={() => setPlaying((value) => !value)} className="industrial-control text-[var(--text)]">
            {playing ? 'Pause' : 'Play'}
          </button>
          <div className="flex-1">
            <div className="flex justify-between caption-mono text-[var(--data-mono)] mb-2">
              <span>MAR 23, 2005 - 00:00</span>
              <span className="status-safe">T+{frame?.minute ?? 0}m</span>
              <span>MAR 23, 2005 - 12:00</span>
            </div>
            <div className="h-3 bg-[var(--surface-high)] border border-[var(--border-strong)] relative">
              <div className="absolute left-0 top-0 h-full bg-[var(--safe)]" style={{ width: `${progress}%` }} />
              <div className="absolute top-[-5px] h-5 w-1 bg-[var(--text)]" style={{ left: `${progress}%` }} />
            </div>
            <input
              type="range"
              min="0"
              max={Math.max(0, (data?.timeline?.length || 1) - 1)}
              value={index}
              onChange={(event) => setIndex(Number(event.target.value))}
              className="sr-only"
            />
          </div>
          <div className="flex border border-[var(--border-strong)]">
            {['1x', '5x', '10x', '30x'].map((speed) => (
              <button key={speed} className={`px-3 py-2 caption-mono border-r border-[var(--border-strong)] last:border-r-0 ${speed === '5x' ? 'status-safe bg-[var(--surface-elevated)]' : 'text-[var(--data-mono)]'}`}>
                {speed}
              </button>
            ))}
          </div>
          <button className="industrial-control text-[var(--text)]">Exit Replay</button>
        </div>

        <div className="flex-1 min-h-0 grid grid-cols-[1fr_420px] gap-[1px] bg-[var(--border-strong)] overflow-hidden">
          <main className="min-w-0 overflow-y-auto scrollbar-thin bg-[var(--surface-base)] p-[1px]">
            <Panel title={`Unit 15 ISOM Replay ${frame ? `/ T+${frame.minute}m` : ''}`} className="border-[var(--warning)]">
              <div className="industrial-grid-shell grid-cols-2">
                {readings.map((reading) => {
                  const conf = confidence.find((item) => item.sensor_id === reading.sensor_id);
                  return mode === 'traditional' ? (
                    <div key={reading.sensor_id} className="industrial-panel-subtle p-5 h-[244px] flex flex-col justify-between">
                      <p className="font-data text-[var(--data-mono)]">{reading.sensor_id}</p>
                      <p className="font-data text-5xl font-bold text-[var(--text)]">{reading.value} <span className="text-sm">{reading.unit}</span></p>
                    </div>
                  ) : (
                    <SensorCard key={reading.sensor_id} reading={reading} confidence={conf} />
                  );
                })}
              </div>
            </Panel>
            <div className="h-[280px] mt-[1px]">
              <MassBalanceChart chartHistory={chartHistory} massBalance={frame?.mass_balance} flags={frame?.mass_balance?.flags} />
            </div>
          </main>

          <aside className="bg-[var(--surface-panel)] overflow-y-auto scrollbar-thin">
            <Panel title="Counterfactual Analysis" className="h-full" bodyClassName="industrial-body space-y-5">
              <div className="grid grid-cols-2 gap-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
                <button onClick={() => setMode('confidenceos')} className={`industrial-panel-subtle p-3 label-caps ${mode === 'confidenceos' ? 'status-safe' : 'text-[var(--data-mono)]'}`}>ConfidenceOS Trust Layer</button>
                <button onClick={() => setMode('traditional')} className={`industrial-panel-subtle p-3 label-caps ${mode === 'traditional' ? 'status-safe' : 'text-[var(--data-mono)]'}`}>Existing HMI View</button>
              </div>
              <div className="industrial-panel-subtle p-4 border-[var(--safe)]">
                <p className="label-caps text-[var(--text)] mb-3">Evidence-Based Operating Basis</p>
                <p className="text-[var(--text)] leading-relaxed">
                  Normal operation enters an inferred startup mode. LT-5100 looks plausible but loses trust, alarms collapse into one abnormal situation, evidence creates an action contract, and unresolved verification becomes handover debt.
                </p>
              </div>
              <div>
                <p className="label-caps text-[var(--text-muted)] mb-4">Replay Annotations</p>
                <div className="space-y-4">
                  {(data?.annotations || []).map((note) => (
                    <div key={note.minute} className={`border-l-2 pl-4 ${frame && note.minute <= frame.minute ? 'border-[var(--warning)]' : 'border-[var(--border-strong)]'}`}>
                      <p className={`caption-mono ${frame && note.minute <= frame.minute ? 'status-warning' : 'text-[var(--data-mono)]'}`}>T+{note.minute}m {note.title}</p>
                      <p className="text-[var(--text-muted)] mt-2">{note.body}</p>
                    </div>
                  ))}
                </div>
              </div>
              {presets.length > 0 && <p className="caption-mono text-[var(--data-mono)]">{presets.length} replay preset available.</p>}
            </Panel>
          </aside>
        </div>
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
    const bytes = Uint8Array.from(atob(report.pdf_base64), (char) => char.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = report.pdf_filename || 'confidenceos_report.pdf';
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <PageFrame>
      <div className="h-full grid grid-cols-[340px_1fr] gap-[1px] bg-[var(--border-strong)] overflow-hidden">
        <Panel title="Report Configuration" className="overflow-y-auto scrollbar-thin" bodyClassName="industrial-body space-y-4">
          <label className="block label-caps text-[var(--text-muted)]">Period Hours
            <input value={hours} onChange={(event) => setHours(event.target.value)} type="number" className="industrial-input mt-2" />
          </label>
          <label className="block label-caps text-[var(--text-muted)]">Report Type
            <select value={reportType} onChange={(event) => setReportType(event.target.value)} className="industrial-select mt-2">
              <option value="full">Full Audit</option>
              <option value="alarm">Alarm Management Only</option>
              <option value="sensor">Sensor Reliability Only</option>
              <option value="handover">Shift Handover Log Only</option>
            </select>
          </label>
          <button onClick={generate} className="industrial-control status-safe w-full">{loading ? 'Generating...' : 'Generate Report'}</button>
          <button onClick={download} disabled={!report?.pdf_base64} className="industrial-control text-[var(--data-mono)] w-full disabled:opacity-40">Download PDF</button>
        </Panel>
        <Panel title="Report Preview" className="overflow-y-auto scrollbar-thin">
          {report ? (
            <div className="space-y-5">
              <div>
                <h1 className="text-4xl font-bold text-[var(--text)]">Compliance Report</h1>
                <p className="caption-mono text-[var(--data-mono)] mt-2">{report.plant_name} / {report.period_hours} hours / signed demo artifact</p>
              </div>
              <pre className="industrial-panel-subtle p-4 caption-mono whitespace-pre-wrap text-[var(--data-mono)]">
                {JSON.stringify(report.sections, null, 2)}
              </pre>
            </div>
          ) : (
            <p className="caption-mono text-[var(--data-mono)]">Generate a report to preview audit sections and download the PDF artifact.</p>
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
  nodes.forEach((node, index) => {
    positions[node.id] = { x: 120 + (index % 3) * 230, y: 90 + Math.floor(index / 3) * 180 };
  });

  return (
    <PageFrame>
      <div className="h-full grid grid-cols-[1fr_380px] gap-[1px] bg-[var(--border-strong)] overflow-hidden">
        <Panel title="Causal Graph" className="overflow-hidden" bodyClassName="industrial-body h-full">
          <svg viewBox="0 0 760 460" className="w-full h-[520px] bg-[#090b0c] border border-[var(--border-strong)]">
            {(graph?.edges || []).map((edge) => {
              const a = positions[edge.source];
              const b = positions[edge.target];
              if (!a || !b) return null;
              return <line key={`${edge.source}-${edge.target}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={edge.is_propagating ? '#FFA500' : '#414752'} strokeWidth={edge.is_active ? 4 : 2} />;
            })}
            {nodes.map((node) => {
              const position = positions[node.id];
              const fill = node.tier === 'CRITICAL' ? '#FF0000' : node.tier === 'LOW' ? '#FFA500' : node.tier === 'MEDIUM' ? '#FFD700' : '#00FF41';
              return (
                <g key={node.id}>
                  <rect x={position.x - 48} y={position.y - 32} width="96" height="64" fill="#141619" stroke={fill} strokeWidth="2" />
                  <text x={position.x} y={position.y - 4} textAnchor="middle" fill="#dae6d2" fontSize="14" fontWeight="700">{node.id}</text>
                  <text x={position.x} y={position.y + 16} textAnchor="middle" fill={fill} fontSize="12">{node.confidence_pct}%</text>
                </g>
              );
            })}
          </svg>
        </Panel>
        <Panel title="Root Cause Narrative" className="overflow-y-auto scrollbar-thin">
          <p className="leading-relaxed text-[var(--text)]">{graph?.narrative || 'No graph data yet.'}</p>
          <div className="mt-5 space-y-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
            {(graph?.causal_chains || []).map((chain, index) => (
              <div key={index} className="industrial-panel-subtle p-3 caption-mono text-[var(--data-mono)]">{chain.join(' -> ')}</div>
            ))}
          </div>
          <div className="mt-5">
            <TrustDependencyGraph />
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

  const chartData = result?.results?.map((item) => ({ time: item.time_hours, confidence: item.confidence_pct, discrepancy: item.mass_balance?.discrepancy })) || [];

  return (
    <PageFrame>
      <div className="h-full grid grid-cols-[340px_1fr] gap-[1px] bg-[var(--border-strong)] overflow-hidden">
        <Panel title="Sandbox Controls" bodyClassName="industrial-body space-y-4">
          <select value={form.sensor_id} onChange={(event) => setForm({ ...form, sensor_id: event.target.value })} className="industrial-select">
            {SENSOR_IDS.map((id) => <option key={id} value={id}>{id}</option>)}
          </select>
          <select value={form.failure_mode} onChange={(event) => setForm({ ...form, failure_mode: event.target.value })} className="industrial-select">
            <option value="calibration_drift">Calibration drift</option>
            <option value="stuck_reading">Stuck reading</option>
            <option value="sg_mismatch">Specific gravity mismatch</option>
            <option value="command_state_decoupling">Command-state decoupling</option>
          </select>
          <select value={form.severity} onChange={(event) => setForm({ ...form, severity: event.target.value })} className="industrial-select">
            <option value="mild">Mild</option>
            <option value="moderate">Moderate</option>
            <option value="severe">Severe</option>
          </select>
          <input value={form.duration_hours} onChange={(event) => setForm({ ...form, duration_hours: event.target.value })} type="number" className="industrial-input" />
          <button onClick={run} className="industrial-control status-warning w-full">{loading ? 'Running...' : 'Run Sandbox'}</button>
        </Panel>
        <Panel title="Sandbox Results">
          <div className="h-96 border border-[var(--border-strong)] bg-[#090b0c]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 24, right: 24, left: 0, bottom: 14 }}>
                <CartesianGrid stroke="#2D3139" strokeDasharray="4 4" vertical={false} />
                <XAxis dataKey="time" tick={{ fontSize: 12, fill: '#A0AEC0', fontFamily: 'JetBrains Mono' }} />
                <YAxis tick={{ fontSize: 12, fill: '#A0AEC0', fontFamily: 'JetBrains Mono' }} />
                <Tooltip content={<IndustrialTooltip />} />
                <Line dataKey="confidence" stroke="#00FF41" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line dataKey="discrepancy" stroke="#FFA500" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          {result && <p className="mt-3 caption-mono text-[var(--data-mono)]">{result.sample_count} samples generated without touching live plant data.</p>}
        </Panel>
      </div>
    </PageFrame>
  );
}

function BottomStatus() {
  const { connected, timestamp } = useStore();
  const [clock, setClock] = useState(() => new Date());

  useEffect(() => {
    const timer = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <footer className="bottom-status">
      <span>ConfidenceOS Industrial Intelligence v4.2.0-stable</span>
      <div className="flex items-center gap-8">
        <span>System Logs</span>
        <span>UTC Timestamp: {clock.toLocaleTimeString()}</span>
        <span className={connected ? 'status-safe' : 'status-critical'}>{connected ? 'API Status' : 'API Offline'}</span>
        {timestamp && <span>Last Tick: {new Date(timestamp * 1000).toLocaleTimeString()}</span>}
      </div>
    </footer>
  );
}

function App() {
  return (
    <div className="industrial-app">
      <NavBar />
      <main className="industrial-main">
        <Routes>
          <Route path="/" element={<RuntimePlatform />} />
          <Route path="/runtime" element={<RuntimePlatform />} />
          <Route path="/studio" element={<StudioWorkspace />} />
          <Route path="/handover" element={<ShiftChannel />} />
          <Route path="/integrity" element={<InstrumentIntegrityOverviewPage />} />
          <Route path="/operator" element={<OperatorSupportView />} />
          <Route path="/predictions" element={<ConfidenceDebtPage />} />
          <Route path="/forensics" element={<ForensicsPage />} />
          <Route path="/graph" element={<CausalGraphPage />} />
          <Route path="/compliance" element={<CompliancePage />} />
          <Route path="/sandbox" element={<SandboxPage />} />
        </Routes>
      </main>
      <BottomStatus />
    </div>
  );
}

export default App;
