import { useEffect, useMemo, useState } from 'react';
import useStore from '../store';
import GenerationReceipt, { ReceiptSummary } from './GenerationReceipt';
import IncidentTimeline from './IncidentTimeline';

function statusClass(value) {
  const status = String(value || '').toUpperCase();
  if (status === 'CRITICAL' || status === 'BLOCKING' || status === 'LOW') return 'status-critical';
  if (status === 'WARNING' || status === 'PASS_WITH_WARNINGS') return 'status-warning';
  if (status === 'MEDIUM' || status === 'CAUTION') return 'status-caution';
  return 'status-safe';
}

function formatText(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function asList(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  if (value == null || value === '') return [];
  return [value];
}

function confidenceValue(confidence) {
  const pct = confidence?.confidence_pct ?? confidence?.score ?? confidence?.value;
  return Number.isFinite(Number(pct)) ? Math.round(Number(pct)) : null;
}

function signalTrustState(signal) {
  const confidence = signal?.confidence || {};
  const tier = confidence.tier || confidence.state || 'HIGH';
  const pct = confidenceValue(confidence);
  return {
    tier,
    pct,
    label: pct == null ? formatText(tier) : `${pct}% ${formatText(tier)}`,
  };
}

function buildBasisLines(manifest) {
  const basis = manifest?.operating_basis || {};
  const evidence = asList(basis.evidence);
  const lines = [
    {
      statement: basis.abnormal_situation || 'Normal operation.',
      owner_role: 'Operator',
      evidence,
      status: basis.abnormal_situation && basis.abnormal_situation !== 'Normal operation' ? 'active' : 'normal',
      expires_when: 'abnormal situation clears',
    },
    ...asList(basis.do_not_trust).map((item) => ({
      statement: `${formatText(item)} is not trusted.`,
      owner_role: 'Operator',
      evidence,
      status: 'active',
      expires_when: 'manual verification clears or confidence recovers',
    })),
    ...asList(basis.trusted_substitutes).map((item) => ({
      statement: `Use ${formatText(item)} as trusted substitute.`,
      owner_role: 'Operator',
      evidence,
      status: 'active',
      expires_when: 'primary indication is verified',
    })),
    ...asList(basis.first_safe_action).map((item) => ({
      statement: formatText(item),
      owner_role: 'Operator',
      evidence,
      status: 'active',
      expires_when: 'first safe action completed',
    })),
    ...asList(basis.decision_freeze).map((item) => ({
      statement: `${formatText(item)} is under decision freeze.`,
      owner_role: 'Operator',
      evidence,
      status: 'active',
      expires_when: 'exit condition is satisfied',
    })),
    ...asList(basis.exit_condition).map((item) => ({
      statement: `Exit condition: ${formatText(item)}.`,
      owner_role: 'Operator',
      evidence,
      status: 'active',
      expires_when: item,
    })),
  ];
  return lines.length ? lines : [{
    statement: 'No abnormal operating basis is active.',
    owner_role: 'Operator',
    evidence: [],
    status: 'normal',
    expires_when: 'new mode or advisory state appears',
  }];
}

function DemoPathStrip() {
  const steps = ['Studio', 'Generate Screens', 'Runtime', 'Abnormal Situation', 'Role Views', 'Handover Debt'];
  return (
    <section className="industrial-panel mb-[1px]">
      <div className="industrial-body">
        <div className="grid grid-cols-2 md:grid-cols-6 gap-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
          {steps.map((step, index) => (
            <div key={step} className="bg-[var(--surface-panel)] p-3 min-h-[64px]">
              <p className="label-caps text-[var(--text-muted)]">Step {index + 1}</p>
              <p className={`caption-mono mt-2 ${index === 2 ? 'status-safe' : 'text-[var(--text)]'}`}>{step}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function computeTrustMap(manifest, storeState) {
  const faceplates = manifest?.faceplates || [];
  const allSignals = faceplates.flatMap((faceplate) => faceplate.signals || []);
  const activeSituations = manifest?.situations?.length ? manifest.situations : storeState.incidents || [];
  const affectedSensors = new Set(activeSituations.flatMap((item) => asList(item.affected_sensors)));
  const lowTrustSignals = allSignals.filter((signal) => {
    const trust = signalTrustState(signal);
    return affectedSensors.has(signal.tag) || ['LOW', 'CRITICAL', 'MEDIUM'].includes(String(trust.tier).toUpperCase());
  });
  const frozenDecisions = new Set([
    ...asList(manifest?.operating_basis?.decision_freeze),
    ...activeSituations.flatMap((item) => asList(item.blocked_decisions)),
  ]);
  const handoverEntries = storeState.handoverDebt?.entries || [];
  const healthySignals = allSignals.filter((signal) => !lowTrustSignals.some((item) => item.tag === signal.tag));
  return {
    activeSituations,
    lowTrustSignals,
    frozenDecisions: [...frozenDecisions].filter(Boolean),
    unresolvedDebt: handoverEntries.filter((item) => item.handover_required !== false),
    hiddenHealthyAssets: Math.max(0, healthySignals.length - 3),
  };
}

function TrustMapNavigation({ navigation, faceplates, selected, onSelect, trustMap }) {
  const areas = navigation?.areas || [];
  const faceplateById = Object.fromEntries((faceplates || []).map((item) => [item.equipment_id, item]));

  return (
    <aside className="bg-[var(--surface-panel)] border-r border-[var(--border-strong)] overflow-y-auto scrollbar-thin">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Trust Map Navigation</p>
          <h2 className="industrial-panel-title text-base">{navigation?.name || 'Plant'}</h2>
        </div>
      </div>
      <div className="industrial-body space-y-3">
        <div className="grid grid-cols-2 gap-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
          <div className="bg-[var(--surface-base)] p-3">
            <p className="label-caps status-warning">Trust Hotspots</p>
            <p className="text-2xl font-bold text-[var(--text)] mt-1">{trustMap.lowTrustSignals.length}</p>
          </div>
          <div className="bg-[var(--surface-base)] p-3">
            <p className="label-caps status-warning">Frozen Decisions</p>
            <p className="text-2xl font-bold text-[var(--text)] mt-1">{trustMap.frozenDecisions.length}</p>
          </div>
          <div className="bg-[var(--surface-base)] p-3">
            <p className="label-caps text-[var(--text-muted)]">Unresolved Debt</p>
            <p className="text-2xl font-bold text-[var(--text)] mt-1">{trustMap.unresolvedDebt.length}</p>
          </div>
          <div className="bg-[var(--surface-base)] p-3">
            <p className="label-caps text-[var(--text-muted)]">Healthy Hidden</p>
            <p className="text-2xl font-bold text-[var(--text)] mt-1">{trustMap.hiddenHealthyAssets}</p>
          </div>
        </div>

        {areas.map((area) => (
          <div key={area.id} className="border border-[var(--border-strong)] bg-[var(--surface-base)]">
            <div className="p-3">
              <p className="label-caps text-[var(--text-muted)]">Area</p>
              <p className="caption-mono text-[var(--text)] mt-1">{area.name}</p>
            </div>
            {(area.units || []).map((unit) => (
              <div key={unit.id} className="border-t border-[var(--border-strong)]">
                <div className="p-3 pl-5">
                  <p className="label-caps text-[var(--text-muted)]">Unit</p>
                  <p className="caption-mono text-[var(--data-mono)] mt-1">{unit.name}</p>
                </div>
                {(unit.modules || []).map((module) => (
                  <div key={module.id} className="border-t border-[var(--border-strong)] p-3 pl-7">
                    <p className="label-caps text-[var(--text-muted)]">Module</p>
                    <p className="caption-mono text-[var(--text)] mt-1">{module.name}</p>
                    <div className="mt-3 space-y-2">
                      {(module.equipment || []).map((equipmentId) => {
                        const faceplate = faceplateById[equipmentId];
                        const signals = faceplate?.signals || [];
                        const hotspotCount = signals.filter((signal) => trustMap.lowTrustSignals.some((item) => item.tag === signal.tag)).length;
                        return (
                          <button
                            key={equipmentId}
                            onClick={() => onSelect(equipmentId)}
                            className={`w-full text-left border p-3 ${selected === equipmentId ? 'border-[var(--safe)] bg-[var(--surface-elevated)]' : 'border-[var(--border-strong)] bg-[var(--surface-panel)]'}`}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="caption-mono text-[var(--text)]">{equipmentId}</span>
                              <span className={`industrial-badge ${hotspotCount ? 'status-warning' : 'status-safe'}`}>
                                {hotspotCount ? `${hotspotCount} hotspot` : 'normal'}
                              </span>
                            </div>
                            <div className="mt-2 flex flex-wrap gap-2">
                              {signals.slice(0, 4).map((signal) => {
                                const trust = signalTrustState(signal);
                                return (
                                  <span key={signal.tag} className={`industrial-badge ${statusClass(trust.tier)}`}>
                                    {signal.tag}
                                  </span>
                                );
                              })}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>
    </aside>
  );
}

function OperatingBasisLedger({ basisLines, compact = false }) {
  return (
    <section className="industrial-panel mb-[1px]">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Operating Basis Ledger</p>
          <h2 className="industrial-panel-title text-base">Current basis for operator decisions</h2>
        </div>
        <span className="industrial-badge text-[var(--data-mono)]">{basisLines.length} basis line(s)</span>
      </div>
      <div className="industrial-body space-y-[1px] bg-[var(--border-strong)]">
        {basisLines.slice(0, compact ? 6 : 10).map((line, index) => (
          <div key={`${line.statement}-${index}`} className="grid grid-cols-1 xl:grid-cols-[1.5fr_140px_1fr_180px] gap-[1px] bg-[var(--border-strong)]">
            <div className="bg-[var(--surface-panel)] p-3">
              <p className={`label-caps ${line.status === 'normal' ? 'status-safe' : 'status-warning'}`}>{formatText(line.status)}</p>
              <p className="caption-mono text-[var(--text)] mt-1">{line.statement}</p>
            </div>
            <div className="bg-[var(--surface-base)] p-3">
              <p className="label-caps text-[var(--text-muted)]">Owner</p>
              <p className="caption-mono text-[var(--data-mono)] mt-1">{line.owner_role}</p>
            </div>
            <div className="bg-[var(--surface-base)] p-3">
              <p className="label-caps text-[var(--text-muted)]">Evidence</p>
              {asList(line.evidence).length ? asList(line.evidence).slice(0, 3).map((item) => (
                <p key={item} className="caption-mono text-[var(--data-mono)] mt-1">{formatText(item)}</p>
              )) : <p className="caption-mono text-[var(--data-mono)] mt-1">No evidence required.</p>}
            </div>
            <div className="bg-[var(--surface-base)] p-3">
              <p className="label-caps text-[var(--text-muted)]">Expires When</p>
              <p className="caption-mono text-[var(--data-mono)] mt-1">{formatText(line.expires_when)}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function decisionTimeScore(situation, confidence) {
  const affected = asList(situation?.affected_sensors);
  const scores = (confidence || [])
    .filter((item) => affected.includes(item.sensor_id))
    .map((item) => Number(item.confidence_pct))
    .filter(Number.isFinite);
  if (!scores.length) return situation?.severity === 'critical' ? 35 : 72;
  return Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length);
}

function SituationWorkspace({ situations, basis, confidence }) {
  const lead = situations?.[0] || {};
  const contract = lead.action_contract || {};
  const collapse = lead.alarm_collapse || {};
  const score = decisionTimeScore(lead, confidence);
  const rows = [
    ['Do Not Trust', contract.do_not_use || basis?.do_not_trust, 'status-critical'],
    ['Trusted Substitute', contract.trusted_substitutes || basis?.trusted_substitutes, 'status-safe'],
    ['First Safe Action', contract.first_safe_action || basis?.first_safe_action, 'status-safe'],
    ['Decision Freeze', contract.blocked_decisions || basis?.decision_freeze, 'status-warning'],
    ['Exit Condition', contract.exit_conditions || basis?.exit_condition, 'text-[var(--data-mono)]'],
  ];

  return (
    <section className="industrial-panel mb-[1px]">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps status-warning">Situation Workspace</p>
          <h2 className="industrial-panel-title">{lead.title || basis?.abnormal_situation || 'No abnormal situation active'}</h2>
        </div>
        <div className="text-right">
          <p className="label-caps text-[var(--text-muted)]">Decision-Time Score</p>
          <p className={`text-2xl font-bold ${statusClass(score < 50 ? 'CRITICAL' : score < 75 ? 'WARNING' : 'SAFE')}`}>{score}</p>
        </div>
      </div>
      <div className="industrial-body">
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
          {rows.map(([label, value, cls]) => (
            <div key={label} className="bg-[var(--surface-base)] p-3 min-h-[126px]">
              <p className={`label-caps ${cls}`}>{label}</p>
              {asList(value).length ? asList(value).slice(0, 4).map((item) => (
                <p key={item} className="caption-mono text-[var(--text)] mt-2">{formatText(item)}</p>
              )) : <p className="caption-mono text-[var(--data-mono)] mt-2">Not active</p>}
            </div>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-1 xl:grid-cols-[1.2fr_1fr] gap-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
          <div className="bg-[var(--surface-panel)] p-4">
            <p className="label-caps text-[var(--text-muted)]">Evidence Ledger</p>
            {asList(lead.evidence_refs || basis?.evidence).length ? asList(lead.evidence_refs || basis?.evidence).map((item) => (
              <p key={item} className="caption-mono text-[var(--text)] mt-2">{formatText(item)}</p>
            )) : <p className="caption-mono text-[var(--data-mono)] mt-2">No active evidence ledger entries.</p>}
          </div>
          <div className="bg-[var(--surface-panel)] p-4">
            <p className="label-caps text-[var(--text-muted)]">Alarm Collapse Receipt</p>
            <p className="caption-mono text-[var(--text)] mt-2">
              {collapse.collapsed ? `Collapsed from ${collapse.raw_signal_count || collapse.consumed_alarm_types?.length || 0} signals.` : 'No alarm collapse active.'}
            </p>
            {asList(collapse.consumed_alarm_types).map((item) => (
              <p key={item} className="caption-mono text-[var(--data-mono)] mt-1">{formatText(item)}</p>
            ))}
            <ReceiptSummary item={lead} />
          </div>
        </div>
      </div>
    </section>
  );
}

function GeneratedFaceplate({ faceplate, selected, onSelect }) {
  const signals = faceplate?.signals || [];
  return (
    <button
      onClick={() => onSelect(faceplate.equipment_id)}
      className={`text-left bg-[var(--surface-panel)] border ${selected ? 'border-[var(--safe)]' : 'border-[var(--border-strong)]'} p-4 hover:bg-[var(--surface-elevated)]`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Generated Faceplate</p>
          <h3 className="text-xl font-bold text-[var(--text)] mt-1">{faceplate.title}</h3>
        </div>
        <div className="flex flex-wrap gap-2 justify-end">
          <span className="industrial-badge text-[var(--data-mono)]">{faceplate.equipment_id}</span>
          <span className="industrial-badge text-[var(--data-mono)]">{faceplate.template_id} v{faceplate.template_version}</span>
        </div>
      </div>
      <p className="caption-mono text-[var(--data-mono)] mt-3">
        source tags: {asList(faceplate.source_tags).join(', ') || 'asset model binding'}
      </p>
      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
        {signals.slice(0, 8).map((signal) => {
          const trust = signalTrustState(signal);
          const reading = signal.reading || {};
          return (
            <div key={signal.tag} className="bg-[var(--surface-base)] p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="font-data text-[var(--text)]">{signal.tag}</p>
                <span className={statusClass(trust.tier)}>{trust.label}</span>
              </div>
              <p className="caption-mono text-[var(--data-mono)] mt-1">
                {reading.value ?? '--'} {reading.unit || signal.unit || ''}
              </p>
              <p className="caption-mono text-[var(--text-muted)] mt-1">{formatText(signal.role || signal.sensor_type)}</p>
            </div>
          );
        })}
      </div>
      <ReceiptSummary item={faceplate} />
    </button>
  );
}

function ScreenReceipts({ manifest, selectedFaceplate }) {
  const receipts = [
    ...(manifest?.screens || []).map((item) => ({ item, title: 'Generated Screen Receipt' })),
    ...(selectedFaceplate ? [{ item: selectedFaceplate, title: 'Selected Faceplate Receipt' }] : []),
    ...(manifest?.situations || []).slice(0, 1).map((item) => ({ item, title: 'Situation Receipt' })),
    ...(manifest?.role_sections || []).slice(0, 2).map((item) => ({ item, title: 'Role Section Receipt' })),
    ...(manifest?.stress_mode_panel ? [{ item: manifest.stress_mode_panel, title: 'Stress-Mode Receipt' }] : []),
  ];

  return (
    <section className="industrial-panel border-t-0">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Screen Receipts</p>
          <h2 className="industrial-panel-title text-base">Generated from template and asset model</h2>
        </div>
      </div>
      <div className="industrial-body space-y-3">
        {receipts.map(({ item, title }) => (
          <GenerationReceipt key={`${title}-${item.generated_id || item.asset_id}`} item={item} title={title} />
        ))}
      </div>
    </section>
  );
}

function RolePanel({ manifest, confidenceDebt }) {
  const rows = manifest?.role_sections || [];
  return (
    <section className="industrial-panel border-t-0">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">{manifest?.role}</p>
          <h2 className="industrial-panel-title text-base">Role View</h2>
        </div>
      </div>
      <div className="industrial-body space-y-[1px] bg-[var(--border-strong)]">
        {rows.map((row) => (
          <div key={row.section} className="bg-[var(--surface-panel)] p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="label-caps text-[var(--text)]">{formatText(row.section)}</p>
              <span className="industrial-badge text-[var(--data-mono)]">{(row.items || []).length} item(s)</span>
            </div>
            {row.section === 'confidence_debt' && confidenceDebt?.length ? confidenceDebt.slice(0, 3).map((item) => (
              <p key={item.sensor_id} className="caption-mono text-[var(--data-mono)] mt-1">
                {item.sensor_id}: {item.priority_language || item.priority || 'confidence debt tracked'}
              </p>
            )) : (
              <p className="caption-mono text-[var(--data-mono)] mt-1">Generated from {manifest?.role} role policy.</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function RuntimeHeader({ manifest, role, plantContext, connected }) {
  return (
    <section className="industrial-panel mb-[1px]">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Compiler Generated Runtime / {role}</p>
          <h1 className="industrial-panel-title">Read-Only Trust-Aware HMI Layer Beside Existing DCS/HMI</h1>
          <p className="caption-mono text-[var(--data-mono)] mt-2">
            build {manifest.build_id} / {manifest.runtime_source === 'published_build' ? 'latest published build' : 'ad hoc unpublished preview'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 justify-end">
          <span className={`industrial-badge ${statusClass(plantContext?.severity || manifest.context)}`}>{formatText(manifest.context)}</span>
          <span className={`industrial-badge ${statusClass(manifest.validation_status)}`}>{manifest.validation_status}</span>
          <span className={`industrial-badge ${connected ? 'status-safe' : 'status-critical'}`}>{connected ? 'LIVE' : 'OFFLINE'}</span>
        </div>
      </div>
    </section>
  );
}

export default function RuntimePlatform() {
  const storeState = useStore();
  const {
    connect,
    connected,
    plantId,
    role,
    plantContext,
    confidence,
    incidents,
    incidentTimeline,
    handoverDebt,
    confidenceDebt,
  } = storeState;
  const [manifest, setManifest] = useState(null);
  const [selected, setSelected] = useState('V-5100');

  useEffect(() => {
    connect();
  }, [connect]);

  useEffect(() => {
    let active = true;
    const load = () => {
      fetch(`/api/screens/generated?role=${role}&context=auto&plant_id=${plantId}`)
        .then((res) => (res.ok ? res.json() : null))
        .then((payload) => {
          if (active) setManifest(payload);
        })
        .catch(() => {
          if (active) setManifest(null);
        });
    };
    load();
    const timer = setInterval(load, 2500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [plantId, role]);

  const faceplates = manifest?.faceplates || [];
  const selectedFaceplate = useMemo(
    () => faceplates.find((item) => item.equipment_id === selected) || faceplates[0],
    [faceplates, selected],
  );
  const situations = useMemo(
    () => (manifest?.situations?.length ? manifest.situations : incidents),
    [manifest, incidents],
  );
  const basisLines = useMemo(() => buildBasisLines(manifest), [manifest]);
  const trustMap = useMemo(
    () => computeTrustMap(manifest, { ...storeState, incidents, handoverDebt }),
    [manifest, storeState, incidents, handoverDebt],
  );
  const stressMode = manifest?.stress_mode || ['WARNING', 'CRITICAL'].includes(String(plantContext?.severity || '').toUpperCase());

  if (!manifest) {
    return (
      <div className="industrial-page p-8">
        <p className="caption-mono text-[var(--data-mono)]">
          Loading published Runtime manifest from compiler build, asset model, and reusable templates...
        </p>
      </div>
    );
  }

  if (stressMode) {
    return (
      <div className="industrial-page grid grid-cols-[340px_1fr] gap-[1px] bg-[var(--border-strong)] overflow-hidden">
        <TrustMapNavigation
          navigation={manifest.navigation}
          faceplates={faceplates}
          selected={selectedFaceplate?.equipment_id || selected}
          onSelect={setSelected}
          trustMap={trustMap}
        />
        <main className="bg-[var(--surface-base)] p-[1px] overflow-y-auto scrollbar-thin">
          <RuntimeHeader manifest={manifest} role={role} plantContext={plantContext} connected={connected} />
          <SituationWorkspace situations={situations} basis={manifest.operating_basis} confidence={confidence} />
          <OperatingBasisLedger basisLines={basisLines} compact />
          <section className="industrial-panel">
            <div className="industrial-panel-header">
              <h2 className="industrial-panel-title text-base">Evidence Timeline</h2>
            </div>
            <div className="industrial-body">
              <IncidentTimeline events={incidentTimeline} compact />
            </div>
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className="industrial-page grid grid-cols-[340px_1fr_390px] gap-[1px] bg-[var(--border-strong)] overflow-hidden">
      <TrustMapNavigation
        navigation={manifest.navigation}
        faceplates={faceplates}
        selected={selectedFaceplate?.equipment_id || selected}
        onSelect={setSelected}
        trustMap={trustMap}
      />
      <main className="bg-[var(--surface-base)] p-[1px] overflow-y-auto scrollbar-thin">
        <RuntimeHeader manifest={manifest} role={role} plantContext={plantContext} connected={connected} />
        <DemoPathStrip />
        <OperatingBasisLedger basisLines={basisLines} />
        <SituationWorkspace situations={situations} basis={manifest.operating_basis} confidence={confidence} />
        <section className="industrial-panel">
          <div className="industrial-panel-header">
            <div>
              <p className="label-caps text-[var(--text-muted)]">Generated From Template</p>
              <h2 className="industrial-panel-title text-base">Generated Faceplates</h2>
            </div>
            <span className="industrial-badge text-[var(--data-mono)]">{faceplates.length}</span>
          </div>
          <div className="industrial-body grid grid-cols-1 xl:grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
            {faceplates.map((faceplate) => (
              <GeneratedFaceplate
                key={faceplate.equipment_id}
                faceplate={faceplate}
                selected={selectedFaceplate?.equipment_id === faceplate.equipment_id}
                onSelect={setSelected}
              />
            ))}
          </div>
        </section>
      </main>
      <aside className="bg-[var(--surface-panel)] overflow-y-auto scrollbar-thin">
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <div>
              <p className="label-caps text-[var(--text-muted)]">Selected Generated Faceplate</p>
              <h2 className="industrial-panel-title text-base">{selectedFaceplate?.title || selected}</h2>
            </div>
          </div>
          <div className="industrial-body">
            {selectedFaceplate ? (
              <GeneratedFaceplate faceplate={selectedFaceplate} selected onSelect={setSelected} />
            ) : (
              <p className="caption-mono text-[var(--data-mono)]">No generated faceplate selected.</p>
            )}
          </div>
        </section>
        <RolePanel manifest={manifest} confidenceDebt={confidenceDebt} />
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">Unresolved Handover Debt</h2>
          </div>
          <div className="industrial-body">
            {(handoverDebt?.entries || []).slice(0, 4).map((item, index) => (
              <p key={`${item.type || 'debt'}-${item.sensor_id || item.incident_id || item.decision_id || index}`} className="caption-mono text-[var(--data-mono)] mb-2">
                {formatText(item.type)}: {item.sensor_id || item.incident_id || item.decision_id || item.description || 'handover required'}
              </p>
            ))}
            {!(handoverDebt?.entries || []).length && (
              <p className="caption-mono status-safe">No unresolved handover debt reported by live Runtime.</p>
            )}
          </div>
        </section>
        <ScreenReceipts manifest={manifest} selectedFaceplate={selectedFaceplate} />
      </aside>
    </div>
  );
}
