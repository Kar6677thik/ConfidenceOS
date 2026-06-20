import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import useStore from '../store';
import PriorityBand from './hmi/PriorityBand';
import MassBalanceChart from './MassBalanceChart';
import ComparisonPanel from './ComparisonPanel';
import apiFetch from '../lib/apiFetch';

function formatText(value) {
  if (value == null || value === '') return '';
  if (Array.isArray(value)) return value.map(formatText).filter(Boolean).join(' / ');
  if (String(value).toUpperCase() === 'NO_LIVE_SAMPLE') return 'Metadata Only';
  if (typeof value === 'object') {
    const candidate = value.message
      || value.title
      || value.description
      || value.statement
      || value.sensor_id
      || value.decision_id
      || value.tag
      || value.type;
    if (candidate) return formatText(candidate);
    return Object.entries(value)
      .filter(([, item]) => item != null && typeof item !== 'object')
      .map(([key, item]) => `${formatText(key)}: ${item}`)
      .join(' / ');
  }
  return String(value)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function displayText(value) {
  if (value == null || value === '') return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return formatText(value);
  }
  if (Array.isArray(value)) {
    return value.map(displayText).filter(Boolean).join(' / ');
  }
  if (typeof value === 'object') {
    return displayText(
      value.message
      || value.title
      || value.description
      || value.statement
      || value.sensor_id
      || value.decision_id
      || value.type
      || Object.entries(value)
        .filter(([, item]) => item != null && typeof item !== 'object')
        .map(([key, item]) => `${formatText(key)}: ${item}`)
        .join(' / '),
    );
  }
  return String(value);
}

function signalDisplayValue(signal, { includeUnit = true } = {}) {
  const trust = signalTrustState(signal);
  const rawValue = signal?.value;
  const unavailable = ['METADATA_ONLY', 'NO_LIVE_SAMPLE', 'UNAVAILABLE'].includes(trust.tier);
  if (rawValue == null || rawValue === '--' || typeof rawValue === 'object' || unavailable) {
    if (trust.tier === 'UNAVAILABLE') return 'provider unavailable';
    if (trust.tier === 'NO_LIVE_SAMPLE') return 'sample pending';
    return 'metadata binding';
  }
  const numeric = Number(rawValue);
  const formatted = Number.isFinite(numeric) ? numeric.toFixed(Math.abs(numeric) >= 100 ? 0 : 1) : String(rawValue);
  return `${formatted}${includeUnit && signal?.unit ? ` ${signal.unit}` : ''}`;
}

function signalSourceNote(signal) {
  const trust = signalTrustState(signal);
  if (trust.tier === 'UNAVAILABLE') return 'Live provider reported unavailable.';
  if (trust.tier === 'NO_LIVE_SAMPLE') return 'Awaiting the next live provider sample.';
  if (trust.tier === 'METADATA_ONLY') return 'Configured from asset model; no live provider sample is bound yet.';
  if (trust.tier === 'NO_CONFIDENCE_RESULT') return 'Live value present; confidence calculation is pending.';
  return trust.pct != null ? `${formatText(trust.tier)} trust / ${trust.pct}%` : `${formatText(trust.tier)} trust`;
}

function asList(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  if (value == null || value === '') return [];
  return [value];
}

function statusClass(value) {
  const status = String(value || '').toUpperCase();
  if (['CRITICAL', 'BLOCKING', 'LOW', 'QUARANTINED', 'UNAVAILABLE', 'FAILED'].includes(status)) return 'status-critical';
  if (['WARNING', 'PASS_WITH_WARNINGS', 'PUBLISHED_WITH_WARNINGS', 'DEGRADED', 'MEDIUM', 'NOT_PUBLISHED', 'NO_CONFIDENCE_RESULT'].includes(status)) return 'status-warning';
  if (['SUBSTITUTED', 'TRUSTED', 'HIGH', 'PASS', 'PUBLISHED'].includes(status)) return 'status-safe';
  if (['METADATA_ONLY', 'NO_LIVE_SAMPLE', 'NOT_BOUND', 'RUNTIME_FALLBACK'].includes(status)) return 'text-[var(--data-mono)]';
  return 'text-[var(--text-muted)]';
}

function runtimeStatusLabel(value) {
  const status = String(value || '').toUpperCase();
  if (status === 'NOT_PUBLISHED') return 'Publish preview';
  if (status === 'PUBLISHED_WITH_WARNINGS') return 'Published with warnings';
  if (status === 'PUBLISHED') return 'Published Runtime';
  if (status === 'PASS_WITH_WARNINGS') return 'Build passed with warnings';
  if (status === 'PASS') return 'Build passed';
  if (status === 'FAILED') return 'Build blocked';
  return formatText(value || 'Runtime live');
}

function normalizeRole(role) {
  return String(role || 'Operator').trim().toLowerCase();
}

function isOperatorRole(role) {
  return normalizeRole(role) === 'operator';
}

function showEngineeringInternals(role) {
  return !isOperatorRole(role);
}

function operatorRuntimeLabel(manifest, connected) {
  if (!connected) return 'Offline';
  const publishState = String(manifest?.runtime_publish_state || manifest?.validation_status || '').toUpperCase();
  const bindingState = String(manifest?.live_binding_status || '').toUpperCase();
  if (manifest?.runtime_preview || ['METADATA_ONLY', 'NO_LIVE_SAMPLE', 'NOT_BOUND', 'RUNTIME_FALLBACK'].includes(bindingState)) {
    return 'Live sample unavailable';
  }
  if (['FAILED', 'BLOCKING', 'NOT_PUBLISHED'].includes(publishState)) {
    return 'Configuration review required';
  }
  return 'Live read-only';
}

function priorityTier(value) {
  const status = String(value || '').toUpperCase();
  if (['CRITICAL', 'LOW', 'QUARANTINED', 'UNAVAILABLE', 'BLOCKING'].includes(status)) return 'p1';
  if (['WARNING', 'MEDIUM', 'DEGRADED', 'NOT_PUBLISHED', 'NO_CONFIDENCE_RESULT'].includes(status)) return 'p2';
  if (status === 'SUBSTITUTED') return 'p3';
  return 'normal';
}

function confidenceValue(confidence) {
  const pct = confidence?.confidence_pct ?? confidence?.score ?? confidence?.value;
  return Number.isFinite(Number(pct)) ? Math.round(Number(pct)) : null;
}

function confidenceSubScores(confidence) {
  const subs = confidence?.sub_scores || {};
  return [
    ['Calibration', subs.calibration],
    ['Stability', subs.stability],
    ['Cross Sensor', subs.cross_sensor],
    ['Plausibility', subs.physical_plausibility],
  ].filter(([, value]) => Number.isFinite(Number(value)));
}

function signalTrustState(signal) {
  const confidence = signal?.confidence || {};
  const tier = signal?.trust_state || confidence.trust_state || confidence.tier || confidence.state || 'METADATA_ONLY';
  const pct = confidenceValue(confidence);
  return { tier: String(tier).toUpperCase(), pct };
}

function normalizeTagIdentifier(value) {
  return String(value || '')
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '');
}

function sameTag(left, right) {
  const a = normalizeTagIdentifier(left);
  const b = normalizeTagIdentifier(right);
  return Boolean(a && b && a === b);
}

function signalRole(signal) {
  const raw = String(signal?.role || signal?.sensor_type || signal?.signal_role || '').toLowerCase();
  if (['mass_balance_input', 'flow_in', 'inlet_flow', 'inflow'].includes(raw)) return 'inflow';
  if (['mass_balance_output', 'flow_out', 'outlet_flow', 'outflow'].includes(raw)) return 'outflow';
  if (['primary_level', 'level', 'validated_level'].includes(raw)) return 'level';
  if (['final_element_position', 'valve_position', 'position', 'valve'].includes(raw)) return 'valve_position';
  return raw;
}

function liveSignal(faceplateSignal, readings, confidence) {
  const tag = faceplateSignal?.tag || faceplateSignal?.sensor_id || faceplateSignal?.id;
  if (!tag) {
    return {
      ...(faceplateSignal || {}),
      tag: '',
      value: null,
      unit: faceplateSignal?.unit || '',
      confidence: faceplateSignal?.confidence || {},
      trust_state: faceplateSignal?.trust_state || 'METADATA_ONLY',
    };
  }
  const manifestReading = faceplateSignal?.reading || {};
  const liveReading = (readings || []).find((item) => sameTag(item.sensor_id, tag) || sameTag(item.tag, tag));
  const reading = liveReading || manifestReading || {};
  const conf = (confidence || []).find((item) => sameTag(item.sensor_id, tag) || sameTag(item.tag, tag)) || faceplateSignal?.confidence || {};
  const hasReading = Boolean(liveReading || reading?.sensor_id || reading?.tag || reading?.value != null);
  return {
    ...faceplateSignal,
    tag,
    value: reading.value ?? faceplateSignal?.value ?? '--',
    unit: reading.unit || faceplateSignal?.unit || '',
    confidence: conf,
    trust_state: faceplateSignal?.trust_state || conf.trust_state || conf.tier || (hasReading ? 'NO_CONFIDENCE_RESULT' : 'METADATA_ONLY'),
  };
}

function findSignal(faceplates, roles = []) {
  const wanted = new Set(roles.map((role) => String(role).toLowerCase()));
  for (const faceplate of faceplates || []) {
    for (const signal of faceplate.signals || []) {
      const role = signalRole(signal);
      if (wanted.has(role)) return { faceplate, signal };
    }
  }
  return null;
}

function buildBasisLines(manifest) {
  const basis = manifest?.operating_basis || {};
  const evidence = asList(basis.evidence);
  return [
    {
      statement: basis.abnormal_situation || 'Normal operation. No abnormal operating basis active.',
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
  ];
}

function runtimeModeLabel(manifest) {
  const publish = runtimeStatusLabel(manifest?.runtime_publish_state || manifest?.validation_status || 'LIVE');
  const binding = formatText(manifest?.live_binding_status || 'live tags');
  if (manifest?.runtime_preview) return `${publish} / metadata preview`;
  return `${publish} / ${binding}`;
}

function primaryBasisStatement(manifest, situations) {
  const basisLines = buildBasisLines(manifest);
  const active = basisLines.find((line) => line.status === 'active');
  return active?.statement || situations?.[0]?.title || basisLines[0]?.statement || 'Normal operation. No abnormal operating basis active.';
}

function decisionScore(situation, confidence) {
  const affected = asList(situation?.affected_sensors);
  const score = situation?.decision_time_score || situation?.interaction_compression_estimate || {};
  const rawSignalCount = score.raw_signal_count || affected.length || 1;
  const blockedDecisionCount = score.blocked_decision_count || asList(situation?.action_contract?.blocked_decisions || situation?.blocked_decisions).length;
  const requiredActionCount = score.required_operator_action_count || asList(situation?.action_contract?.first_safe_action || situation?.first_action).length || 1;
  const collapsedSituationCount = score.collapsed_situation_count || (situation?.title ? 1 : 0);
  const evidenceCount = asList(situation?.evidence_refs || situation?.evidence).length;
  const traditional = score.traditional_steps || Math.max(1, rawSignalCount + blockedDecisionCount + evidenceCount);
  const confidenceos = score.confidenceos_steps || Math.max(1, collapsedSituationCount + requiredActionCount);
  const affectedScores = (confidence || [])
    .filter((item) => affected.includes(item.sensor_id))
    .map((item) => Number(item.confidence_pct))
    .filter(Number.isFinite);
  return {
    metric_label: 'Interaction Compression Estimate',
    score: score.score || (affectedScores.length ? Math.round(affectedScores.reduce((sum, item) => sum + item, 0) / affectedScores.length) : 72),
    raw_signal_count: rawSignalCount,
    suppressed_alarm_count: score.suppressed_alarm_count ?? Math.max(0, rawSignalCount - collapsedSituationCount),
    collapsed_situation_count: collapsedSituationCount,
    blocked_decision_count: blockedDecisionCount,
    required_operator_action_count: requiredActionCount,
    traditional_steps: traditional,
    confidenceos_steps: confidenceos,
    decision_compression: score.decision_compression || `${traditional} -> ${confidenceos}`,
  };
}

function TrustStatusSymbol({ state }) {
  const tier = priorityTier(state);
  const label = tier === 'p1' ? '1' : tier === 'p2' ? '2' : tier === 'p3' ? '3' : 'N';
  return <span className={`hmi-status-symbol ${tier}`} title={formatText(state)}>{label}</span>;
}

function HmiLiveValue({ signal }) {
  const trust = signalTrustState(signal);
  const isLiveValue = !['METADATA_ONLY', 'NO_LIVE_SAMPLE', 'UNAVAILABLE'].includes(trust.tier)
    && signal.value != null
    && signal.value !== '--'
    && typeof signal.value !== 'object';
  return (
    <span className="hmi-live-value" title={`${signal.tag || 'generated signal'} - ${signalSourceNote(signal)}`}>
      <span>{signalDisplayValue(signal, { includeUnit: false })}</span>
      {isLiveValue && signal.unit && <span className="text-[11px] font-normal">{signal.unit}</span>}
    </span>
  );
}

function HmiAlarmBand({ manifest, role, connected, plantId, plantContext, situation }) {
  const basis = manifest?.operating_basis || {};
  const lead = situation || {};
  const trust = manifest?.worst_trust_exception || {};
  const isCritical = ['CRITICAL', 'QUARANTINED', 'LOW', 'FAILED'].includes(String(trust.trust_state || lead.severity || '').toUpperCase());
  const runtimeStatus = manifest?.runtime_publish_state || manifest?.validation_status || 'LIVE';
  const buildLabel = manifest?.published_build_id || manifest?.build_id || 'unpublished';
  const operatorView = isOperatorRole(role);
  const showBuildInternals = showEngineeringInternals(role);

  return (
    <div className="hmi-alarm-band">
      <div className={`hmi-band-cell ${isCritical ? 'hmi-band-critical' : 'hmi-band-warning'}`}>
        <TrustStatusSymbol state={trust.trust_state || lead.severity || manifest?.context} />
        <div className="min-w-0">
          <p className="label-caps text-[var(--text-muted)]">Abnormal Situation</p>
          <p className="caption-mono font-semibold truncate" title={lead.title || basis.abnormal_situation || 'Normal operation'}>
            {lead.title || basis.abnormal_situation || 'Normal operation'}
          </p>
        </div>
      </div>
      <div className="hmi-band-cell">
        <span className="label-caps">{operatorView ? 'Operating Context' : 'Runtime'}</span>
        <span className="caption-mono text-[var(--text-muted)] truncate">
          {manifest?.navigation?.name || plantId} / {formatText(manifest?.context || plantContext?.status || 'live')}
        </span>
        {operatorView && (
          <span className={`caption-mono ${connected ? 'status-safe' : 'status-critical'}`}>
            {operatorRuntimeLabel(manifest, connected)}
          </span>
        )}
        {showBuildInternals && (
          <>
            <span className={`caption-mono ${statusClass(runtimeStatus)}`}>{runtimeStatusLabel(runtimeStatus)}</span>
            <span className="caption-mono text-[var(--text-dim)]">build {String(buildLabel).slice(0, 18)}</span>
          </>
        )}
      </div>
      <div className="hmi-band-cell justify-end">
        <span className="caption-mono">{role}</span>
        <span className={connected ? 'caption-mono status-safe' : 'caption-mono status-critical'}>
          {connected ? 'LIVE READ-ONLY' : 'OFFLINE'}
        </span>
      </div>
    </div>
  );
}

function TrustMapEdgeNav({ navigation, faceplates, selectedId, onSelect, situations, handoverDebt }) {
  return (
    <aside className="hmi-edge-nav" aria-label="Trust map navigation">
      <button className="hmi-edge-button active" title={navigation?.name || 'Plant'}>Plant</button>
      {(faceplates || []).map((faceplate) => {
        const hotspot = (faceplate.signals || []).some((signal) => ['LOW', 'CRITICAL', 'QUARANTINED', 'DEGRADED'].includes(signalTrustState(signal).tier));
        return (
          <button
            key={faceplate.equipment_id}
            type="button"
            onClick={() => onSelect(faceplate.equipment_id)}
            className={`hmi-edge-button ${selectedId === faceplate.equipment_id ? 'active' : ''}`}
            title={faceplate.title || faceplate.equipment_id}
          >
            <span className={hotspot ? 'status-warning' : ''}>{faceplate.equipment_id}</span>
          </button>
        );
      })}
      <button className="hmi-edge-button" title={`${situations.length} collapsed situations`}>{situations.length} Sit.</button>
      <button className="hmi-edge-button" title={`${handoverDebt?.count || 0} unresolved handover debt items`}>{handoverDebt?.count || 0} Debt</button>
    </aside>
  );
}

function ProcessCanvas({ manifest, faceplates, readings, confidence, situations, onSelect, role, connected }) {
  const vessel = faceplates.find((item) => /vessel|tank/i.test(`${item.template_id} ${item.template_label} ${item.title}`)) || faceplates[0];
  const pump = faceplates.find((item) => /pump/i.test(`${item.template_id} ${item.template_label} ${item.title}`));
  const valve = faceplates.find((item) => /valve/i.test(`${item.template_id} ${item.template_label} ${item.title}`));
  const level = liveSignal(findSignal(faceplates, ['level'])?.signal || vessel?.signals?.[0], readings, confidence);
  const inflow = liveSignal(findSignal(faceplates, ['inflow'])?.signal, readings, confidence);
  const outflow = liveSignal(findSignal(faceplates, ['outflow'])?.signal, readings, confidence);
  const vibration = liveSignal(findSignal(faceplates, ['vibration'])?.signal, readings, confidence);
  const basis = manifest?.operating_basis || {};
  const levelTrust = signalTrustState(level);
  const levelHeight = Number.isFinite(Number(level.value)) ? Math.max(8, Math.min(86, Number(level.value))) : 42;
  const basisStatement = primaryBasisStatement(manifest, situations);
  const publishState = manifest?.runtime_publish_state || manifest?.validation_status || 'LIVE';
  const previewLike = manifest?.runtime_preview || String(publishState).toUpperCase() === 'NOT_PUBLISHED';
  const operatorView = isOperatorRole(role);
  const title = manifest?.process_mimic?.relationship_label || manifest?.navigation?.name || (operatorView ? 'Process mimic' : 'Generated process mimic');
  const runtimeBadge = operatorView ? operatorRuntimeLabel(manifest, connected) : runtimeModeLabel(manifest);
  const runtimeBadgeTitle = operatorView ? 'Read-only operating display state.' : (manifest?.runtime_notice || runtimeModeLabel(manifest));
  const runtimeNeedsAttention = previewLike || !connected || ['FAILED', 'BLOCKING', 'NOT_PUBLISHED'].includes(String(publishState).toUpperCase());
  const processEyebrow = operatorView ? 'Level 2 Unit Overview / Process Graphic' : 'Level 2 Unit Overview / Generated Process Graphic';
  const assetFooter = operatorView ? formatText(vessel?.template_label || vessel?.template_id || 'equipment') : `${vessel?.template_id || 'template'} / generated from asset model`;

  return (
    <section className="hmi-process-area">
      <div className="hmi-process-header">
        <div className="min-w-0">
          <p className="label-caps text-[var(--text-muted)]">{processEyebrow}</p>
          <h1 className="m-0 text-[16px] leading-[18px] font-bold truncate">{title}</h1>
        </div>
        <div className="hmi-runtime-basis">
          <div className="min-w-0">
            <p className="label-caps text-[var(--text-muted)]">Operating Basis</p>
            <p className={`caption-mono font-semibold truncate ${runtimeNeedsAttention ? 'status-warning' : 'text-[var(--text)]'}`} title={basisStatement}>
              {basisStatement}
            </p>
          </div>
          <span className={`industrial-badge ${runtimeNeedsAttention ? 'status-warning' : 'status-safe'}`} title={runtimeBadgeTitle}>
            {runtimeBadge}
          </span>
        </div>
      </div>
      <div className="hmi-process-canvas">
        <svg viewBox="0 0 1000 520" role="img" aria-label={operatorView ? 'Process mimic' : 'Generated process mimic'} className="w-full h-full">
          <defs>
            <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
              <path d="M0,0 L0,6 L9,3 z" fill="#4d4d4d" />
            </marker>
            <pattern id="quarantineHatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="8" stroke="#cc0000" strokeWidth="2" />
            </pattern>
          </defs>

          <rect x="0" y="0" width="1000" height="520" fill="#c9c9c9" />

          <line x1="80" y1="210" x2="350" y2="210" stroke="#555" strokeWidth="6" markerEnd="url(#arrow)" />
          <line x1="650" y1="310" x2="920" y2="310" stroke="#555" strokeWidth="6" markerEnd="url(#arrow)" />
          <line x1="500" y1="120" x2="500" y2="86" stroke="#555" strokeWidth="3" strokeDasharray="7 5" />

          <text x="100" y="184" fill="#4d4d4d" fontSize="15" fontWeight="700">Inflow</text>
          <foreignObject x="98" y="218" width="190" height="58">
            <div xmlns="http://www.w3.org/1999/xhtml" className="flex items-center gap-2">
              <TrustStatusSymbol state={inflow.trust_state} />
              <div>
                <p className="label-caps text-[var(--text-muted)]">{inflow.tag || 'inflow'}</p>
                <HmiLiveValue signal={inflow} />
              </div>
            </div>
          </foreignObject>

          <text x="742" y="286" fill="#4d4d4d" fontSize="15" fontWeight="700">Outflow</text>
          <foreignObject x="738" y="320" width="196" height="58">
            <div xmlns="http://www.w3.org/1999/xhtml" className="flex items-center gap-2">
              <TrustStatusSymbol state={outflow.trust_state} />
              <div>
                <p className="label-caps text-[var(--text-muted)]">{outflow.tag || 'outflow'}</p>
                <HmiLiveValue signal={outflow} />
              </div>
            </div>
          </foreignObject>

          <g onClick={() => vessel?.equipment_id && onSelect(vessel.equipment_id)} style={{ cursor: vessel ? 'pointer' : 'default' }}>
            <rect x="350" y="110" width="300" height="300" rx="14" fill="#d7d7d7" stroke="#6f6f6f" strokeWidth="4" />
            <rect x="370" y={390 - levelHeight * 2.7} width="260" height={levelHeight * 2.7} fill={levelTrust.tier === 'QUARANTINED' ? 'url(#quarantineHatch)' : '#9fb7c8'} opacity="0.72" />
            <line x1="370" y1="260" x2="630" y2="260" stroke="#777" strokeWidth="2" strokeDasharray="5 5" />
            <text x="374" y="92" fill="#3a3a3a" fontSize="17" fontWeight="700">{vessel?.equipment_id || (operatorView ? 'Equipment' : 'Generated Asset')}</text>
            <text x="374" y="430" fill="#4d4d4d" fontSize="13">{assetFooter}</text>
          </g>

          <foreignObject x="455" y="172" width="260" height="90">
            <div xmlns="http://www.w3.org/1999/xhtml" className="flex items-start gap-2">
              <TrustStatusSymbol state={level.trust_state} />
              <div>
                <p className={`label-caps ${statusClass(levelTrust.tier)}`}>{level.tag || 'primary level'}</p>
                <HmiLiveValue signal={level} />
                <p className="caption-mono text-[var(--text-muted)] mt-1">
                  {formatText(levelTrust.tier)}{levelTrust.pct != null ? ` / ${levelTrust.pct}%` : ''}
                </p>
              </div>
            </div>
          </foreignObject>

          {pump && (
            <g onClick={() => onSelect(pump.equipment_id)} style={{ cursor: 'pointer' }}>
              <circle cx="790" cy="210" r="54" fill="#d7d7d7" stroke="#6f6f6f" strokeWidth="4" />
              <path d="M770 188 L830 210 L770 232 Z" fill="#888" />
              <text x="735" y="150" fill="#3a3a3a" fontSize="15" fontWeight="700">{pump.equipment_id}</text>
              {vibration.tag && (
                <foreignObject x="704" y="252" width="190" height="68">
                  <div xmlns="http://www.w3.org/1999/xhtml" className="flex items-center gap-2">
                    <TrustStatusSymbol state={vibration.trust_state} />
                    <div>
                      <p className="label-caps text-[var(--text-muted)]">{vibration.tag}</p>
                      <HmiLiveValue signal={vibration} />
                    </div>
                  </div>
                </foreignObject>
              )}
            </g>
          )}

          {valve && (
            <g onClick={() => onSelect(valve.equipment_id)} style={{ cursor: 'pointer' }}>
              <path d="M675 292 L725 328 M725 292 L675 328" stroke="#5b5b5b" strokeWidth="6" />
              <text x="658" y="278" fill="#3a3a3a" fontSize="14" fontWeight="700">{valve.equipment_id}</text>
            </g>
          )}

          <foreignObject x="36" y="28" width="430" height="92">
            <div xmlns="http://www.w3.org/1999/xhtml" className="hmi-operation-note">
              <p className="label-caps text-[var(--text-muted)]">Operating Basis</p>
              <p className="caption-mono font-semibold mt-1">{displayText(basis.abnormal_situation) || 'No abnormal situation active.'}</p>
              <p className="caption-mono text-[var(--text-muted)] mt-1">{asList(basis.evidence).slice(0, 2).map(displayText).filter(Boolean).join(' / ') || 'live process values within operating basis'}</p>
            </div>
          </foreignObject>
        </svg>
      </div>
    </section>
  );
}

function DockSection({ title, eyebrow, right, children }) {
  return (
    <section className="hmi-dock-section">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {eyebrow && <p className="label-caps text-[var(--text-muted)]">{eyebrow}</p>}
          <h2 className="hmi-dock-title truncate" title={title}>{title}</h2>
        </div>
        {right}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function ValueList({ values, empty = 'No active item.', status = 'text-[var(--data-mono)]' }) {
  const rows = asList(values);
  if (!rows.length) return <p className="caption-mono text-[var(--text-muted)]">{empty}</p>;
  return (
    <div className="space-y-2">
      {rows.map((item, index) => (
        // Index keeps the key unique even when the same item id appears twice in
        // a section's values (avoids React duplicate-key warnings / dropped rows).
        <p key={`${typeof item === 'string' ? item : item?.id || 'row'}-${index}`} className={`caption-mono ${status}`}>
          {displayText(item)}
        </p>
      ))}
    </div>
  );
}

function SimulationControlStrip({ demoState, busy, onReset, onStart, role }) {
  const phase = demoState?.phase || 'NORMAL_BASELINE';
  const failures = asList(demoState?.active_failures).map((item) => item.operator_label || displayText(item));
  const story = asList(demoState?.operator_story);
  const lifecycle = demoState?.lifecycle || {};
  const workflowEffects = asList(demoState?.workflow_effects);
  const activeIndex = Math.max(0, Number(demoState?.phase_index ?? 0));
  // Simulation control buttons (reset/inject) are restricted to Engineer and Manager roles.
  // Operators see the scenario status (so they know data is simulated) but cannot trigger scenario transitions.
  const roleKey = normalizeRole(role);
  const canControl = roleKey === 'engineer' || roleKey === 'manager';
  return (
    <section className="hmi-demo-strip">
      <div className="min-w-0">
        <p className="label-caps text-[var(--text-muted)]">
          Training Source — Simulator Scenario State
          {!canControl && (
            <span className="ml-2 text-[var(--text-dim)] normal-case font-normal">
              (read-only view — scenario control available to Engineers)
            </span>
          )}
        </p>
        <p className="caption-mono font-semibold truncate">
          {formatText(phase)} / {demoState?.stream_status || 'stream pending'} / tick {demoState?.tick_count ?? '--'}
        </p>
        <div className="hmi-demo-failures mt-1">
          {failures.length ? failures.map((failure) => (
            <span key={failure}>{failure}</span>
          )) : (
            <span>Normal baseline. No simulator trust failure injected.</span>
          )}
        </div>
        {story.length > 0 && (
          <div className="hmi-demo-timeline mt-2" aria-label="Simulator scenario timeline">
            {story.map((item, index) => (
              <span key={item} className={index <= activeIndex ? 'active' : ''}>
                {index + 1}. {item}
              </span>
            ))}
          </div>
        )}
        {(lifecycle.expected_system_response || demoState?.trust_recovery_status) && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-2">
            <p className="caption-mono text-[var(--text-muted)]">
              response: {lifecycle.expected_system_response || 'Runtime monitors trust state.'}
            </p>
            <p className="caption-mono text-[var(--text-muted)]">
              recovery: {lifecycle.recovery_condition || demoState?.trust_recovery_status || 'No recovery action required.'}
            </p>
            <p className="caption-mono text-[var(--text-muted)]">
              workflow: {workflowEffects[0] || 'Runtime remains in normal monitoring mode.'}
            </p>
          </div>
        )}
      </div>
      {canControl && (
        <div className="flex items-center gap-2 shrink-0">
          <button type="button" disabled={busy} onClick={onReset} className="industrial-control">Reset Simulator</button>
          <button type="button" disabled={busy} onClick={onStart} className="industrial-control status-warning">Inject Abnormal Situation</button>
        </div>
      )}
    </section>
  );
}

function ConfidenceEvidenceLedger({ confidence, situation, basis }) {
  const affected = new Set([
    ...asList(situation?.affected_sensors),
    ...asList(basis?.do_not_trust),
  ].map(String));
  const rows = (confidence || []).filter((item) => affected.size ? affected.has(String(item.sensor_id)) : true).slice(0, 3);
  if (!rows.length) {
    return (
      <div className="bg-[var(--surface-highest)] border border-[var(--border-strong)] p-4">
        <p className="label-caps text-[var(--text-muted)]">Confidence Evidence Ledger</p>
        <p className="caption-mono text-[var(--text-muted)] mt-2">
          Waiting for confidence evidence from the live simulator stream. The display will show formula factors, strongest evidence, and counter-evidence when samples arrive.
        </p>
      </div>
    );
  }
  return (
    <div className="bg-[var(--surface-highest)] border border-[var(--border-strong)] p-4">
      <p className="label-caps text-[var(--text-muted)]">Confidence Evidence Ledger</p>
      <p className="caption-mono text-[var(--text-muted)] mt-1">
        Confidence is a governed trust rubric, not probability. The score explains whether a reading can be used as operating basis.
      </p>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 mt-3">
        {rows.map((item) => {
          const evidence = asList(item.evidence);
          const problem = evidence.find((entry) => !['OK', 'INFO'].includes(String(entry?.status || '').toUpperCase())) || evidence[0];
          const counter = evidence.find((entry) => String(entry?.status || '').toUpperCase() === 'OK');
          const subScores = confidenceSubScores(item);
          return (
            <div key={item.sensor_id} className="border border-[var(--border-strong)] bg-[var(--surface-panel)] p-3 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <p className="caption-mono font-semibold">{item.sensor_id}</p>
                <span className={statusClass(item.trust_state || item.tier)}>
                  {formatText(item.trust_state || item.tier)}{Number.isFinite(Number(item.confidence_pct)) ? ` / ${Math.round(Number(item.confidence_pct))}%` : ' / evidence pending'}
                </span>
              </div>
              {subScores.length > 0 && (
                <div className="grid grid-cols-2 gap-2 mt-3">
                  {subScores.map(([label, value]) => (
                    <div key={label} className="border border-[var(--border)] bg-[var(--surface-highest)] px-2 py-1">
                      <p className="label-caps text-[var(--text-dim)]">{label}</p>
                      <p className={`caption-mono font-semibold ${Number(value) < 0.5 ? 'status-critical' : Number(value) < 0.8 ? 'status-warning' : 'status-safe'}`}>
                        {Number(value).toFixed(2)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
              <p className="label-caps text-[var(--text-muted)] mt-3">Dominant Factor</p>
              <p className="caption-mono">{formatText(item.dominant_factor || 'current evidence')}</p>
              <p className="label-caps text-[var(--text-muted)] mt-3">Strongest Evidence</p>
              <p className="caption-mono status-warning">{displayText(problem) || item.trust_reason || 'No adverse evidence listed.'}</p>
              <p className="label-caps text-[var(--text-muted)] mt-3">Counter-Evidence</p>
              <p className="caption-mono status-safe">{displayText(counter) || 'No independent positive evidence listed.'}</p>
              <p className="label-caps text-[var(--text-muted)] mt-3">What Restores Trust</p>
              <ValueList values={basis?.exit_condition || item.recommended_action} empty="Manual verification accepted or mass-balance contradiction clears." />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GeneratedFaceplate({ faceplate, readings, confidence, compact = false, role = 'Operator' }) {
  const signals = (faceplate?.signals || []).map((signal) => liveSignal(signal, readings, confidence));
  // Template provenance and generation receipts are engineering detail — the
  // operator faceplate shows only the equipment and its live trusted signals.
  const showTemplateInternals = showEngineeringInternals(role);
  return (
    <div className="bg-[var(--surface-highest)] border border-[var(--border-strong)] p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label-caps text-[var(--text-muted)]">{showTemplateInternals ? 'Generated From Template' : 'Equipment Faceplate'}</p>
          <p className="caption-mono font-semibold truncate">{faceplate?.equipment_id || faceplate?.title}</p>
        </div>
        {showTemplateInternals && (
          <span className="caption-mono text-[var(--text-muted)]">{faceplate?.template_id} v{faceplate?.template_version || '1.0'}</span>
        )}
      </div>
      <table className="hmi-flat-table mt-3">
        <thead>
          <tr><th>Tag</th><th>Value</th><th>Trust</th></tr>
        </thead>
        <tbody>
          {signals.slice(0, compact ? 4 : 8).map((signal) => {
            const trust = signalTrustState(signal);
            return (
              <tr key={signal.tag}>
                <td>{signal.tag}</td>
                <td title={signalSourceNote(signal)}>{signalDisplayValue(signal)}</td>
                <td><span className={statusClass(trust.tier)}>{formatText(trust.tier)}{trust.pct != null ? ` / ${trust.pct}%` : ''}</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!compact && showTemplateInternals && (
        <div className="mt-3">
          <p className="label-caps text-[var(--text-muted)]">Receipt Summary</p>
          <ValueList values={faceplate?.receipt?.generated_because?.slice?.(0, 3)} empty="Receipt attached to generated manifest." />
        </div>
      )}
    </div>
  );
}

const LEGAL_NEXT = {
  REQUESTED: ['ASSIGNED', 'EXPIRED'],
  ASSIGNED: ['FIELD_CHECK_DONE', 'EXPIRED'],
  FIELD_CHECK_DONE: ['ACCEPTED', 'REJECTED', 'EXPIRED'],
  REJECTED: ['ASSIGNED', 'EXPIRED'],
};
const EVIDENCE_REQUIRED_STATES = new Set(['FIELD_CHECK_DONE', 'ACCEPTED', 'REJECTED']);
const STATE_LABEL = {
  ASSIGNED: 'Assign',
  FIELD_CHECK_DONE: 'Field Check Done',
  ACCEPTED: 'Accept',
  REJECTED: 'Reject',
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

function VerificationTaskControls({ tasks, role, plantId }) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');

  const updateTask = async (task, state) => {
    const taskId = task.task_id || task.token_id;
    if (!taskId) return;
    if (EVIDENCE_REQUIRED_STATES.has(state) && !note.trim()) {
      setMessage(`Evidence note required to move task to ${state}.`);
      return;
    }
    setBusy(`${taskId}:${state}`);
    setMessage('');
    try {
      const res = await apiFetch(`/api/verification-tasks/state?plant_id=${plantId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: taskId,
          state,
          actor: role,
          actor_role: role,
          accepted_by: state === 'ACCEPTED' ? role : null,
          evidence_note: note,
          note,
        }),
      });
      const payload = await res.json().catch(() => null);
      if (!res.ok) throw new Error(payload?.detail || `Request failed: ${res.status}`);
      setMessage(`${task.sensor_id || taskId} moved to ${state}.`);
      setNote('');
    } catch (err) {
      setMessage(err.message || 'Task update failed.');
    } finally {
      setBusy('');
    }
  };

  const visible = (tasks || []).slice(0, 4);
  return (
    <div>
      {visible.length ? visible.map((task) => {
        const legal = legalTransitionsForRole(task.state, role);
        return (
          <div key={task.task_id || task.token_id} className="border border-[var(--border-strong)] bg-[var(--surface-highest)] p-2 mb-2">
            <div className="flex items-center justify-between gap-2">
              <p className="caption-mono font-semibold">{task.sensor_id}</p>
              <span className="caption-mono status-warning">{task.state}</span>
            </div>
            <p className="caption-mono text-[var(--text-muted)] mt-1">{formatText(task.verification_method || task.verification_type)}</p>
            <ValueList values={task.evidence_required} empty="Evidence requirement not listed." />
            {legal.length > 0 && (
              <div className="grid grid-cols-2 gap-1 mt-2">
                {legal.map((state) => (
                  <button key={state} type="button" disabled={!!busy} onClick={() => updateTask(task, state)} className="industrial-control bg-[var(--surface-panel)] disabled:opacity-40">
                    {STATE_LABEL[state] || formatText(state)}
                  </button>
                ))}
              </div>
            )}
          </div>
        );
      }) : <p className="caption-mono text-[var(--text-muted)]">No active field verification task.</p>}
      <input value={note} onChange={(event) => setNote(event.target.value)} className="industrial-input mt-2" placeholder="Evidence note for task transition" />
      {message && <p className="caption-mono text-[var(--text-muted)] mt-2">{message}</p>}
    </div>
  );
}

function RoleDock({ manifest, selectedFaceplate, confidenceDebt, handoverDebt, verificationTasks, plantId }) {
  const role = manifest?.role || 'Operator';
  const roleKey = normalizeRole(role);
  const basis = manifest?.operating_basis || {};
  const sections = manifest?.role_sections || [];
  const sectionItems = (name) => sections.filter((item) => item.section === name).flatMap((item) => item.items || []);

  if (roleKey === 'maintenance') {
    return (
      <>
        <DockSection title="Verification Task" eyebrow="Maintenance Workspace">
          <VerificationTaskControls tasks={sectionItems('verification_task').length ? sectionItems('verification_task') : verificationTasks} role={role} plantId={plantId} />
        </DockSection>
        <DockSection title="Device Health">
          <ValueList values={sectionItems('device_health')} empty="No device-health exception attached." />
        </DockSection>
        <DockSection title="Confidence Debt">
          <ValueList values={(confidenceDebt || []).map((item) => `${item.sensor_id}: ${item.priority_language || item.maintenance_priority || item.confidence_debt}`)} empty="No confidence debt active." status="status-warning" />
        </DockSection>
      </>
    );
  }

  if (roleKey === 'engineer') {
    const receipt = selectedFaceplate?.receipt || {};
    return (
      <>
        <DockSection title="Field Verification" eyebrow="Engineer Workspace">
          <VerificationTaskControls tasks={sectionItems('verification_task').length ? sectionItems('verification_task') : verificationTasks} role={role} plantId={plantId} />
        </DockSection>
        <DockSection title="Signal Binding">
          <ValueList values={(selectedFaceplate?.signals || []).map((signal) => `${signal.tag}: ${signal.role || signal.sensor_type || 'signal'} -> ${selectedFaceplate.equipment_id}`)} />
        </DockSection>
        <DockSection title="Template Receipt">
          <ValueList values={receipt.generated_because} empty="No generated-because receipt lines." />
          <ValueList values={receipt.warnings} empty="No receipt warnings." status="status-warning" />
          <p className="caption-mono text-[var(--text-muted)] mt-2">{selectedFaceplate?.template_id} v{selectedFaceplate?.template_version || '1.0'}</p>
        </DockSection>
        <DockSection title="Validation Warnings">
          <ValueList values={sectionItems('validation_warnings').map((item) => item.message || item.rule)} empty="No validation warnings attached." status="status-warning" />
        </DockSection>
      </>
    );
  }

  if (roleKey === 'manager' || roleKey === 'auditor') {
    return (
      <>
        <DockSection title="Unresolved Handover Debt" eyebrow={`${role} Workspace`}>
          <ValueList values={handoverDebt?.entries || []} empty="No unresolved handover debt." status={(handoverDebt?.count || 0) ? 'status-warning' : 'status-safe'} />
        </DockSection>
        <DockSection title="Handover Acceptance">
          <p className={`caption-mono ${(handoverDebt?.handover_acceptance_blocked || handoverDebt?.handover_acceptance === 'blocked') ? 'status-critical' : 'status-safe'}`}>
            {(handoverDebt?.handover_acceptance_blocked || handoverDebt?.handover_acceptance === 'blocked') ? 'Blocked until verification debt clears.' : 'Unblocked.'}
          </p>
        </DockSection>
        <DockSection title="Field Verification">
          {/* Manager can accept/reject a field-checked task; Auditor sees it read-only
              (legalTransitionsForRole returns no actions for Auditor). */}
          <VerificationTaskControls tasks={verificationTasks} role={role} plantId={plantId} />
        </DockSection>
        <DockSection title="Published Build">
          <ValueList values={[manifest?.published_build_id || manifest?.build_id || 'No published build id listed']} />
        </DockSection>
      </>
    );
  }

  return (
    <>
      <DockSection title="Single Safe Move" eyebrow="Operator Workspace">
        <ValueList values={basis.operator_single_safe_move || basis.first_safe_action} empty="No single safe move required." status="status-safe" />
      </DockSection>
      <DockSection title="Do Not Trust">
        <ValueList values={basis.do_not_trust} empty="No signal quarantined from operating basis." status="status-critical" />
      </DockSection>
      <DockSection title="Trusted Substitute">
        <ValueList values={basis.trusted_substitutes} empty="No substitute required." status="status-safe" />
      </DockSection>
      <DockSection title="Decision Freeze">
        <ValueList values={basis.decision_freeze} empty="No decision freeze active." status="status-warning" />
      </DockSection>
      <DockSection title="Exit Condition">
        <ValueList values={basis.exit_condition} empty="No abnormal exit condition active." />
      </DockSection>
    </>
  );
}

function BottomStrip({ manifest, situations, handoverDebt, chartHistory }) {
  const lead = situations?.[0] || {};
  const score = decisionScore(lead);
  const basisLines = buildBasisLines(manifest);

  // Embedded trend: plot the *indicated* level (what the LT reports) over the
  // latest samples, with an explicit unit, a current-value marker, and a label
  // saying whether the line is measured or implied — so it reads, not decorates.
  const trendSamples = (chartHistory || []).slice(-24);
  const trendUsesMeasured = trendSamples.some((p) => p.measured != null);
  const trendValue = (p) => Number((p.measured ?? p.implied ?? 0));
  const trendLast = trendSamples.length ? trendValue(trendSamples[trendSamples.length - 1]) : null;
  const trendY = (v) => 70 - Math.max(0, Math.min(70, v));
  const trendXY = trendSamples.map((point, index, arr) => ({
    x: arr.length <= 1 ? 300 : (index / (arr.length - 1)) * 300,
    y: trendY(trendValue(point)),
  }));
  const trendEnd = trendXY[trendXY.length - 1];

  return (
    <footer className="hmi-bottom-strip">
      <section className="hmi-strip-cell">
        <div className="flex items-baseline justify-between gap-2">
          <p className="label-caps text-[var(--text-muted)]">Embedded Trend</p>
          <p className="caption-mono text-[var(--text)]">
            {trendLast != null ? `${trendLast.toFixed(1)} ft` : '-- ft'}
          </p>
        </div>
        <div className="h-[72px] mt-2 border border-[var(--border-strong)] bg-[var(--surface-highest)] relative overflow-hidden">
          <span className="absolute left-1 top-1 caption-mono text-[9px] text-[var(--text-muted)]">
            {trendUsesMeasured ? 'measured level (ft)' : 'implied level (ft)'}
          </span>
          <span className="absolute right-1 bottom-1 caption-mono text-[9px] text-[var(--text-muted)]">latest 24 samples</span>
          <svg viewBox="0 0 300 72" className="w-full h-full">
            <line x1="0" y1="12" x2="300" y2="12" stroke="#9a9a9a" strokeWidth="0.5" strokeDasharray="3 3" />
            <line x1="0" y1="60" x2="300" y2="60" stroke="#9a9a9a" strokeWidth="0.5" strokeDasharray="3 3" />
            <polyline
              fill="none"
              stroke="#005aa0"
              strokeWidth="2"
              points={trendXY.map((p) => `${p.x},${p.y}`).join(' ')}
            />
            {trendEnd && (
              <circle cx={trendEnd.x} cy={trendEnd.y} r="3" fill="#005aa0" />
            )}
          </svg>
        </div>
      </section>
      <section className="hmi-strip-cell">
        <p className="label-caps text-[var(--text-muted)]">Operating Basis Ledger</p>
        {basisLines.slice(0, 3).map((line, index) => (
          <p key={`${line.statement}-${index}`} className={`caption-mono mt-1 ${line.status === 'normal' ? 'status-safe' : 'status-warning'}`}>
            {line.statement}
          </p>
        ))}
      </section>
      <section className="hmi-strip-cell">
        <p className="label-caps text-[var(--text-muted)]">Interaction Compression Estimate</p>
        <p className="text-[22px] leading-[26px] font-bold mt-1">{score.decision_compression}</p>
        <p className="caption-mono text-[var(--text-muted)] mt-1">
          raw {score.raw_signal_count} / suppressed {score.suppressed_alarm_count} / action {score.required_operator_action_count}
        </p>
        <p className={`caption-mono mt-1 ${(handoverDebt?.count || 0) ? 'status-warning' : 'status-safe'}`}>
          unresolved handover debt: {handoverDebt?.count || 0}
        </p>
      </section>
    </footer>
  );
}

function PressureModeRuntime({
  manifest,
  situations,
  confidence,
  connected,
  plantId,
  plantContext,
  chartHistory,
  massBalance,
  demoState,
  demoBusy,
  onDemoReset,
  onDemoStart,
  isSimulation,
  role,
}) {
  const lead = situations?.[0] || {};
  const basis = manifest?.operating_basis || {};
  const contract = lead.action_contract || {};
  const collapse = lead.alarm_collapse_receipt || basis.alarm_collapse_receipt || lead.alarm_collapse || {};
  const score = decisionScore(lead, confidence);
  // Physics is the alarm: surface the implied-vs-indicated gap when a
  // mass-balance contradiction is the basis of the abnormal situation.
  const hasMassBalanceStory = (massBalance?.flags || []).length > 0
    || (chartHistory || []).length > 1;
  const flagMessages = asList(massBalance?.flags).map(displayText);

  return (
    <div className="industrial-page hmi-workplace hmi-pressure">
      <HmiAlarmBand manifest={manifest} role="Operator" connected={connected} plantId={plantId} plantContext={plantContext} situation={lead} />
      <div className="hmi-main-grid">
        <section className="hmi-process-area">
          <div className="hmi-process-header">
            <div>
              <p className="label-caps text-[var(--text-muted)]">Pressure Mode / Operating Basis Workflow</p>
              <h1 className="m-0 text-[17px] leading-[20px] font-bold">{lead.title || basis.abnormal_situation || 'Abnormal situation'}</h1>
            </div>
            <span className="caption-mono status-warning">Grounded explanation disabled during active decision freeze.</span>
          </div>
          <div className="hmi-process-canvas p-5 flex flex-col gap-3 overflow-y-auto scrollbar-thin">
            {isSimulation && (
              <SimulationControlStrip demoState={demoState || manifest?.demo_state} busy={demoBusy} onReset={onDemoReset} onStart={onDemoStart} role={role} />
            )}
            {flagMessages.length > 0 && (
              <div className="hmi-alert-ribbon">
                <p className="label-caps status-critical">Mass-balance evidence</p>
                <ValueList values={flagMessages} status="status-critical" />
              </div>
            )}
            {/* The star of the abnormal situation: physics disagreeing with the
                indicated reading. This dominates the operator's view. */}
            {hasMassBalanceStory && (
              <div className="min-h-[560px] w-full shrink-0" style={{ minWidth: 0 }}>
                <MassBalanceChart chartHistory={chartHistory} massBalance={massBalance} flags={massBalance?.flags} />
              </div>
            )}
            <div className="hmi-operation-note">
              <p className="label-caps text-[var(--text-muted)]">Operator Single Safe Move</p>
              <p className="text-[24px] leading-[30px] font-bold mt-2">
                {formatText(basis.operator_single_safe_move || contract.first_safe_action || 'Verify locally before changing operation.')}
              </p>
            </div>
            <ComparisonPanel confidence={confidence} massBalance={massBalance} basis={basis} situation={lead} />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              <div className="bg-[var(--surface-highest)] border border-[var(--border-strong)] p-4">
                <p className="label-caps status-critical">Do Not Trust</p>
                <ValueList values={basis.do_not_trust || contract.do_not_use} status="status-critical" />
                <p className="label-caps status-safe mt-4">Trusted Substitute</p>
                <ValueList values={basis.trusted_substitutes || contract.trusted_substitutes} status="status-safe" />
              </div>
              <div className="bg-[var(--surface-highest)] border border-[var(--border-strong)] p-4">
                <p className="label-caps status-warning">Decision Freeze</p>
                <ValueList values={basis.decision_freeze || contract.blocked_decisions} status="status-warning" />
                <p className="label-caps text-[var(--text-muted)] mt-4">Exit Condition</p>
                <ValueList values={basis.exit_condition || contract.exit_conditions} />
              </div>
            </div>
            <ConfidenceEvidenceLedger confidence={confidence} situation={lead} basis={basis} />
            <div className="bg-[var(--surface-highest)] border border-[var(--border-strong)] p-4">
              <p className="label-caps text-[var(--text-muted)]">Alarm Collapse Receipt</p>
              <p className="caption-mono mt-2">Raw signals: {collapse.raw_signal_count ?? asList(lead.affected_sensors).length}</p>
              <p className="caption-mono">Suppressed alarms: {collapse.suppressed_alarm_count ?? score.suppressed_alarm_count}</p>
              <p className="caption-mono mt-2 font-semibold">{collapse.operator_question || 'Can the operator trust the primary indication before changing operation?'}</p>
              <p className="caption-mono text-[var(--text-muted)] mt-2">{collapse.collapse_reason || 'Signals affect the same operating basis.'}</p>
              <p className="label-caps text-[var(--text-muted)] mt-4">Interaction Compression</p>
              <p className="text-[22px] font-bold">{score.decision_compression}</p>
            </div>
          </div>
        </section>
        <aside className="hmi-dock">
          <DockSection title="Simulator Source" eyebrow="Training State">
            <ValueList
              values={[
                `phase: ${(demoState || manifest?.demo_state)?.phase || 'normal baseline'}`,
                `active failures: ${(demoState || manifest?.demo_state)?.active_failure_count ?? 0}`,
                (demoState || manifest?.demo_state)?.next_operator_action,
              ]}
            />
          </DockSection>
          <DockSection title="Operating Basis" eyebrow="Pressure Mode">
            <ValueList values={[basis.abnormal_situation || lead.title]} />
          </DockSection>
          <DockSection title="Required Operator Actions">
            <ValueList values={[`${score.required_operator_action_count} action required`]} status="status-warning" />
          </DockSection>
          <DockSection title="Read-Only Boundary">
            <p className="caption-mono text-[var(--text-muted)]">ConfidenceOS is a read-only trust-aware HMI layer beside existing DCS/HMI. It does not write commands, setpoints, or alarm acknowledgements.</p>
          </DockSection>
        </aside>
      </div>
    </div>
  );
}

function RuntimeUnavailable({ error, plantId, role, connected, onRetry }) {
  const operatorView = isOperatorRole(role);
  const manifest = {
    navigation: { name: operatorView ? 'Runtime operating view unavailable' : 'Runtime manifest unavailable' },
    context: 'runtime_unavailable',
    validation_status: 'FAILED',
    worst_trust_exception: { label: operatorView ? 'Runtime operating view unavailable' : 'Runtime manifest unavailable', trust_state: 'CRITICAL' },
  };
  const title = operatorView ? 'Runtime operating view unavailable' : 'Generated Runtime manifest did not load';
  const recovery = operatorView
    ? 'Retry Runtime data. If this remains active, continue from the existing HMI/DCS and notify Engineering.'
    : 'Retry Runtime manifest, then verify backend health if this remains active.';
  const detail = operatorView ? 'The read-only operating display cannot load current Runtime data.' : (error || 'No response from /api/screens/generated.');
  return (
    <div className="industrial-page hmi-workplace hmi-pressure">
      <HmiAlarmBand manifest={manifest} role={role} connected={connected} plantId={plantId} plantContext={{ status: 'runtime_unavailable' }} />
      <div className="hmi-main-grid">
        <section className="hmi-process-area">
          <div className="hmi-process-header">
            <div>
              <p className="label-caps text-[var(--text-muted)]">{operatorView ? 'Runtime Data State' : 'Runtime Fault State'}</p>
              <h1 className="m-0 text-[17px] leading-[20px] font-bold">{title}</h1>
            </div>
            <span className="caption-mono status-critical">operator display degraded</span>
          </div>
          <div className="hmi-process-canvas p-6">
            <div className="hmi-operation-note max-w-[760px]">
              <p className="label-caps status-critical">Required Recovery</p>
              <p className="text-[22px] leading-[28px] font-bold mt-2">{recovery}</p>
              <p className="caption-mono text-[var(--text-muted)] mt-3">{detail}</p>
              <div className="flex flex-wrap gap-2 mt-4">
                <button type="button" onClick={onRetry} className="industrial-control status-warning">Retry Runtime</button>
                {!operatorView && <Link to="/studio" className="industrial-control inline-flex">Open Studio</Link>}
              </div>
            </div>
          </div>
        </section>
        <aside className="hmi-dock">
          {operatorView ? (
            <DockSection title="Operator Continuity" eyebrow="Runtime Support">
              <ValueList values={[
                'Use existing HMI/DCS indications until this display recovers.',
                'Do not change blocked decisions from ConfidenceOS during this state.',
                'Notify Engineering if retry does not restore the operating view.',
              ]} />
            </DockSection>
          ) : (
            <DockSection title="Likely Causes" eyebrow="Runtime Support">
              <ValueList values={[
                'Backend API unavailable or restarting.',
                'SQLite persistence lock is delaying API response.',
                'Generated manifest hydration raised an exception.',
              ]} />
            </DockSection>
          )}
          <DockSection title="Read-Only Boundary">
            <p className="caption-mono text-[var(--text-muted)]">
              {operatorView
                ? 'ConfidenceOS has not written any control command. This state only means the operating view cannot be loaded.'
                : 'ConfidenceOS has not written any control command. This state only means the generated display cannot be loaded.'}
            </p>
          </DockSection>
        </aside>
      </div>
    </div>
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
    readings,
    confidence,
    incidents,
    handoverDebt,
    confidenceDebt,
    verificationTasks,
    demoState,
    chartHistory,
    massBalance,
    providerType,
  } = storeState;
  const isSimulation = providerType === 'simulator';
  const [manifest, setManifest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [manifestError, setManifestError] = useState('');
  const [retryToken, setRetryToken] = useState(0);
  const [selected, setSelected] = useState('');
  const [demoBusy, setDemoBusy] = useState(false);
  const [localDemoState, setLocalDemoState] = useState(null);

  useEffect(() => {
    connect();
  }, [connect]);

  useEffect(() => {
    let active = true;
    let inFlight = false;
    let currentController = null;
    const load = () => {
      if (inFlight) return;
      inFlight = true;
      const controller = new AbortController();
      currentController = controller;
      const timeout = setTimeout(() => controller.abort(), 8000);
      apiFetch(`/api/screens/generated?role=${role}&context=auto&plant_id=${plantId}`, { signal: controller.signal })
        .then(async (res) => {
          const payload = await res.json().catch(() => null);
          if (!res.ok) {
            throw new Error(payload?.detail || `Runtime manifest request failed: ${res.status}`);
          }
          if (!payload) {
            throw new Error('Runtime manifest response was empty.');
          }
          return payload;
        })
        .then((payload) => {
          if (active) {
            setManifest(payload);
            setManifestError('');
            setLoading(false);
          }
        })
        .catch((err) => {
          if (active) {
            setManifestError(
              err.name === 'AbortError'
                ? 'Runtime manifest request timed out after 8 seconds.'
                : err.message || 'Runtime manifest request failed.',
            );
            setLoading(false);
          }
        })
        .finally(() => {
          clearTimeout(timeout);
          inFlight = false;
          if (currentController === controller) {
            currentController = null;
          }
        });
    };
    load();
    const timer = setInterval(load, 2500);
    return () => {
      active = false;
      clearInterval(timer);
      if (currentController) {
        currentController.abort();
      }
    };
  }, [plantId, role, retryToken]);

  const faceplates = useMemo(() => manifest?.faceplates || [], [manifest]);
  const selectedFaceplate = useMemo(
    () => faceplates.find((item) => item.equipment_id === selected) || faceplates[0],
    [faceplates, selected],
  );
  const situations = useMemo(
    () => (manifest?.situations?.length ? manifest.situations : incidents || []),
    [manifest, incidents],
  );
  const pressureContext = manifest?.stress_mode
    || ['WARNING', 'CRITICAL'].includes(String(plantContext?.severity || '').toUpperCase())
    || ['WARNING', 'CRITICAL', 'MASS_BALANCE_DIVERGENCE', 'MANUAL_VERIFICATION_REQUIRED'].includes(String(manifest?.context || '').toUpperCase());
  const operatorView = isOperatorRole(role);
  const stressMode = operatorView && pressureContext;
  const activeDemoState = localDemoState || demoState || manifest?.demo_state;

  const runDemoAction = async (path) => {
    setDemoBusy(true);
    try {
      const res = await apiFetch(`${path}?plant_id=${plantId}`, { method: 'POST' });
      const payload = await res.json().catch(() => null);
      if (!res.ok) throw new Error(payload?.detail || `Simulator action failed: ${res.status}`);
      setLocalDemoState(payload?.simulation_state || payload?.demo_state || payload || null);
      setRetryToken((value) => value + 1);
    } catch (err) {
      setManifestError(err.message || 'Simulator action failed.');
    } finally {
      setDemoBusy(false);
    }
  };

  if (loading && !manifest) {
    return (
      <div className="industrial-page p-8">
        <p className="caption-mono text-[var(--data-mono)]">Loading the trust-aware operator view...</p>
      </div>
    );
  }

  if (!manifest) {
    return (
      <RuntimeUnavailable
        error={manifestError}
        plantId={plantId}
        role={role}
        connected={connected}
        onRetry={() => {
          setLoading(true);
          setManifestError('');
          setRetryToken((value) => value + 1);
        }}
      />
    );
  }

  if (stressMode) {
    return (
      <PressureModeRuntime
        manifest={manifest}
        situations={situations}
        confidence={confidence}
        connected={connected}
        plantId={plantId}
        plantContext={plantContext}
        chartHistory={chartHistory}
        massBalance={massBalance}
        demoState={activeDemoState}
        demoBusy={demoBusy}
        onDemoReset={() => runDemoAction('/api/simulation/reset-source')}
        onDemoStart={() => runDemoAction('/api/simulation/start-abnormal-situation')}
        isSimulation={isSimulation}
        role={role}
      />
    );
  }

  return (
    <div className="industrial-page flex flex-col overflow-hidden">
      <PriorityBand />
      <div className="hmi-workplace flex-1">
        <HmiAlarmBand manifest={manifest} role={role} connected={connected} plantId={plantId} plantContext={plantContext} situation={situations[0]} />
        <div className="hmi-main-grid">
          <TrustMapEdgeNav
            navigation={manifest.navigation}
            faceplates={faceplates}
            selectedId={selectedFaceplate?.equipment_id}
            onSelect={setSelected}
            situations={situations}
            handoverDebt={handoverDebt}
          />
          <ProcessCanvas
            manifest={manifest}
            faceplates={faceplates}
            readings={readings}
            confidence={confidence}
            situations={situations}
            onSelect={setSelected}
            role={role}
            connected={connected}
          />
          <aside className="hmi-dock">
            {isSimulation && (
              <DockSection title="Simulation Controls" eyebrow="Training Source">
                <SimulationControlStrip
                  demoState={activeDemoState}
                  busy={demoBusy}
                  onReset={() => runDemoAction('/api/simulation/reset-source')}
                  onStart={() => runDemoAction('/api/simulation/start-abnormal-situation')}
                  role={role}
                />
              </DockSection>
            )}
            {manifest.runtime_notice && showEngineeringInternals(role) && (
              <DockSection
                title={manifest.runtime_preview ? 'Generated Preview' : 'Runtime Live Binding'}
                eyebrow={manifest.runtime_preview ? 'Metadata Only - No Live Tags' : 'Compiler Boundary'}
              >
                <p className="caption-mono status-warning">{manifest.runtime_notice}</p>
                {manifest.demo_alias_bindings?.length > 0 && showEngineeringInternals(role) && (
                  <ValueList
                    values={manifest.demo_alias_bindings.map((item) => `${item.target_tag} bound from ${item.source_tag}`)}
                    status="text-[var(--data-mono)]"
                  />
                )}
                <Link to="/studio" className="industrial-control inline-flex mt-2">Open Studio</Link>
              </DockSection>
            )}
            <DockSection title={selectedFaceplate?.title || selectedFaceplate?.equipment_id || 'Faceplate'} eyebrow="Fixed Faceplate Dock">
              {selectedFaceplate ? (
                <GeneratedFaceplate faceplate={selectedFaceplate} readings={readings} confidence={confidence} role={role} />
              ) : (
                <p className="caption-mono text-[var(--text-muted)]">No faceplate selected.</p>
              )}
            </DockSection>
            <RoleDock
              manifest={manifest}
              selectedFaceplate={selectedFaceplate}
              confidenceDebt={confidenceDebt}
              handoverDebt={handoverDebt}
              verificationTasks={verificationTasks}
              plantId={plantId}
            />
            {showEngineeringInternals(role) && (
              <DockSection title="Support Level" eyebrow="Level 4 Details">
                <p className="caption-mono text-[var(--text-muted)]">Screen receipts, assumptions, sensitivity, and audit views are support-level information.</p>
                <Link to="/studio" className="industrial-control inline-flex mt-2">Open Studio</Link>
              </DockSection>
            )}
          </aside>
        </div>
        <BottomStrip manifest={manifest} situations={situations} handoverDebt={handoverDebt} chartHistory={chartHistory} />
      </div>
    </div>
  );
}
