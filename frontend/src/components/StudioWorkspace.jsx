import { useEffect, useMemo, useState } from 'react';
import useStore from '../store';

const STAGE_LABELS = {
  import: 'Import',
  mapping: 'Mapping',
  template_binding: 'Template Binding',
  validation: 'Validation',
  screen_generation: 'Screen Generation',
  publish_readiness: 'Publish Readiness',
  runtime: 'Runtime',
};

function formatText(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function statusClass(value) {
  const status = String(value || '').toUpperCase();
  if (['PASS', 'READY', 'PUBLISHED', 'VALID', 'APPROVED', 'IGNORED'].includes(status)) return 'status-safe';
  if (['WARNING', 'PASS_WITH_WARNINGS', 'WARNINGS'].includes(status)) return 'status-warning';
  if (['FAILED', 'BLOCKING', 'BLOCKED', 'NOT_READY', 'CRITICAL'].includes(status)) return 'status-critical';
  if (['NOT_RUN', 'LOADING'].includes(status)) return 'status-disabled';
  return 'text-[var(--data-mono)]';
}

function statusPip(value) {
  const status = String(value || '').toUpperCase();
  if (['PASS', 'READY', 'PUBLISHED', 'VALID', 'APPROVED', 'IGNORED'].includes(status)) return 'pip-ok';
  if (['WARNING', 'PASS_WITH_WARNINGS', 'WARNINGS'].includes(status)) return 'pip-warning';
  if (['FAILED', 'BLOCKING', 'BLOCKED', 'NOT_READY', 'CRITICAL'].includes(status)) return 'pip-critical';
  return '';
}

function asList(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  if (value == null || value === '') return [];
  return [value];
}

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(`Request failed: ${res.status}`);
    err.payload = payload;
    throw err;
  }
  return payload;
}

function Panel({ title, eyebrow, right, children, className = '' }) {
  return (
    <section className={`industrial-panel ${className}`}>
      <div className="industrial-panel-header">
        <div>
          {eyebrow && <p className="label-caps text-[var(--text-muted)]">{eyebrow}</p>}
          <h2 className="industrial-panel-title text-base">{title}</h2>
        </div>
        {right}
      </div>
      <div className="industrial-body">{children}</div>
    </section>
  );
}

function CompilerPipeline({ build }) {
  const stages = build?.stages || [
    { id: 'import', status: 'NOT_RUN' },
    { id: 'mapping', status: 'NOT_RUN' },
    { id: 'template_binding', status: 'NOT_RUN' },
    { id: 'validation', status: 'NOT_RUN' },
    { id: 'screen_generation', status: 'NOT_RUN' },
    { id: 'publish_readiness', status: 'NOT_RUN' },
  ];
  return (
    <Panel
      eyebrow="HMI Compiler Pipeline"
      title="Raw Tags To Runtime Build"
      right={<span className={`industrial-badge ${statusClass(build?.status || 'NOT_RUN')}`}>{build?.status || 'NOT_RUN'}</span>}
      className="mb-[1px]"
    >
      <div className="grid grid-cols-2 xl:grid-cols-6 gap-[1px] bg-[var(--border-strong)]">
        {stages.filter((stage) => stage.id !== 'runtime').map((stage) => (
          <div key={stage.id} className="bg-[var(--surface-panel)] p-3 min-h-[96px]">
            <div className="flex items-center justify-between gap-2">
              <span className={`status-pip ${statusPip(stage.status)}`} />
              <span className={`caption-mono ${statusClass(stage.status)}`}>{stage.status}</span>
            </div>
            <p className="label-caps text-[var(--text-muted)] mt-4">Stage</p>
            <p className="caption-mono text-[var(--text)] mt-1">{stage.label || STAGE_LABELS[stage.id] || formatText(stage.id)}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 grid grid-cols-1 xl:grid-cols-3 gap-[1px] bg-[var(--border-strong)]">
        <div className="bg-[var(--surface-panel)] p-3">
          <p className="label-caps text-[var(--text-muted)]">Build ID</p>
          <p className="caption-mono text-[var(--text)] mt-1">{build?.build_id || 'No build run yet'}</p>
        </div>
        <div className="bg-[var(--surface-panel)] p-3">
          <p className="label-caps text-[var(--text-muted)]">Publish Gate</p>
          <p className={`caption-mono mt-1 ${build?.can_publish ? 'status-safe' : 'status-critical'}`}>
            {build?.can_publish ? 'can publish latest build' : 'publish refused until blocking issues clear'}
          </p>
        </div>
        <div className="bg-[var(--surface-panel)] p-3">
          <p className="label-caps text-[var(--text-muted)]">Compiler Contract</p>
          <p className="caption-mono text-[var(--data-mono)] mt-1">read-only trust-aware HMI layer beside existing DCS/HMI</p>
          <p className="caption-mono text-[var(--text-muted)] mt-1">forbidden writes: tag values / setpoints / controller modes / DCS alarm acknowledgements</p>
        </div>
      </div>
    </Panel>
  );
}

function DirtyTagGauntlet({ court, selectedRawTag, onSelect }) {
  const counts = court?.counts || {};
  const rows = court?.items || [];
  const buckets = ['mapped', 'ambiguous', 'unmapped', 'ignored', 'blocking'];
  return (
    <Panel eyebrow="Dirty Tag Import Gauntlet" title="Imported Raw Tags" className="mb-[1px]">
      <div className="grid grid-cols-5 gap-[1px] bg-[var(--border-strong)] mb-4">
        {buckets.map((bucket) => (
          <div key={bucket} className="bg-[var(--surface-panel)] p-3">
            <p className="label-caps text-[var(--text-muted)]">{bucket}</p>
            <p className={`font-data text-2xl mt-1 ${bucket === 'blocking' && counts[bucket] ? 'status-critical' : 'status-safe'}`}>{counts[bucket] || 0}</p>
          </div>
        ))}
      </div>
      <div className="space-y-[1px] bg-[var(--border-strong)]">
        {rows.map((row) => (
          <button
            key={row.raw_tag}
            onClick={() => onSelect(row.raw_tag)}
            className={`w-full grid grid-cols-[1fr_1fr_105px] gap-[1px] text-left bg-[var(--border-strong)] ${selectedRawTag === row.raw_tag ? 'outline outline-1 outline-[var(--primary)]' : ''}`}
          >
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="caption-mono text-[var(--text)]">{row.raw_tag}</p>
              <p className="label-caps text-[var(--text-muted)] mt-1">raw tag</p>
            </div>
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="caption-mono text-[var(--data-mono)]">{row.proposed_canonical_tag || 'unresolved'}</p>
              <p className="label-caps text-[var(--text-muted)] mt-1">canonical mapping</p>
            </div>
            <div className="bg-[var(--surface-panel)] p-3">
              <p className={`caption-mono ${row.blocking ? 'status-critical' : statusClass(row.bucket)}`}>{formatText(row.bucket)}</p>
              <p className="label-caps text-[var(--text-muted)] mt-1">state</p>
            </div>
          </button>
        ))}
      </div>
    </Panel>
  );
}

function MappingCourt({
  item,
  assets = [],
  signals = [],
  signalRoles = [],
  ignoreReason,
  onIgnoreReason,
  manualCanonical,
  onManualCanonical,
  manualAsset,
  onManualAsset,
  manualRole,
  onManualRole,
  manualReason,
  onManualReason,
  onManualMap,
  onApprove,
  onIgnore,
  onKeepBlocking,
  busy,
  actionMessage,
}) {
  const evidence = asList(item?.evidence);
  const counterEvidence = asList(item?.counter_evidence);
  const needsManualResolution = item && ['unmapped', 'ambiguous', 'blocking'].includes(String(item.bucket || '').toLowerCase());
  return (
    <Panel
      eyebrow="Mapping Court"
      title={item?.raw_tag || 'Select Raw Tag'}
      right={<span className={`industrial-badge ${item?.blocking ? 'status-critical' : statusClass(item?.bucket)}`}>{item?.blocking ? 'BLOCKING' : formatText(item?.bucket)}</span>}
      className="mb-[1px]"
    >
      <div className="industrial-panel-subtle p-3 mb-4">
        <p className="caption-mono text-[var(--text)]">AI suggests when available; deterministic rule active; engineer approval required.</p>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-[1px] bg-[var(--border-strong)]">
        {[
          ['Proposed Canonical Tag', item?.proposed_canonical_tag || 'none'],
          ['Proposed Asset', item?.proposed_asset_id || 'none'],
          ['Proposed Signal Role', item?.proposed_role || 'none'],
          ['Suggestion Type', item?.suggestion_label || item?.suggestion_type || 'none'],
          ['Approval Required', item ? String(item.approval_required) : 'none'],
          ['Verdict', item?.verdict || 'none'],
        ].map(([label, value]) => (
          <div key={label} className="bg-[var(--surface-panel)] p-3">
            <p className="label-caps text-[var(--text-muted)]">{label}</p>
            <p className="caption-mono text-[var(--text)] mt-1">{value}</p>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-[1px] bg-[var(--border-strong)] mt-4">
        <div className="bg-[var(--surface-panel)] p-3">
          <p className="label-caps status-safe">Evidence</p>
          <ul className="mt-2 space-y-2">
            {evidence.length ? evidence.map((entry) => <li key={entry} className="caption-mono text-[var(--data-mono)]">{entry}</li>) : <li className="caption-mono text-[var(--data-mono)]">No supporting evidence.</li>}
          </ul>
        </div>
        <div className="bg-[var(--surface-panel)] p-3">
          <p className="label-caps status-warning">Counter-Evidence</p>
          <ul className="mt-2 space-y-2">
            {counterEvidence.length ? counterEvidence.map((entry) => <li key={entry} className="caption-mono text-[var(--data-mono)]">{entry}</li>) : <li className="caption-mono text-[var(--data-mono)]">No counter-evidence listed.</li>}
          </ul>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-1 xl:grid-cols-[1fr_140px_140px_140px] gap-[1px] bg-[var(--border-strong)]">
        <div className="bg-[var(--surface-panel)] p-3">
          <label className="label-caps text-[var(--text-muted)]" htmlFor="ignore-reason">Ignored Reason</label>
          <input
            id="ignore-reason"
            value={ignoreReason}
            onChange={(event) => onIgnoreReason(event.target.value)}
            className="industrial-input mt-2"
            placeholder="Engineering reason required"
          />
        </div>
        <div className="bg-[var(--surface-panel)] p-3 flex items-center">
          <button disabled={busy || !item?.proposed_canonical_tag} onClick={onApprove} className="industrial-control status-safe w-full disabled:opacity-40">Approve Mapping</button>
        </div>
        <div className="bg-[var(--surface-panel)] p-3 flex items-center">
          <button disabled={busy || !item} onClick={onIgnore} className="industrial-control status-warning w-full disabled:opacity-40">Mark Ignored</button>
        </div>
        <div className="bg-[var(--surface-panel)] p-3 flex items-center">
          <button disabled={busy || !item} onClick={onKeepBlocking} className="industrial-control status-critical w-full disabled:opacity-40">Keep Blocking</button>
        </div>
      </div>
      {needsManualResolution && (
        <div className="mt-4 border border-[var(--border-strong)] bg-[var(--surface-base)] p-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="label-caps status-warning">Manual Mapping Workflow</p>
              <p className="caption-mono text-[var(--data-mono)] mt-1">Engineer-approved binding; removes ignored state and invalidates the previous build.</p>
            </div>
            <span className="industrial-badge text-[var(--data-mono)]">approval required</span>
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-4 gap-[1px] bg-[var(--border-strong)] mt-3">
            <div className="bg-[var(--surface-panel)] p-3">
              <label className="label-caps text-[var(--text-muted)]" htmlFor="manual-canonical">Canonical Signal</label>
              <select id="manual-canonical" value={manualCanonical} onChange={(event) => onManualCanonical(event.target.value)} className="industrial-input mt-2">
                <option value="">Select signal</option>
                {signals.map((signal) => (
                  <option key={signal.tag || signal.id} value={signal.tag || signal.id}>
                    {signal.tag || signal.id} - {formatText(signal.sensor_type || signal.role)}
                  </option>
                ))}
              </select>
            </div>
            <div className="bg-[var(--surface-panel)] p-3">
              <label className="label-caps text-[var(--text-muted)]" htmlFor="manual-asset">Asset</label>
              <select id="manual-asset" value={manualAsset} onChange={(event) => onManualAsset(event.target.value)} className="industrial-input mt-2">
                <option value="">Select asset</option>
                {assets.map((asset) => (
                  <option key={asset.asset_id} value={asset.asset_id}>
                    {asset.asset_id} - {formatText(asset.asset_type)}
                  </option>
                ))}
              </select>
            </div>
            <div className="bg-[var(--surface-panel)] p-3">
              <label className="label-caps text-[var(--text-muted)]" htmlFor="manual-role">Signal Role</label>
              <select id="manual-role" value={manualRole} onChange={(event) => onManualRole(event.target.value)} className="industrial-input mt-2">
                <option value="">Select role</option>
                {signalRoles.map((role) => (
                  <option key={role} value={role}>{formatText(role)}</option>
                ))}
              </select>
            </div>
            <div className="bg-[var(--surface-panel)] p-3 flex items-end">
              <button disabled={busy || !item || !manualCanonical || !manualAsset || !manualRole || !manualReason} onClick={onManualMap} className="industrial-control status-safe w-full disabled:opacity-40">Submit Manual Map</button>
            </div>
          </div>
          <div className="bg-[var(--surface-panel)] p-3 mt-[1px]">
            <label className="label-caps text-[var(--text-muted)]" htmlFor="manual-reason">Engineering Reason</label>
            <input
              id="manual-reason"
              value={manualReason}
              onChange={(event) => onManualReason(event.target.value)}
              className="industrial-input mt-2"
              placeholder="Why this raw tag belongs to this asset/signal"
            />
          </div>
        </div>
      )}
      {actionMessage && <p className="caption-mono text-[var(--data-mono)] mt-3">{actionMessage}</p>}
    </Panel>
  );
}

function TemplateBindingTable({ validation }) {
  const rows = validation?.items || [];
  return (
    <Panel eyebrow="Template Binding Table" title="Asset Template Validation" className="mb-[1px]">
      <div className="space-y-[1px] bg-[var(--border-strong)]">
        <div className="hidden xl:grid grid-cols-[120px_150px_1fr_1fr_1fr_120px] gap-[1px] bg-[var(--border-strong)]">
          {['Asset', 'Template', 'Required Signal Roles', 'Present Signal Roles', 'Missing Roles', 'Validation'].map((label) => (
            <p key={label} className="bg-[var(--surface-lowest)] p-3 label-caps text-[var(--text-muted)]">{label}</p>
          ))}
        </div>
        {rows.map((row) => (
          <div key={`${row.asset_id}-${row.template_id}`} className="grid grid-cols-1 xl:grid-cols-[120px_150px_1fr_1fr_1fr_120px] gap-[1px] bg-[var(--border-strong)]">
            <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--text)]">{row.asset_id}</p>
            <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">{row.template_id}</p>
            <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">{asList(row.required_signal_types).join(' / ') || 'none'}</p>
            <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">{asList(row.present_signal_types).join(' / ') || 'none'}</p>
            <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">{asList(row.missing_signal_types).join(' / ') || 'none'}</p>
            <p className={`bg-[var(--surface-panel)] p-3 caption-mono ${statusClass(row.status)}`}>{formatText(row.status)}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function TemplateTestSuite({ tests }) {
  const rows = tests?.tests || [];
  return (
    <Panel
      eyebrow="Template Test Suite"
      title="Deterministic Runtime Checks"
      right={<span className={`industrial-badge ${statusClass(tests?.status || 'NOT_RUN')}`}>{tests?.status || 'NOT_RUN'}</span>}
      className="mb-[1px]"
    >
      <div className="space-y-[1px] bg-[var(--border-strong)]">
        {rows.map((test) => (
          <div key={test.test_id} className="grid grid-cols-1 xl:grid-cols-[180px_110px_1fr] gap-[1px] bg-[var(--border-strong)]">
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="label-caps text-[var(--text-muted)]">{test.template_id}</p>
              <p className={`caption-mono mt-1 ${statusClass(test.status)}`}>{test.status}</p>
            </div>
            <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--text)]">{formatText(test.template_id)}</p>
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="caption-mono text-[var(--text)]">{formatText(test.test_id)}</p>
              <p className="caption-mono text-[var(--data-mono)] mt-1">{test.message}</p>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function PublishDiff({ diff }) {
  const rows = diff?.changes || [];
  return (
    <Panel
      eyebrow="Publish Preview Diff"
      title="Generated HMI Effects"
      right={<span className={`industrial-badge ${statusClass(diff?.status || 'NOT_RUN')}`}>{diff?.status || 'NOT_RUN'}</span>}
      className="mb-[1px]"
    >
      <div className="space-y-[1px] bg-[var(--border-strong)]">
        {rows.length ? rows.map((item, index) => (
          <div key={`${item.type}-${item.description || item.id || index}`} className="grid grid-cols-[150px_1fr] gap-[1px] bg-[var(--border-strong)]">
            <p className={`bg-[var(--surface-panel)] p-3 caption-mono ${item.type?.includes('blocked') ? 'status-critical' : item.type?.includes('warning') ? 'status-warning' : 'status-safe'}`}>{formatText(item.type)}</p>
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="caption-mono text-[var(--text)]">{item.description || item.title || item.id || 'Generated HMI change'}</p>
              {(item.asset_id || item.raw_tag || item.decision_id) && (
                <p className="caption-mono text-[var(--data-mono)] mt-1">{[item.asset_id, item.raw_tag, item.decision_id].filter(Boolean).join(' / ')}</p>
              )}
            </div>
          </div>
        )) : <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">No generated HMI diff yet. Run build.</p>}
      </div>
    </Panel>
  );
}

function PublishGuardrails({ build, onPublish, busy, result }) {
  const blocking = build?.validation?.blocking || [];
  return (
    <Panel
      eyebrow="Publish Guardrails"
      title="Readiness Gate"
      right={<button disabled={busy || !build?.can_publish} onClick={onPublish} className="industrial-control status-safe disabled:opacity-40">Publish Latest Build</button>}
      className="mb-[1px]"
    >
      <div className="space-y-[1px] bg-[var(--border-strong)]">
        {blocking.length ? blocking.map((item) => (
          <div key={`${item.rule}-${item.raw_tag || item.asset_id || item.message}`} className="bg-[var(--surface-panel)] p-3">
            <p className="label-caps status-critical">{formatText(item.rule || 'blocking')}</p>
            <p className="caption-mono text-[var(--text)] mt-1">{item.message}</p>
            {(item.raw_tag || item.asset_id) && <p className="caption-mono text-[var(--data-mono)] mt-1">{[item.raw_tag, item.asset_id].filter(Boolean).join(' / ')}</p>}
          </div>
        )) : <p className="bg-[var(--surface-panel)] p-3 caption-mono status-safe">No blocking guardrails. Publish is enabled for the latest build.</p>}
      </div>
      {result && (
        <div className="industrial-panel-subtle p-3 mt-4">
          <p className={`caption-mono ${statusClass(result.status || result.detail?.status)}`}>{result.status || result.detail?.status || 'publish result'}</p>
          <p className="caption-mono text-[var(--data-mono)] mt-1">{result.reason || result.detail?.reason || 'Latest publish action completed.'}</p>
        </div>
      )}
    </Panel>
  );
}

function RuntimePreview({ manifest }) {
  const screens = manifest?.screens || [];
  const faceplates = manifest?.faceplates || [];
  return (
    <Panel
      eyebrow="Generated Runtime Preview"
      title={manifest?.manifest_id || 'No Generated Manifest'}
      right={<span className="industrial-badge text-[var(--data-mono)]">{faceplates.length} faceplates</span>}
      className="mb-[1px]"
    >
      {manifest ? (
        <div className="space-y-4">
          <div>
            <p className="label-caps text-[var(--text-muted)]">Screens</p>
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-[1px] bg-[var(--border-strong)] mt-2">
              {screens.map((screen) => (
                <div key={screen.generated_id || screen.screen_id} className="bg-[var(--surface-panel)] p-3">
                  <p className="caption-mono text-[var(--text)]">{screen.title}</p>
                  <p className="caption-mono text-[var(--data-mono)] mt-1">{screen.sections?.join(' / ')}</p>
                </div>
              ))}
            </div>
          </div>
          <div>
            <p className="label-caps text-[var(--text-muted)]">Faceplates</p>
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-[1px] bg-[var(--border-strong)] mt-2">
              {faceplates.map((faceplate) => (
                <div key={faceplate.generated_id || faceplate.equipment_id} className="bg-[var(--surface-panel)] p-3">
                  <p className="label-caps status-safe">{faceplate.template_label}</p>
                  <p className="caption-mono text-[var(--text)] mt-1">{faceplate.title}</p>
                  <p className="caption-mono text-[var(--data-mono)] mt-1">{faceplate.signals?.map((signal) => signal.tag).join(' / ')}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <p className="caption-mono text-[var(--data-mono)]">Run a passing build to generate Runtime screens and faceplates.</p>
      )}
    </Panel>
  );
}

function ReceiptPanel({ item, label }) {
  const receipt = item?.receipt || {};
  return (
    <div className="bg-[var(--surface-panel)] p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="label-caps text-[var(--text-muted)]">{label}</p>
          <p className="caption-mono text-[var(--text)] mt-1">{item?.generated_id}</p>
        </div>
        <span className={`industrial-badge ${statusClass(item?.validation_status)}`}>{item?.validation_status}</span>
      </div>
      <div className="grid grid-cols-2 gap-[1px] bg-[var(--border-strong)] mt-3">
        <p className="bg-[var(--surface-base)] p-2 caption-mono text-[var(--data-mono)]">Asset {item?.asset_id}</p>
        <p className="bg-[var(--surface-base)] p-2 caption-mono text-[var(--data-mono)]">Template {item?.template_id}</p>
        <p className="bg-[var(--surface-base)] p-2 caption-mono text-[var(--data-mono)]">Role {item?.role_policy}</p>
        <p className="bg-[var(--surface-base)] p-2 caption-mono text-[var(--data-mono)]">Context {item?.context_policy}</p>
      </div>
      <p className="label-caps text-[var(--text-muted)] mt-3">Generated Because</p>
      <ul className="mt-2 space-y-1">
        {asList(receipt.generated_because).map((line) => <li key={line} className="caption-mono text-[var(--data-mono)]">{line}</li>)}
      </ul>
      {asList(receipt.warnings).length > 0 && (
        <>
          <p className="label-caps status-warning mt-3">Warnings</p>
          <ul className="mt-2 space-y-1">
            {asList(receipt.warnings).map((line) => <li key={line} className="caption-mono text-[var(--data-mono)]">{line}</li>)}
          </ul>
        </>
      )}
      <p className="label-caps text-[var(--text-muted)] mt-3">Source Files</p>
      <p className="caption-mono text-[var(--data-mono)] mt-1">{asList(receipt.source_files).join(' / ') || 'none listed'}</p>
    </div>
  );
}

function ScreenReceipts({ manifest }) {
  const receipts = [
    ...(manifest?.screens || []).map((item) => ({ label: 'Screen', item })),
    ...(manifest?.faceplates || []).map((item) => ({ label: 'Faceplate', item })),
    ...(manifest?.situations || []).map((item) => ({ label: 'Situation', item })),
    ...(manifest?.role_sections || []).map((item) => ({ label: 'Role Section', item })),
    ...(manifest?.stress_mode_panel ? [{ label: 'Stress-Mode Panel', item: manifest.stress_mode_panel }] : []),
  ].filter(({ item }) => item?.receipt);

  return (
    <Panel eyebrow="Screen Receipts" title="Generation Provenance">
      <div className="space-y-[1px] bg-[var(--border-strong)]">
        {receipts.length ? receipts.map(({ label, item }) => (
          <ReceiptPanel key={`${label}-${item.generated_id}`} label={label} item={item} />
        )) : <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">No generation receipts yet. Run a passing build.</p>}
      </div>
    </Panel>
  );
}

export default function StudioWorkspace() {
  const { role } = useStore();
  const [overview, setOverview] = useState(null);
  const [imported, setImported] = useState(null);
  const [build, setBuild] = useState(null);
  const [tests, setTests] = useState(null);
  const [court, setCourt] = useState(null);
  const [preview, setPreview] = useState(null);
  const [selectedRawTag, setSelectedRawTag] = useState('');
  const [ignoreReason, setIgnoreReason] = useState('');
  const [manualCanonical, setManualCanonical] = useState('');
  const [manualAsset, setManualAsset] = useState('');
  const [manualRole, setManualRole] = useState('');
  const [manualReason, setManualReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionMessage, setActionMessage] = useState('');
  const [publishResult, setPublishResult] = useState(null);

  const refresh = async () => {
    const [studio, importedSignals, buildPayload, testPayload, courtPayload] = await Promise.all([
      fetchJson('/api/studio'),
      fetchJson('/api/studio/imported-signals'),
      fetchJson('/api/studio/build'),
      fetchJson('/api/studio/template-tests'),
      fetchJson('/api/studio/mapping-court'),
    ]);
    setOverview(studio);
    setImported(importedSignals);
    setBuild(buildPayload);
    setTests(testPayload);
    setCourt(courtPayload);
    if (!selectedRawTag && courtPayload?.items?.length) {
      const first = courtPayload.items.find((item) => item.blocking) || courtPayload.items[0];
      setSelectedRawTag(first.raw_tag);
    }
  };

  useEffect(() => {
    refresh().catch(() => {
      setOverview(null);
      setImported(null);
      setBuild(null);
      setTests(null);
      setCourt(null);
    });
  }, []);

  const mappingItems = court?.items || build?.imported_tags?.items || imported?.raw_tags || [];
  const selectedItem = useMemo(
    () => mappingItems.find((item) => item.raw_tag === selectedRawTag) || mappingItems[0],
    [mappingItems, selectedRawTag],
  );
  const validation = build?.validation || overview?.validation?.compiler || overview?.validation || {};
  const runtimeManifest = (build?.generated_manifest && Object.keys(build.generated_manifest).length > 0)
    ? build.generated_manifest
    : preview;
  const graphSignals = overview?.graph?.signals || [];
  const graphAssets = (overview?.graph?.assets || overview?.assets || []).filter((asset) => ['process_vessel', 'valve', 'flow_pair', 'pump'].includes(asset.asset_type));
  const signalRoles = [...new Set(graphSignals.map((signal) => signal.role || signal.sensor_type).filter(Boolean))];

  useEffect(() => {
    if (!selectedItem) return;
    setManualCanonical(selectedItem.proposed_canonical_tag || '');
    setManualAsset(selectedItem.proposed_asset_id || '');
    setManualRole(selectedItem.proposed_role || '');
    setManualReason('');
  }, [selectedItem?.raw_tag]);

  const runAction = async (fn) => {
    setBusy(true);
    setActionMessage('');
    try {
      await fn();
      await refresh();
    } catch (err) {
      setActionMessage(err.payload?.detail?.reason || err.payload?.reason || err.message || 'Action failed.');
    } finally {
      setBusy(false);
    }
  };

  const runBuild = () => runAction(async () => {
    const payload = await fetchJson('/api/studio/build/run', { method: 'POST' });
    setBuild(payload);
    setPublishResult(null);
    setActionMessage(payload.can_publish ? 'Build passed with publish readiness.' : 'Build failed. Resolve blocking guardrails and run again.');
  });

  const generatePreview = () => runAction(async () => {
    const payload = await fetchJson('/api/studio/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role, context: 'auto' }),
    });
    setPreview(payload);
  });

  const publish = () => runAction(async () => {
    try {
      const payload = await fetchJson('/api/studio/publish', { method: 'POST' });
      setPublishResult(payload);
    } catch (err) {
      setPublishResult(err.payload?.detail || err.payload || { status: 'blocked', reason: err.message });
      throw err;
    }
  });

  const reset = () => runAction(async () => {
    await fetchJson('/api/studio/reset', { method: 'POST' });
    setPreview(null);
    setPublishResult(null);
    setIgnoreReason('');
    setSelectedRawTag('');
    setManualCanonical('');
    setManualAsset('');
    setManualRole('');
    setManualReason('');
  });

  const approveSelected = () => runAction(async () => {
    if (!selectedItem) return;
    const payload = await fetchJson('/api/studio/mapping-court/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_tag: selectedItem.raw_tag }),
    });
    setActionMessage(`${payload.mapping?.raw_tag || selectedItem.raw_tag} approved. Run build again.`);
  });

  const ignoreSelected = () => runAction(async () => {
    if (!selectedItem) return;
    const payload = await fetchJson('/api/studio/mapping-court/ignore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_tag: selectedItem.raw_tag, reason: ignoreReason }),
    });
    setActionMessage(`${payload.mapping?.raw_tag || selectedItem.raw_tag} ignored. Run build again.`);
  });

  const keepBlocking = () => runAction(async () => {
    if (!selectedItem) return;
    await fetchJson('/api/studio/mapping-court/keep-blocking', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_tag: selectedItem.raw_tag }),
    });
    setActionMessage(`${selectedItem.raw_tag} remains blocking. Publish stays disabled.`);
  });

  const manualMapSelected = () => runAction(async () => {
    if (!selectedItem) return;
    const payload = await fetchJson('/api/studio/mapping-court/manual-map', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_tag: selectedItem.raw_tag,
        canonical_tag: manualCanonical,
        asset_id: manualAsset,
        signal_role: manualRole,
        reason: manualReason,
      }),
    });
    setActionMessage(`${payload.mapping?.raw_tag || selectedItem.raw_tag} manually mapped. Run build again.`);
  });

  const switchAssetModel = (modelKey) => runAction(async () => {
    await fetchJson('/api/studio/asset-model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_key: modelKey }),
    });
    setPreview(null);
    setPublishResult(null);
    setSelectedRawTag('');
    setManualCanonical('');
    setManualAsset('');
    setManualRole('');
    setManualReason('');
    setActionMessage('Asset model switched. Run build to compile the selected model.');
  });

  const toggleVerificationMutation = (enabled) => runAction(async () => {
    await fetchJson('/api/studio/template-mutation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ require_manual_verification_when_level_quarantined: enabled }),
    });
    setPreview(null);
    setPublishResult(null);
    setActionMessage('Template mutation updated. Run build to see publish diff and receipts.');
  });

  return (
    <div className="industrial-page grid grid-cols-[380px_1fr_430px] gap-[1px] bg-[var(--border-strong)] overflow-hidden">
      <aside className="bg-[var(--surface-panel)] overflow-y-auto scrollbar-thin">
        <Panel
          eyebrow="ConfidenceOS Studio"
          title="HMI Compiler Controls"
          right={<span className={`industrial-badge ${busy ? 'status-warning' : 'status-safe'}`}>{busy ? 'working' : 'ready'}</span>}
          className="border-t-0"
        >
          <div className="space-y-3">
            <div>
              <label className="label-caps text-[var(--text-muted)]" htmlFor="asset-model-select">Asset Model</label>
              <select
                id="asset-model-select"
                value={overview?.selected_asset_model || overview?.state?.selected_asset_model || 'texas_city_vessel'}
                onChange={(event) => switchAssetModel(event.target.value)}
                className="industrial-input mt-2"
                disabled={busy}
              >
                {(overview?.asset_models || [
                  { key: 'texas_city_vessel', label: 'Texas City Demo Vessel' },
                  { key: 'pump_station', label: 'Pump Station Demo' },
                ]).map((model) => (
                  <option key={model.key} value={model.key}>{model.label}</option>
                ))}
              </select>
            </div>
            <div className="border border-[var(--border-strong)] bg-[var(--surface-base)] p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="label-caps text-[var(--text-muted)]">Controlled Template Mutation</p>
                  <p className="caption-mono text-[var(--text)] mt-1">Require manual verification when primary level is quarantined.</p>
                </div>
                <input
                  type="checkbox"
                  checked={!!(overview?.template_mutations || overview?.state?.template_mutations)?.require_manual_verification_when_level_quarantined}
                  onChange={(event) => toggleVerificationMutation(event.target.checked)}
                  disabled={busy}
                  className="mt-1"
                />
              </div>
            </div>
            <button onClick={runBuild} disabled={busy} className="industrial-control status-safe w-full disabled:opacity-40">Run Build</button>
            <button onClick={generatePreview} disabled={busy} className="industrial-control text-[var(--text)] w-full disabled:opacity-40">Generate Preview</button>
            <button onClick={publish} disabled={busy || !build?.can_publish} className="industrial-control status-warning w-full disabled:opacity-40">Publish Latest Build</button>
            <button onClick={reset} disabled={busy} className="industrial-control text-[var(--data-mono)] w-full disabled:opacity-40">Reset Demo Default</button>
          </div>
          <div className="industrial-panel-subtle p-3 mt-4">
            <p className="label-caps text-[var(--text-muted)]">Demo Loop</p>
            <p className="caption-mono text-[var(--data-mono)] mt-2">Run build / resolve dirty tag / run build again / publish latest build.</p>
          </div>
        </Panel>
        <DirtyTagGauntlet court={court} selectedRawTag={selectedItem?.raw_tag} onSelect={(tag) => { setSelectedRawTag(tag); setIgnoreReason(''); setActionMessage(''); }} />
        <Panel eyebrow="Imported Source" title="Read-Only Tag Provider">
          <div className="grid grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="label-caps text-[var(--text-muted)]">Asset Signals</p>
              <p className="font-data text-2xl status-safe mt-1">{imported?.signals?.length || 0}</p>
            </div>
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="label-caps text-[var(--text-muted)]">Raw Tags</p>
              <p className="font-data text-2xl status-safe mt-1">{mappingItems.length}</p>
            </div>
          </div>
          <p className="caption-mono text-[var(--data-mono)] mt-3">{imported?.source || 'Waiting for Studio import.'}</p>
        </Panel>
      </aside>

      <main className="bg-[var(--surface-base)] p-[1px] overflow-y-auto scrollbar-thin">
        <CompilerPipeline build={build} />
        <MappingCourt
          item={selectedItem}
          assets={graphAssets}
          signals={graphSignals}
          signalRoles={signalRoles}
          ignoreReason={ignoreReason}
          onIgnoreReason={setIgnoreReason}
          manualCanonical={manualCanonical}
          onManualCanonical={setManualCanonical}
          manualAsset={manualAsset}
          onManualAsset={setManualAsset}
          manualRole={manualRole}
          onManualRole={setManualRole}
          manualReason={manualReason}
          onManualReason={setManualReason}
          onManualMap={manualMapSelected}
          onApprove={approveSelected}
          onIgnore={ignoreSelected}
          onKeepBlocking={keepBlocking}
          busy={busy}
          actionMessage={actionMessage}
        />
        <TemplateBindingTable validation={validation} />
        <TemplateTestSuite tests={tests} />
        <PublishDiff diff={build?.publish_diff || overview?.diff?.compiler_publish_diff} />
        <RuntimePreview manifest={runtimeManifest} />
      </main>

      <aside className="bg-[var(--surface-panel)] overflow-y-auto scrollbar-thin">
        <PublishGuardrails build={build} onPublish={publish} busy={busy} result={publishResult} />
        <ScreenReceipts manifest={runtimeManifest} />
      </aside>
    </div>
  );
}
