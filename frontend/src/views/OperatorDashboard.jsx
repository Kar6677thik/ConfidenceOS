/**
 * views/OperatorDashboard.jsx - Secondary Runtime Support View
 *
 * Endpoints (via Zustand store):
 *   WS  /ws/sensors?plant_id=...  - live 1Hz sensor + confidence + mass-balance
 *   POST /api/mode/startup         - toggle startup scrutiny mode
 *   POST /api/mode/startup/acknowledge/:id - clear stale flag
 *   GET  /api/predictions/:plant_id - forecast data (sidebar)
 *
 * Stitch mockup: secondary operator support view
 */

import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useStore from '../store';
import SensorCard from '../components/SensorCard';
import MassBalanceChart from '../components/MassBalanceChart';
import HealthTimeline from '../components/HealthTimeline';
import HandoverBrief from '../components/HandoverBrief';
import StartupBanner from '../components/StartupBanner';
import FlagBar from '../components/FlagBar';
import QueryPanel from '../components/QueryPanel';

// Friend's component integrations:
import IncidentQueue from '../components/IncidentQueue';
import EvidenceStack from '../components/EvidenceStack';
import IncidentTimeline from '../components/IncidentTimeline';
import ScoreSensitivityPanel from '../components/ScoreSensitivityPanel';
import VerificationTokens from '../components/VerificationTokens';
import HandoverDebtLedger from '../components/HandoverDebtLedger';
import PageIdentity from '../components/hmi/PageIdentity';

function healthColor(pct) {
  if (pct >= 80) return 'text-[var(--safe-text)]';
  if (pct >= 50) return 'text-[var(--caution)]';
  if (pct >= 20) return 'text-[var(--warning)]';
  return 'text-[var(--critical)]';
}

function statusClass(status) {
  const s = String(status || '').toUpperCase();
  if (s === 'CRITICAL') return 'status-critical';
  if (s === 'WARNING' || s === 'STARTUP' || s === 'MEDIUM') return 'status-warning';
  if (s === 'LOW' || s === 'LOW RISK' || s === 'OK' || s === 'NOMINAL') return 'status-safe';
  return 'text-[var(--text-muted)]';
}

function PredictionSidecard({ prediction }) {
  if (!prediction) {
    return (
      <p className="caption-mono text-[var(--text-muted)] p-4 text-[12px]">
        Select a sensor to view confidence degradation forecast data.
      </p>
    );
  }
  const hasCrit = prediction.time_to_critical_hours != null;
  const hasLow  = prediction.time_to_low_hours != null;
  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="font-data text-[var(--primary)] text-[14px] font-bold">{prediction.sensor_id}</span>
        <span className="caption-mono text-[var(--text-muted)] text-[11px]">
          {prediction.model_type || 'unknown'} / {prediction.model_fit || 'insufficient'}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="industrial-card p-3 text-center">
          <p className="label-caps text-[var(--text-muted)] mb-1">LOW in</p>
          <p className={`text-[24px] font-bold font-data ${hasLow ? 'text-[var(--warning)]' : 'text-[var(--text-dim)]'}`}>
            {hasLow ? `${prediction.time_to_low_hours}h` : 'N/A'}
          </p>
        </div>
        <div className="industrial-card p-3 text-center">
          <p className="label-caps text-[var(--text-muted)] mb-1">CRIT in</p>
          <p className={`text-[24px] font-bold font-data ${hasCrit ? 'text-[var(--critical)]' : 'text-[var(--text-dim)]'}`}>
            {hasCrit ? `${prediction.time_to_critical_hours}h` : 'N/A'}
          </p>
        </div>
      </div>
      <p className="caption-mono text-[var(--text-muted)] text-[12px] leading-relaxed">
        {prediction.recommended_action || prediction.action || 'No recommendation available.'}
      </p>
    </div>
  );
}

// -- Context Strip --
function ContextStrip({ context, incidents = [], incidentTimeline = [] }) {
  if (!context) return null;
  const cls = statusClass(context.severity);
  const inference = context.inferred_mode || context.mode_inference;
  const leadIncident = incidents?.[0];
  const collapse = leadIncident?.alarm_collapse;
  const collapsedCount = collapse?.raw_signal_count ?? leadIncident?.source_flags?.length;
  return (
    <div className="industrial-card p-4">
      <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
        <div className="flex items-center gap-2">
          <span className={`industrial-badge ${cls}`}>{context.state || 'STEADY_STATE'}</span>
          <span className="caption-mono text-[var(--text-muted)]">{context.layout_hint || 'standard_monitoring'}</span>
          {inference?.rule_id && <span className="caption-mono text-[var(--text-muted)]">{inference.rule_id}</span>}
        </div>
        {!!context.priority_sensors?.length && (
          <div className="flex flex-wrap gap-1">
            {context.priority_sensors.map((sensorId) => (
              <span key={sensorId} className="industrial-badge text-[var(--text-muted)]">{sensorId}</span>
            ))}
          </div>
        )}
      </div>
      <p className="caption-mono text-[var(--text)] text-[13px]">{context.operator_focus || 'No active operator focus.'}</p>
      {leadIncident && (
        <div className="mt-2 flex flex-wrap items-center gap-2 caption-mono text-[12px] text-[var(--warning)]">
          <span className="flex items-center gap-1"><span className="material-symbols-outlined text-[16px]">warning</span>{leadIncident.title}</span>
          {collapsedCount != null && <span className="text-[var(--text-muted)]">(collapsed from {collapsedCount} signals)</span>}
          {!!incidentTimeline.length && <span className="text-[var(--text-muted)]">/ {incidentTimeline.length} events</span>}
        </div>
      )}
    </div>
  );
}

// -- Asset Integration Strip --
function AssetIntegrationStrip({ plantId }) {
  const [metadata, setMetadata] = useState(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetch(`/api/asset-model?plant_id=${encodeURIComponent(plantId)}`).then((res) => (res.ok ? res.json() : null)),
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
  }, [plantId]);

  if (!metadata?.asset && !metadata?.integration) return null;

  const equipment = metadata.asset?.equipment || {};
  const relationship = (equipment.relationships || []).find((item) => item.type === 'mass_balance_validation') || {};
  const provider = metadata.integration?.active_providers?.[plantId] || {};
  const opcua = metadata.integration?.opcua_boundary || {};
  const sensorCount = equipment.sensor_tags?.length || 0;
  const validationText = relationship.source_tags?.length
    ? `${relationship.source_tags.join(' + ')} validates ${relationship.validated_tag}`
    : 'metadata relationship unavailable';

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
      <div className="industrial-card p-3">
        <p className="label-caps text-[var(--text-muted)]">Asset Metadata</p>
        <p className="caption-mono text-[var(--text)] mt-1 font-semibold text-[13px]">{equipment.equipment_id || 'V-5100'} / {sensorCount} tags</p>
      </div>
      <div className="industrial-card p-3">
        <p className="label-caps text-[var(--text-muted)]">Self-Configured Check</p>
        <p className="caption-mono text-[var(--text)] mt-1 font-semibold text-[13px]">{validationText}</p>
      </div>
      <div className="industrial-card p-3">
        <p className="label-caps text-[var(--safe-text)]">Read-Only Provider</p>
        <p className="caption-mono text-[var(--text)] mt-1 font-semibold text-[13px]">
          {provider.display_name || 'TagProvider'} / {provider.control_writes_enabled === false ? 'Read-only' : 'Active'}
        </p>
        <p className="caption-mono text-[var(--text-muted)] mt-1">
          OPC UA: {opcua.configured ? 'configured read-only boundary' : 'planned boundary, not connected in demo'}
        </p>
      </div>
    </div>
  );
}

// -- Stress Mode Layout --
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
    return <p className="caption-mono text-[var(--text-muted)]">{empty}</p>;
  }
  return (
    <div className="space-y-1">
      {rows.slice(0, 6).map((value) => (
        <p key={value} className="caption-mono text-[var(--text)]">{formatStressValue(value)}</p>
      ))}
    </div>
  );
}

function StressRow({ label, tone = 'text-[var(--text-muted)]', children }) {
  return (
    <div className="industrial-card p-4 grid grid-cols-1 md:grid-cols-[180px_1fr] gap-4">
      <div className="border-r border-[var(--border)] pr-4 flex items-center md:items-start">
        <p className={`label-caps ${tone} font-bold`}>{label}</p>
      </div>
      <div className="min-w-0">
        {children}
      </div>
    </div>
  );
}

function StressModeLayout({
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
    <div className="flex flex-col gap-4">
      <div className="flex justify-between items-center border-b border-[var(--border)] pb-2">
        <div>
          <span className="label-caps text-[var(--text-muted)]">Stress Mode / {plantId?.toUpperCase()}</span>
          <h2 className="text-[20px] font-bold text-[var(--critical)] mt-1 flex items-center gap-2">
            <span className="material-symbols-outlined text-[22px]">warning</span>
            {leadIncident?.title || context?.state || 'Abnormal Situation'}
          </h2>
        </div>
        <span className="industrial-badge text-[var(--critical)] border-[var(--critical)]">
          CRITICAL INTEGRITY RISK
        </span>
      </div>

      <div className="space-y-2">
        <StressRow label="Abnormal Situation" tone="text-[var(--warning)]">
          <p className="caption-mono text-[var(--text)] leading-relaxed text-[13px]">
            {leadIncident?.summary || context?.operator_focus || 'Abnormal plant context active.'}
          </p>
          {collapsedCount != null && (
            <p className="caption-mono text-[var(--text-muted)] mt-2 text-[12px]">Collapsed from {collapsedCount} raw HMI alarms</p>
          )}
          {!!leadIncident?.root_trigger && (
            <p className="caption-mono text-[var(--text-dim)] mt-1 text-[11px]">Root Cause Hypothesis: {formatStressValue(leadIncident.root_trigger)}</p>
          )}
        </StressRow>

        <StressRow label="Do Not Trust" tone="text-[var(--critical)]">
          <StressValueList values={doNotTrust} empty="No blocked instrument trust restriction reported." />
        </StressRow>

        <StressRow label="Use Instead" tone="text-[var(--safe-text)]">
          <StressValueList values={contract.trusted_substitutes} empty="Use manual field verification or adjacent validated references." />
        </StressRow>

        <StressRow label="First Safe Action" tone="text-[var(--safe-text)]">
          <StressValueList values={firstSafeAction} empty="Verify evidence before taking the next operating action." />
        </StressRow>

        <StressRow label="Exit Condition" tone="text-[var(--primary)]">
          <StressValueList values={contract.exit_conditions} empty="No exit condition reported yet." />
        </StressRow>

        <StressRow label="Evidence Base" tone="text-[var(--warning)]">
          <StressValueList values={evidenceRows} empty="No structured evidence reported yet." />
          {incidentTimeline?.length > 0 && (
            <div className="mt-4 pt-4 border-t border-[var(--border)]">
              <p className="label-caps text-[var(--text-muted)] mb-2">Decision-Integrity Log</p>
              <IncidentTimeline events={incidentTimeline} compact />
            </div>
          )}
        </StressRow>
      </div>
    </div>
  );
}

// -- Secondary Runtime Support View --
export default function OperatorDashboard() {
  const navigate = useNavigate();
  const [railMessage, setRailMessage] = useState('');
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

  useEffect(() => { connect(); }, [connect]);
  useEffect(() => { fetchPredictions(plantId); }, [fetchPredictions, plantId]);
  useEffect(() => {
    if (!['Operator', 'Maintenance', 'Engineer', 'Manager'].includes(role)) {
      navigate('/runtime', { replace: true });
    }
  }, [role, navigate]);

  const selectedPrediction = predictions?.[selectedSensorId];
  const isStressMode = ['WARNING', 'CRITICAL'].includes(String(plantContext?.severity || '').toUpperCase());

  const lastUpdate = useMemo(() => {
    if (!readings.length) return '-';
    return new Date().toLocaleTimeString();
  }, [readings]);

  const railActions = [
    { id: 'RT', label: 'RT', title: 'Open primary Runtime', action: () => navigate('/runtime') },
    { id: 'GR', label: 'GR', title: 'Grounded Operator Explanation', action: () => document.getElementById('grounded-explanation-panel')?.scrollIntoView({ block: 'start' }) },
    { id: 'SB', label: 'SB', title: 'Shift Channel', action: () => navigate('/handover') },
    { id: 'SG', label: 'SG', title: 'Signal Graph', action: () => navigate('/graph') },
  ];

  return (
    <div className="industrial-page flex flex-col overflow-hidden">
      {/* Startup mode banner */}
      {mode?.is_active && (
        <div className="startup-banner shrink-0">
          <span className="material-symbols-outlined text-[var(--critical)] text-[18px]">warning</span>
          <span className="label-caps text-[var(--critical)] tracking-widest">
            STARTUP MODE ACTIVE - ELEVATED MONITORING REQUIRED
          </span>
        </div>
      )}

      {/* Main 3-column layout */}
      <div className="flex flex-1 overflow-hidden">

        {/* -- Left Rail (Static layout helper buttons) -- */}
        <aside className="w-12 bg-[var(--bg-low)] border-r border-[var(--border)] flex flex-col justify-between items-center py-4 shrink-0">
          <div className="flex flex-col gap-4">
            {railActions.map((item, i) => (
              <button
                key={item.id}
                type="button"
                title={item.title}
                onClick={item.action}
                className={`w-8 h-8 rounded flex items-center justify-center font-bold text-[11px] caption-mono border border-[var(--border)] hover:bg-[var(--bg-elevated)]
                ${i === 0 ? 'bg-[var(--bg-elevated)] text-[var(--primary)] border-[var(--primary)]/40' : 'text-[var(--text-muted)]'}`}>
                {item.label}
              </button>
            ))}
          </div>
          <div className="flex flex-col gap-2">
            <button
              type="button"
              title="Explain support rail"
              onClick={() => setRailMessage('RT opens the primary Runtime, GR jumps to the grounded explanation, SB opens Shift Channel, and SG opens the signal graph. These controls are read-only navigation shortcuts.')}
              className="w-8 h-8 rounded flex items-center justify-center text-[10px] font-bold text-[var(--text-muted)] border border-[var(--border)] hover:bg-[var(--bg-elevated)]"
            >
              INFO
            </button>
            <button
              type="button"
              title="Read-only boundary"
              onClick={() => setRailMessage('ConfidenceOS does not write setpoints, controller modes, tag values, or alarm acknowledgements. Configuration changes belong in Studio and require engineer approval.')}
              className="w-8 h-8 rounded flex items-center justify-center text-[10px] font-bold text-[var(--text-muted)] border border-[var(--border)] hover:bg-[var(--bg-elevated)]"
            >
              HELP
            </button>
          </div>
        </aside>

        {/* -- Center Canvas -- */}
        <main className="flex-1 min-w-0 flex flex-col overflow-hidden bg-[var(--bg-base)]">
          <PageIdentity displayName="Operator Support Runtime" level={3} area="Secondary Operator View" plant={plantId} />
          <div className="flex items-center gap-3 px-5 py-1.5 border-b border-[var(--border)] flex-shrink-0">
            <span className={`industrial-badge ${connected ? 'text-[var(--safe-text)] border-[var(--safe-text)]' : 'text-[var(--critical)] border-[var(--critical)]'}`}>
              {connected ? 'LIVE' : 'OFFLINE'}
            </span>
            <span className={`font-data text-[20px] font-bold ${healthColor(averageConfidence)}`}>
              {averageConfidence}%
            </span>
            <span className="caption-mono text-[var(--text-dim)] ml-auto">
              Last Update: <span className="text-[var(--primary)]">{lastUpdate}</span>
            </span>
          </div>
          <div className="flex-1 overflow-y-auto scrollbar-thin overflow-x-hidden p-4 gap-4 flex flex-col">
          {railMessage && (
            <div className="industrial-card p-3 caption-mono text-[var(--data-mono)] flex items-center justify-between gap-3">
              <span>{railMessage}</span>
              <button type="button" onClick={() => setRailMessage('')} className="industrial-control text-[var(--text-muted)]">Dismiss</button>
            </div>
          )}

          {isStressMode ? (
            <StressModeLayout
              plantId={plantId}
              context={plantContext}
              incidents={incidents}
              confidence={confidence}
              massBalance={massBalance}
              incidentTimeline={incidentTimeline}
            />
          ) : (
            <>
              {/* Context strip */}
              <ContextStrip context={plantContext} incidents={incidents} incidentTimeline={incidentTimeline} />

              {/* Asset integration strip */}
              <AssetIntegrationStrip plantId={plantId} />

              {/* Startup manager */}
              <StartupBanner
                isActive={mode?.is_active ?? false}
                onToggle={toggleStartupMode}
                staleFlags={staleFlags}
                onAcknowledge={acknowledgeStale}
              />

              {/* Sensor grid */}
              <div>
                <p className="label-caps text-[var(--text-muted)] mb-2">Critical Sensors</p>
                <div className="grid grid-cols-2 xl:grid-cols-3 gap-1 bg-[var(--border)] border border-[var(--border)]">
                  {readings.map((reading) => {
                    const conf = confidence.find((c) => c.sensor_id === reading.sensor_id);
                    return (
                      <SensorCard
                        key={reading.sensor_id}
                        reading={reading}
                        confidence={conf}
                        isSelected={selectedSensorId === reading.sensor_id}
                        onSelect={selectSensor}
                      />
                    );
                  })}
                </div>
              </div>

              {/* Mass-balance chart */}
              <div className="h-[380px] shrink-0">
                <MassBalanceChart chartHistory={chartHistory} massBalance={massBalance} flags={massBalance?.flags} />
              </div>

              {/* Incidents Queue / Flag bar */}
              <div className="shrink-0">
                {Array.isArray(incidents) ? (
                  <IncidentQueue incidents={incidents} confidence={confidence} massBalance={massBalance} staleFlags={staleFlags} />
                ) : (
                  <FlagBar confidence={confidence} massBalance={massBalance} staleFlags={staleFlags} />
                )}
              </div>
            </>
          )}
          </div>
        </main>

        {/* -- Right Sidebar -- */}
        <aside className="w-80 xl:w-96 bg-[var(--bg-surface)] border-l border-[var(--border)] flex flex-col overflow-y-auto scrollbar-thin shrink-0 p-4 gap-4">
          
          {/* Query assistant */}
          <div id="grounded-explanation-panel" className="industrial-card p-0 overflow-hidden shrink-0">
            <div className="industrial-card-header px-4 py-3 border-b border-[var(--border)]">
              <span className="text-[14px] font-semibold text-[var(--text)]">Grounded Operator Explanation</span>
            </div>
            <div className="h-[380px]">
              <QueryPanel />
            </div>
          </div>

          {/* Confidence degradation forecast */}
          <div className="industrial-card p-0 overflow-hidden shrink-0">
            <div className="industrial-card-header px-4 py-3 border-b border-[var(--border)]">
              <span className="text-[14px] font-semibold text-[var(--text)]">Confidence Forecast</span>
            </div>
            <PredictionSidecard prediction={selectedPrediction} />
          </div>

          {/* Evidence stack */}
          <div className="shrink-0">
            <EvidenceStack selectedSensorId={selectedSensorId} confidence={confidence} incidents={incidents} />
          </div>

          {/* Verification tokens */}
          <div className="shrink-0">
            <VerificationTokens selectedSensorId={selectedSensorId} confidence={confidence} />
          </div>

          {/* Incident timeline */}
          <div className="shrink-0">
            <div className="industrial-card p-4">
              <p className="label-caps text-[var(--text-muted)] mb-3">Incident Log</p>
              <IncidentTimeline events={incidentTimeline} />
            </div>
          </div>

          {/* Handover debt ledger */}
          <div className="shrink-0">
            <HandoverDebtLedger />
          </div>

          {/* Engineer deep-dive (role-scoped, advisory) */}
          {role === 'Engineer' && selectedSensorId && (
            <>
              <div className="industrial-card p-0 overflow-hidden shrink-0">
                <div className="industrial-card-header px-4 py-3 border-b border-[var(--border)]">
                  <span className="text-[14px] font-semibold text-[var(--text)]">Engineer Deep-Dive</span>
                </div>
                <EngineerMini sensorId={selectedSensorId} confidence={confidence} />
              </div>
              <div className="shrink-0">
                <ScoreSensitivityPanel selectedSensorId={selectedSensorId} />
              </div>
            </>
          )}

          {/* Health timeline + Handover */}
          <div className="shrink-0">
            <HealthTimeline sensorId={selectedSensorId} />
          </div>
          <div className="shrink-0">
            <HandoverBrief />
          </div>
        </aside>
      </div>
    </div>
  );
}

function EngineerMini({ sensorId, confidence }) {
  const selected = confidence.find((c) => c.sensor_id === sensorId);
  const subs = selected?.sub_scores || {};

  return (
    <div className="p-4 space-y-3">
      <div className="grid grid-cols-2 gap-1">
        {[
          { key: 'CAL', val: subs.calibration },
          { key: 'STB', val: subs.stability },
          { key: 'XSN', val: subs.cross_sensor },
          { key: 'PHY', val: subs.physical_plausibility },
        ].map(({ key, val }) => {
          const pct = val != null ? Math.round(val * 100) : null;
          const col = pct == null ? 'text-[var(--text-dim)]'
            : pct >= 80 ? 'text-[var(--safe-text)]'
            : pct >= 50 ? 'text-[var(--caution)]'
            : 'text-[var(--critical)]';
          return (
            <div key={key} className="industrial-card p-2 text-center min-w-0">
              <p className="caption-mono text-[var(--text-muted)] whitespace-nowrap">{key}</p>
              <p className={`text-[16px] font-bold font-data mt-1 ${col}`}>
                {pct != null ? `${pct}%` : '-'}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
