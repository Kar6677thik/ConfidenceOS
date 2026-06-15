import { useEffect, useMemo, useState } from 'react';
import useStore from '../store';
import GenerationReceipt, { ReceiptSummary } from './GenerationReceipt';

function statusClass(value) {
  const status = String(value || '').toUpperCase();
  if (status === 'CRITICAL' || status === 'BLOCKING' || status === 'LOW' || status === 'QUARANTINED' || status === 'UNAVAILABLE') return 'status-critical';
  if (status === 'WARNING' || status === 'PASS_WITH_WARNINGS') return 'status-warning';
  if (status === 'MEDIUM' || status === 'CAUTION' || status === 'DEGRADED') return 'status-caution';
  if (status === 'SUBSTITUTED') return 'status-safe';
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
  const tier = signal?.trust_state || confidence.trust_state || confidence.tier || confidence.state || 'HIGH';
  const pct = confidenceValue(confidence);
  // Trust STATE is the primary label; % score is secondary detail (demoted)
  return {
    tier,
    pct,
    label: formatText(tier),
    detail: pct == null ? null : `${pct}%`,
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
  const steps = [
    { label: 'Studio', desc: 'Import tags → map → build' },
    { label: 'Publish', desc: 'Compiler validates; guardrails pass' },
    { label: 'Runtime', desc: 'Trust map + operating basis', active: true },
    { label: 'Abnormal Situation', desc: 'Alarm collapse → single safe move' },
    { label: 'Role Switch', desc: 'Operator / Maintenance / Engineer / Manager' },
    { label: 'Shift Channel', desc: 'Handover debt carried forward' },
  ];
  return (
    <section className="industrial-panel mb-[1px]">
      <div className="industrial-body">
        <p className="label-caps text-[var(--text-muted)] mb-2">Primary Demo Path — HMI Compiler for Trust-Aware Interfaces</p>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
          {steps.map((step, index) => (
            <div key={step.label} className={`p-3 min-h-[72px] ${step.active ? 'bg-[var(--surface-raised)]' : 'bg-[var(--surface-panel)]'}`}>
              <p className="label-caps text-[var(--text-muted)]">Step {index + 1}</p>
              <p className={`caption-mono mt-1 font-semibold ${step.active ? 'status-safe' : 'text-[var(--text)]'}`}>{step.label}</p>
              <p className="label-caps text-[var(--text-muted)] mt-1">{step.desc}</p>
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
  if (situation?.decision_time_score) return situation.decision_time_score;
  const affected = asList(situation?.affected_sensors);
  const scores = (confidence || [])
    .filter((item) => affected.includes(item.sensor_id))
    .map((item) => Number(item.confidence_pct))
    .filter(Number.isFinite);
  const rawSignalCount = affected.length || 1;
  const blockedDecisionCount = asList(situation?.action_contract?.blocked_decisions || situation?.blocked_decisions).length;
  const evidenceCategoryCount = asList(situation?.evidence_refs || situation?.evidence).length;
  const requiredOperatorActionCount = asList(situation?.action_contract?.first_safe_action || situation?.first_action).length || 1;
  const collapsedSituationCount = situation?.title ? 1 : 0;
  const traditionalSteps = rawSignalCount + blockedDecisionCount + evidenceCategoryCount;
  const confidenceosSteps = collapsedSituationCount + requiredOperatorActionCount;
  const score = scores.length
    ? Math.round(scores.reduce((sum, item) => sum + item, 0) / scores.length)
    : situation?.severity === 'critical' ? 35 : 72;
  return {
    metric_label: 'Interaction Compression Estimate',
    score,
    raw_signal_count: rawSignalCount,
    suppressed_alarm_count: Math.max(0, rawSignalCount - collapsedSituationCount),
    collapsed_situation_count: collapsedSituationCount,
    blocked_decision_count: blockedDecisionCount,
    required_operator_action_count: requiredOperatorActionCount,
    traditional_steps: Math.max(1, traditionalSteps),
    confidenceos_steps: Math.max(1, confidenceosSteps),
    decision_compression: `${Math.max(1, traditionalSteps)} -> ${Math.max(1, confidenceosSteps)}`,
    required_operator_actions: requiredOperatorActionCount,
    method: 'Estimated from active raw signals, collapsed situations, blocked decisions, and required operator actions.',
  };
}

function SituationWorkspace({ situations, basis, confidence }) {
  const lead = situations?.[0] || {};
  const contract = lead.action_contract || {};
  const collapse = lead.alarm_collapse_receipt || basis?.alarm_collapse_receipt || lead.alarm_collapse || {};
  const score = decisionTimeScore(lead, confidence);
  const rows = [
    ['Do Not Trust', contract.do_not_use || basis?.do_not_trust, 'status-critical'],
    ['Trusted Substitute', contract.trusted_substitutes || basis?.trusted_substitutes, 'status-safe'],
    ['Operator Single Safe Move', contract.operator_single_safe_move || basis?.operator_single_safe_move || contract.first_safe_action || basis?.first_safe_action, 'status-safe'],
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
          <p className="label-caps text-[var(--text-muted)]">{score.metric_label || 'Interaction Compression Estimate'}</p>
          <p className={`text-2xl font-bold ${statusClass(score.score < 50 ? 'CRITICAL' : score.score < 75 ? 'WARNING' : 'SAFE')}`}>{score.decision_compression}</p>
          <p className="caption-mono text-[var(--data-mono)] mt-1">{score.required_operator_actions ?? score.required_operator_action_count ?? 1} required operator action</p>
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
              {(collapse.raw_signal_count || collapse.collapsed) ? `Collapsed from ${collapse.raw_signal_count || collapse.consumed_alarm_types?.length || 0} raw signals; suppressed ${collapse.suppressed_alarm_count ?? 0}.` : 'No alarm collapse active.'}
            </p>
            <p className="caption-mono text-[var(--text)] mt-2">{collapse.operator_question}</p>
            <p className="caption-mono text-[var(--data-mono)] mt-1">{collapse.collapse_reason}</p>
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
                <div className="flex items-center gap-1">
                  {/* Trust STATE is primary — % score is secondary detail */}
                  <span className={`label-caps font-semibold ${statusClass(trust.tier)}`}>{trust.label}</span>
                  {trust.detail && <span className="label-caps text-[var(--text-muted)]">({trust.detail})</span>}
                </div>
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

function StressField({ label, value, status = 'text-[var(--data-mono)]' }) {
  const values = asList(value);
  return (
    <div className="border border-[var(--border-strong)] bg-[var(--surface-panel)] p-4">
      <p className={`label-caps ${status}`}>{label}</p>
      {values.length ? values.slice(0, 5).map((item) => (
        <p key={typeof item === 'string' ? item : JSON.stringify(item)} className="caption-mono text-[var(--text)] mt-2">
          {typeof item === 'string' ? formatText(item) : formatText(item?.message || item?.sensor_id || item?.source || item?.category)}
        </p>
      )) : <p className="caption-mono text-[var(--data-mono)] mt-2">Not active</p>}
    </div>
  );
}

function PressureModeRuntime({ manifest, situations, confidence }) {
  const lead = situations?.[0] || {};
  const basis = manifest.operating_basis || {};
  const contract = lead.action_contract || {};
  const collapse = lead.alarm_collapse_receipt || basis.alarm_collapse_receipt || lead.alarm_collapse || {};
  const score = lead.decision_time_score || basis.decision_time_score || decisionTimeScore(lead, confidence);
  const singleMove = contract.operator_single_safe_move || basis.operator_single_safe_move || contract.first_safe_action || basis.first_safe_action;

  return (
    <div className="industrial-page bg-[var(--surface-base)] overflow-y-auto scrollbar-thin">
      <main className="max-w-6xl mx-auto p-[1px]">
        <section className="industrial-panel mb-[1px]">
          <div className="industrial-panel-header">
            <div>
              <p className="label-caps status-warning">Pressure-Mode Runtime</p>
              <h1 className="industrial-panel-title">{lead.title || basis.abnormal_situation || 'Abnormal situation active'}</h1>
            </div>
            <span className={`industrial-badge ${statusClass(manifest.context)}`}>{formatText(manifest.context)}</span>
          </div>
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
          <StressField label="Abnormal Situation" value={lead.title || basis.abnormal_situation} status="status-warning" />
          <StressField label="Operator Single Safe Move" value={singleMove} status="status-safe" />
          <StressField label="Do Not Trust" value={contract.do_not_use || basis.do_not_trust} status="status-critical" />
          <StressField label="Trusted Substitute" value={contract.trusted_substitutes || basis.trusted_substitutes} status="status-safe" />
          <StressField label="Decision Freeze" value={contract.blocked_decisions || basis.decision_freeze} status="status-warning" />
          <StressField label="Exit Condition" value={contract.exit_conditions || basis.exit_condition} />
        </div>

        <section className="industrial-panel mt-[1px]">
          <div className="industrial-body grid grid-cols-1 lg:grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
            <div className="bg-[var(--surface-panel)] p-4">
              <p className="label-caps text-[var(--text-muted)]">Alarm Collapse Receipt</p>
              <p className="caption-mono text-[var(--text)] mt-2">
                Raw signals: {collapse.raw_signal_count ?? 0} / suppressed alarms: {collapse.suppressed_alarm_count ?? 0}
              </p>
              <p className="caption-mono text-[var(--text)] mt-2">{collapse.operator_question || 'Can the operator trust level before increasing feed?'}</p>
              <p className="caption-mono text-[var(--data-mono)] mt-1">{collapse.collapse_reason || 'All signals affect the same operating basis.'}</p>
              <p className="caption-mono text-[var(--data-mono)] mt-2">
                {asList(collapse.raw_signals).join(', ') || 'No raw signals reported.'}
              </p>
            </div>
            <div className="bg-[var(--surface-panel)] p-4">
              <p className="label-caps text-[var(--text-muted)]">{score.metric_label || 'Interaction Compression Estimate'}</p>
              <p className={`text-4xl font-bold mt-2 ${statusClass(score.score < 50 ? 'CRITICAL' : score.score < 75 ? 'WARNING' : 'SAFE')}`}>
                {score.decision_compression || '6 -> 2'}
              </p>
              <p className="caption-mono text-[var(--data-mono)] mt-2">
                Traditional steps: {score.traditional_steps ?? 6} / ConfidenceOS steps: {score.confidenceos_steps ?? 2}
              </p>
              <p className="caption-mono text-[var(--text)] mt-2">
                Required operator actions: {score.required_operator_actions ?? 1}
              </p>
              <p className="caption-mono text-[var(--data-mono)] mt-1">
                raw {score.raw_signal_count ?? 0} / suppressed {score.suppressed_alarm_count ?? 0} / blocked decisions {score.blocked_decision_count ?? 0}
              </p>
              <p className="caption-mono text-[var(--text-muted)] mt-1">
                {score.method || 'Estimated interaction compression, not measured decision time.'}
              </p>
            </div>
          </div>
        </section>

        <section className="border border-[var(--border-strong)] bg-[var(--surface-panel)] p-4 mt-[1px]">
          <p className="label-caps status-warning">Grounded Operator Explanation Disabled</p>
          <p className="caption-mono text-[var(--text)] mt-2">
            Grounded explanation disabled during active decision freeze. Use operating-basis workflow.
          </p>
        </section>
      </main>
    </div>
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

function sectionItems(sections, name) {
  return (sections || []).find((row) => row.section === name)?.items || [];
}

function ValueList({ values, empty = 'Not active', status = 'text-[var(--data-mono)]' }) {
  const rows = asList(values);
  if (!rows.length) return <p className="caption-mono text-[var(--data-mono)] mt-2">{empty}</p>;
  return rows.slice(0, 6).map((item, index) => (
    <p key={`${typeof item === 'string' ? item : item?.id || item?.sensor_id || item?.task_id || index}`} className={`caption-mono mt-2 ${status}`}>
      {typeof item === 'string'
        ? formatText(item)
        : formatText(item?.title || item?.required_action || item?.message || item?.sensor_id || item?.state || item?.assumption_id)}
    </p>
  ));
}

function WorkspacePanel({ title, children, badge }) {
  return (
    <div className="bg-[var(--surface-panel)] p-3">
      <div className="flex items-center justify-between gap-3">
        <p className="label-caps text-[var(--text)]">{title}</p>
        {badge && <span className="industrial-badge text-[var(--data-mono)]">{badge}</span>}
      </div>
      {children}
    </div>
  );
}

function AuditTrailTimeline({ events }) {
  return (
    <div className="mt-3 border border-[var(--border-strong)] bg-[var(--surface-panel)] p-3">
      <p className="label-caps text-[var(--text-muted)] mb-2">Immutable Audit Trail</p>
      <div className="space-y-[1px] bg-[var(--border-strong)]">
        {events.map((event) => (
          <div key={event.id} className="bg-[var(--surface-base)] p-2">
            <div className="flex items-center justify-between gap-2">
              <span className="caption-mono text-[var(--text)]">
                {event.from_state ? `${event.from_state} → ` : ''}{event.to_state}
              </span>
              <span className="label-caps text-[var(--text-muted)]">
                {event.actor || 'system'}{event.actor_role ? ` · ${event.actor_role}` : ''}
              </span>
            </div>
            {event.evidence_note && <p className="caption-mono text-[var(--data-mono)] mt-1">{event.evidence_note}</p>}
            <p className="label-caps text-[var(--text-muted)] mt-1">{event.created_at}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// Legal verification transitions (mirrors backend VERIFICATION_TRANSITIONS).
const LEGAL_NEXT = {
  REQUESTED: ['ASSIGNED', 'EXPIRED'],
  ASSIGNED: ['FIELD_CHECK_DONE', 'EXPIRED'],
  FIELD_CHECK_DONE: ['ACCEPTED', 'REJECTED', 'EXPIRED'],
  REJECTED: ['ASSIGNED', 'EXPIRED'],
  ACCEPTED: [],
  EXPIRED: [],
};
const EVIDENCE_REQUIRED_STATES = new Set(['FIELD_CHECK_DONE', 'ACCEPTED', 'REJECTED']);
const STATE_LABEL = {
  ASSIGNED: 'Assign to me',
  FIELD_CHECK_DONE: 'Field Check Done',
  ACCEPTED: 'Accept Field Check',
  REJECTED: 'Reject / Reopen Required',
  EXPIRED: 'Expire',
};
const ROLE_TRANSITIONS = {
  Maintenance: new Set(['ASSIGNED', 'FIELD_CHECK_DONE', 'EXPIRED']),
  Engineer: new Set(['ASSIGNED', 'ACCEPTED', 'REJECTED', 'EXPIRED']),
  Manager: new Set(['ASSIGNED', 'ACCEPTED', 'REJECTED', 'EXPIRED']),
};

function legalTransitionsForRole(state, role) {
  const allowedForState = LEGAL_NEXT[state] || [];
  const allowedForRole = ROLE_TRANSITIONS[role] || new Set();
  return allowedForState.filter((item) => allowedForRole.has(item));
}

function RoleWorkspace({ manifest, confidenceDebt, handoverDebt, verificationTasks }) {
  const sections = manifest?.role_sections || [];
  const role = manifest?.role || 'Operator';
  const basis = manifest?.operating_basis || {};
  const { plantId } = useStore();
  const [taskNote, setTaskNote] = useState('');
  const [taskBusy, setTaskBusy] = useState('');
  const [taskMessage, setTaskMessage] = useState('');
  const [auditTrail, setAuditTrail] = useState({ taskId: null, events: [] });

  const updateTask = async (task, state) => {
    const taskId = task.task_id || task.token_id;
    if (!taskId) return;
    // Client-side guard mirrors the backend so the operator gets immediate feedback.
    if (EVIDENCE_REQUIRED_STATES.has(state) && !taskNote.trim()) {
      setTaskMessage(`An evidence note is required to move this task to ${state}.`);
      return;
    }
    setTaskBusy(`${taskId}:${state}`);
    setTaskMessage('');
    try {
      const res = await fetch(`/api/verification-tasks/state?plant_id=${plantId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: taskId,
          state,
          actor: role,            // client-supplied identity (no real auth yet)
          actor_role: role,
          accepted_by: state === 'ACCEPTED' ? role : null,
          evidence_note: taskNote,
          note: taskNote,
        }),
      });
      const payload = await res.json().catch(() => null);
      if (!res.ok) throw new Error(payload?.detail || `Request failed: ${res.status}`);
      setTaskMessage(`${task.sensor_id || taskId} moved to ${state} by ${role}.`);
      if (auditTrail.taskId === taskId) loadAudit(taskId);
    } catch (err) {
      setTaskMessage(err.message || 'Task update failed.');
    } finally {
      setTaskBusy('');
    }
  };

  const loadAudit = async (taskId) => {
    try {
      const url = taskId
        ? `/api/verification-tasks/audit?plant_id=${plantId}&task_id=${encodeURIComponent(taskId)}`
        : `/api/verification-tasks/audit?plant_id=${plantId}`;
      const res = await fetch(url);
      const payload = await res.json().catch(() => null);
      if (res.ok && payload) setAuditTrail({ taskId: taskId || null, events: payload.events || [] });
    } catch {
      /* non-fatal: audit view is supplementary */
    }
  };

  let content;
  if (role === 'Maintenance') {
    const tasks = sectionItems(sections, 'verification_task').length
      ? sectionItems(sections, 'verification_task')
      : (verificationTasks || []);
    content = (
      <>
        <WorkspacePanel title="Verification Task" badge={`${tasks.length} task(s)`}>
          <p className="caption-mono text-[var(--text-muted)] mb-2">
            Role-scoped actions; actor identity client-supplied; immutable audit trail. ConfidenceOS never writes process controls.
          </p>
          {tasks.length ? tasks.slice(0, 4).map((task) => {
            const legal = legalTransitionsForRole(task.state, role);
            const owner = task.field_checked_by || task.assigned_to || task.accepted_by;
            return (
              <div key={task.task_id || task.token_id} className="border border-[var(--border-strong)] bg-[var(--surface-base)] p-3 mt-2">
                <div className="flex items-center justify-between gap-3">
                  <p className="caption-mono status-warning">{task.sensor_id}</p>
                  <span className="industrial-badge status-warning">{task.state}</span>
                </div>
                <p className="caption-mono text-[var(--data-mono)] mt-1">{formatText(task.verification_method)}</p>
                <p className="caption-mono text-[var(--text)] mt-1">{asList(task.evidence_required).join(' / ')}</p>
                {owner && (
                  <p className="label-caps text-[var(--text-muted)] mt-1">
                    {task.accepted_by ? `accepted by ${task.accepted_by}` : task.field_checked_by ? `field-checked by ${task.field_checked_by}` : `assigned to ${task.assigned_to}`}
                  </p>
                )}
                {legal.length ? (
                  <div className="mt-3 grid grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
                    {legal.map((state) => (
                      <button
                        key={state}
                        disabled={!!taskBusy}
                        onClick={() => updateTask(task, state)}
                        className="industrial-control bg-[var(--surface-panel)] disabled:opacity-40"
                      >
                        {STATE_LABEL[state] || formatText(state)}
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="caption-mono status-safe mt-2">Terminal state — no further action.</p>
                )}
                <button
                  onClick={() => loadAudit(task.task_id || task.token_id)}
                  className="industrial-control bg-transparent text-[var(--text-muted)] mt-2 w-full"
                >
                  View audit trail
                </button>
              </div>
            );
          }) : <ValueList values={[]} empty="No active field verification task." />}
          <input
            value={taskNote}
            onChange={(event) => setTaskNote(event.target.value)}
            className="industrial-input mt-3"
            placeholder="Evidence note (required for Field Check Done / Accept)"
          />
          {taskMessage && <p className="caption-mono text-[var(--data-mono)] mt-2">{taskMessage}</p>}
          {auditTrail.events.length > 0 && <AuditTrailTimeline events={auditTrail.events} />}
        </WorkspacePanel>
        <WorkspacePanel title="Calibration Context">
          <ValueList values={sectionItems(sections, 'calibration_context').map((item) => `${item.sensor_id}: ${item.calibration_status} - ${item.calibration_message}`)} />
        </WorkspacePanel>
        <WorkspacePanel title="Device Health">
          <ValueList values={sectionItems(sections, 'device_health').map((item) => `${item.sensor_id}: ${item.trust_state} / ${item.confidence_pct ?? '--'}%`)} />
        </WorkspacePanel>
        <WorkspacePanel title="Confidence Debt">
          <ValueList values={(confidenceDebt || sectionItems(sections, 'confidence_debt')).map((item) => item.maintenance_priority || item.priority_language || `${item.sensor_id}: confidence debt ${item.confidence_debt ?? 0}`)} />
        </WorkspacePanel>
        <WorkspacePanel title="Field Check Status">
          <ValueList values={sectionItems(sections, 'field_check_status').map((item) => `${item.sensor_id}: ${item.state || 'not requested'} / ${item.confidence_tier || 'unknown confidence'}`)} />
        </WorkspacePanel>
      </>
    );
  } else if (role === 'Engineer') {
    const provenance = sectionItems(sections, 'build_publish_provenance')[0] || {};
    const reviewTasks = (verificationTasks || []).filter((task) => ['FIELD_CHECK_DONE', 'REJECTED', 'ASSIGNED'].includes(task.state));
    content = (
      <>
        <WorkspacePanel title="Verification Review" badge={`${reviewTasks.length} task(s)`}>
          <p className="caption-mono text-[var(--text-muted)] mb-2">
            Engineer/Manager acceptance is separate from Maintenance field check. Evidence note required for accept or reject.
          </p>
          {reviewTasks.length ? reviewTasks.slice(0, 4).map((task) => {
            const legal = legalTransitionsForRole(task.state, role);
            return (
              <div key={task.task_id || task.token_id} className="border border-[var(--border-strong)] bg-[var(--surface-base)] p-3 mt-2">
                <div className="flex items-center justify-between gap-3">
                  <p className="caption-mono status-warning">{task.sensor_id}</p>
                  <span className="industrial-badge status-warning">{task.state}</span>
                </div>
                <p className="caption-mono text-[var(--data-mono)] mt-1">{task.last_evidence_summary || task.note || 'Awaiting structured field evidence.'}</p>
                <div className="mt-3 grid grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
                  {legal.map((state) => (
                    <button
                      key={state}
                      disabled={!!taskBusy}
                      onClick={() => updateTask(task, state)}
                      className="industrial-control bg-[var(--surface-panel)] disabled:opacity-40"
                    >
                      {STATE_LABEL[state] || formatText(state)}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => loadAudit(task.task_id || task.token_id)}
                  className="industrial-control bg-transparent text-[var(--text-muted)] mt-2 w-full"
                >
                  View audit trail
                </button>
              </div>
            );
          }) : <ValueList values={[]} empty="No verification tasks awaiting engineer review." />}
          <input
            value={taskNote}
            onChange={(event) => setTaskNote(event.target.value)}
            className="industrial-input mt-3"
            placeholder="Engineer evidence note for acceptance/rejection"
          />
          {taskMessage && <p className="caption-mono text-[var(--data-mono)] mt-2">{taskMessage}</p>}
          {auditTrail.events.length > 0 && <AuditTrailTimeline events={auditTrail.events} />}
        </WorkspacePanel>
        <WorkspacePanel title="Signal Binding" badge={`${sectionItems(sections, 'signal_mapping').length} signal(s)`}>
          <ValueList values={sectionItems(sections, 'signal_mapping').map((item) => `${item.tag}: ${item.role || item.sensor_type} -> ${item.equipment_id}`)} />
        </WorkspacePanel>
        <WorkspacePanel title="Template Receipt">
          <ValueList values={sectionItems(sections, 'template_receipt').map((item) => item.message || item.receipt || item.generated_id || item.rule || item.status)} empty="No compiler receipt rows attached." />
        </WorkspacePanel>
        <WorkspacePanel title="Assumptions Used">
          <ValueList values={sectionItems(sections, 'assumptions_used').map((item) => `${item.assumption_id}: ${item.value?.value ?? item.value} ${item.unit || ''}`)} />
        </WorkspacePanel>
        <WorkspacePanel title="Score Sensitivity">
          <ValueList values={sectionItems(sections, 'score_sensitivity').flatMap((item) => item.scenarios || []).map((item) => `${item.label}: ${item.confidence_pct}% (${item.delta_pct >= 0 ? '+' : ''}${item.delta_pct})`)} />
        </WorkspacePanel>
        <WorkspacePanel title="Engineer-Owned Confidence Thresholds">
          <p className="caption-mono text-[var(--text-muted)] mb-2">These weights are engineering choices, not physics. They reflect relative importance of each sub-check for this asset model. Changing them requires a new compiler build and engineer sign-off.</p>
          <ValueList values={[
            'calibration weight: 0.30 — How recently the sensor was checked against a reference',
            'stability weight: 0.20 — Whether the reading has been stable (not stuck or oscillating)',
            'cross-sensor weight: 0.30 — Consistency with related sensors via mass balance',
            'range plausibility weight: 0.20 — Whether the reading is within the physical operating envelope',
            'HIGH band: ≥ 80 — TRUSTED; MEDIUM band: ≥ 50 — DEGRADED; LOW band: ≥ 20 — QUARANTINE candidate; CRITICAL: < 20 — QUARANTINED',
            'Verdict is robust: changing any single weight by ±10 pp does not change the trust state tier for most sensors',
          ]} />
        </WorkspacePanel>
        <WorkspacePanel title="Validation Warnings">
          <ValueList values={sectionItems(sections, 'validation_warnings').map((item) => item.message || item.rule)} empty="No validation warnings on current build." status="status-warning" />
        </WorkspacePanel>
        <WorkspacePanel title="Build / Publish Provenance" badge={provenance.validation_status}>
          <ValueList values={[
            `build id: ${provenance.build_id || manifest.build_id}`,
            `published build id: ${provenance.published_build_id || manifest.published_build_id || 'not published'}`,
            `runtime source: ${provenance.runtime_source || manifest.runtime_source}`,
          ]} />
        </WorkspacePanel>
      </>
    );
  } else if (role === 'Manager' || role === 'Auditor') {
    const acceptance = sectionItems(sections, 'handover_acceptance')[0] || {
      state: handoverDebt?.handover_acceptance || 'unblocked',
      blocking_items: handoverDebt?.count || 0,
    };
    const reviewTasks = (verificationTasks || []).filter((task) => task.handover_required || ['FIELD_CHECK_DONE', 'REJECTED', 'ASSIGNED'].includes(task.state));
    content = (
      <>
        <WorkspacePanel title="Unresolved Handover Debt" badge={`${sectionItems(sections, 'unresolved_handover_debt').length || handoverDebt?.count || 0}`}>
          <ValueList values={sectionItems(sections, 'unresolved_handover_debt').length ? sectionItems(sections, 'unresolved_handover_debt') : handoverDebt?.entries || []} empty="No unresolved handover debt." />
        </WorkspacePanel>
        <WorkspacePanel title="Decision Freeze State">
          <ValueList values={sectionItems(sections, 'decision_freeze_state').map((item) => `${item.decision}: ${item.status}`)} />
        </WorkspacePanel>
        <WorkspacePanel title="Handover Acceptance" badge={acceptance.state}>
          <p className={`caption-mono mt-2 ${acceptance.blocked ? 'status-critical' : 'status-safe'}`}>
            {acceptance.blocked ? `Blocked by ${acceptance.blocking_items} item(s).` : 'Unblocked.'}
          </p>
          <ValueList
            values={(handoverDebt?.entries || [])
              .filter((item) => item.type === 'active_verification_token' || item.task_type === 'active_verification_task')
              .map((item) => `${item.title} clears when ${item.sensor_id || 'field verification'} is ACCEPTED or EXPIRED`)}
            empty="No verification task is blocking handover acceptance."
            status="status-warning"
          />
        </WorkspacePanel>
        <WorkspacePanel title="Verification Acceptance Gate" badge={`${reviewTasks.length} task(s)`}>
          <p className="caption-mono text-[var(--text-muted)] mb-2">
            Manager can accept or reject completed field evidence; Auditor view is read-only. Handover remains blocked while required verification is unresolved.
          </p>
          {reviewTasks.length ? reviewTasks.slice(0, 5).map((task) => {
            const legal = legalTransitionsForRole(task.state, role);
            return (
              <div key={task.task_id || task.token_id} className="border border-[var(--border-strong)] bg-[var(--surface-base)] p-3 mt-2">
                <div className="flex items-center justify-between gap-3">
                  <p className="caption-mono status-warning">{task.sensor_id}</p>
                  <span className="industrial-badge status-warning">{task.state}</span>
                </div>
                <p className="caption-mono text-[var(--data-mono)] mt-1">
                  {task.last_evidence_summary || task.note || 'No field evidence accepted yet.'}
                </p>
                <p className="label-caps text-[var(--text-muted)] mt-1">
                  clears handover when ACCEPTED or EXPIRED
                </p>
                {legal.length ? (
                  <div className="mt-3 grid grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
                    {legal.map((state) => (
                      <button
                        key={state}
                        disabled={!!taskBusy}
                        onClick={() => updateTask(task, state)}
                        className="industrial-control bg-[var(--surface-panel)] disabled:opacity-40"
                      >
                        {STATE_LABEL[state] || formatText(state)}
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="caption-mono text-[var(--text-muted)] mt-2">
                    {role === 'Auditor' ? 'Read-only audit role.' : 'No legal transition from this state.'}
                  </p>
                )}
                <button
                  onClick={() => loadAudit(task.task_id || task.token_id)}
                  className="industrial-control bg-transparent text-[var(--text-muted)] mt-2 w-full"
                >
                  View audit trail
                </button>
              </div>
            );
          }) : <ValueList values={[]} empty="No verification task is blocking handover acceptance." />}
          {role === 'Manager' && (
            <input
              value={taskNote}
              onChange={(event) => setTaskNote(event.target.value)}
              className="industrial-input mt-3"
              placeholder="Manager acceptance/rejection evidence note"
            />
          )}
          {taskMessage && <p className="caption-mono text-[var(--data-mono)] mt-2">{taskMessage}</p>}
        </WorkspacePanel>
        <WorkspacePanel title="Timeline Evidence">
          <ValueList values={sectionItems(sections, 'timeline_evidence').map((item) => item.message)} />
        </WorkspacePanel>
        <WorkspacePanel title="Verification Audit Trail" badge={`${auditTrail.events.length} event(s)`}>
          <p className="caption-mono text-[var(--text-muted)] mb-2">
            Immutable, time-ordered record of every field-verification state change (who, role, evidence, when). Actor identity is client-supplied; real RBAC is future work.
          </p>
          <button onClick={() => loadAudit(null)} className="industrial-control bg-[var(--surface-panel)] w-full">
            Load plant verification audit trail
          </button>
          {auditTrail.events.length > 0
            ? <AuditTrailTimeline events={auditTrail.events} />
            : <p className="caption-mono text-[var(--data-mono)] mt-2">No audit events loaded yet.</p>}
        </WorkspacePanel>
        <WorkspacePanel title="Published Build ID">
          <ValueList values={sectionItems(sections, 'published_build_id').map((item) => item.build_id)} />
        </WorkspacePanel>
      </>
    );
  } else {
    content = (
      <>
        <WorkspacePanel title="Single Safe Move">
          <ValueList values={sectionItems(sections, 'single_safe_move').length ? sectionItems(sections, 'single_safe_move') : basis.operator_single_safe_move} status="status-safe" />
        </WorkspacePanel>
        <WorkspacePanel title="Operating Basis">
          <ValueList values={[basis.abnormal_situation]} />
        </WorkspacePanel>
        <WorkspacePanel title="Do-Not-Trust">
          <ValueList values={sectionItems(sections, 'do_not_trust').length ? sectionItems(sections, 'do_not_trust') : basis.do_not_trust} status="status-critical" />
        </WorkspacePanel>
        <WorkspacePanel title="Trusted Substitute">
          <ValueList values={sectionItems(sections, 'trusted_substitute').length ? sectionItems(sections, 'trusted_substitute') : basis.trusted_substitutes} status="status-safe" />
        </WorkspacePanel>
        <WorkspacePanel title="Decision Freeze">
          <ValueList values={sectionItems(sections, 'decision_freeze').length ? sectionItems(sections, 'decision_freeze') : basis.decision_freeze} status="status-warning" />
        </WorkspacePanel>
        <WorkspacePanel title="Exit Condition">
          <ValueList values={sectionItems(sections, 'exit_condition').length ? sectionItems(sections, 'exit_condition') : basis.exit_condition} />
        </WorkspacePanel>
      </>
    );
  }

  return (
    <section className="industrial-panel border-t-0">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">{role}</p>
          <h2 className="industrial-panel-title text-base">Operational Role Workspace</h2>
        </div>
      </div>
      <div className="industrial-body space-y-[1px] bg-[var(--border-strong)]">
        {content}
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
          <p className="caption-mono text-[var(--text-muted)] mt-1">
            Trust state is a governed deterministic rubric, not a probability of correctness.
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
    handoverDebt,
    confidenceDebt,
    verificationTasks,
  } = storeState;
  const [manifest, setManifest] = useState(null);
  const [selected, setSelected] = useState('');

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
  const pressureContext = manifest?.stress_mode
    || ['WARNING', 'CRITICAL'].includes(String(plantContext?.severity || '').toUpperCase())
    || ['WARNING', 'CRITICAL', 'MASS_BALANCE_DIVERGENCE', 'MANUAL_VERIFICATION_REQUIRED'].includes(String(manifest?.context || '').toUpperCase());
  const stressMode = role === 'Operator' && pressureContext;

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
    return <PressureModeRuntime manifest={manifest} situations={situations} confidence={confidence} />;
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
        <RoleWorkspace manifest={manifest} confidenceDebt={confidenceDebt} handoverDebt={handoverDebt} verificationTasks={verificationTasks} />
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
