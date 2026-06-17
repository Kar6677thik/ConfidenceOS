import Panel from './Panel';
import { asList, formatText, statusClass } from './studioUtils';

export default function MappingCourt({
  item,
  aiLabel,
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
  const aiEvidence = asList(item?.ai_evidence);
  const aiCounterEvidence = asList(item?.ai_counter_evidence);
  const hasAiNarrative = !!item?.ai_narrative;
  const needsManualResolution = item && ['unmapped', 'ambiguous', 'blocking'].includes(String(item.bucket || '').toLowerCase());

  const displayLabel = aiLabel
    || (item?.ai_assisted
      ? 'Deterministic mapping active; AI explanation optional; engineer approval required'
      : 'Deterministic mapping active; AI explanation unavailable; engineer approval required');

  return (
    <Panel
      eyebrow="Mapping Court"
      title={item?.raw_tag || 'Select Raw Tag'}
      right={<span className={`industrial-badge ${item?.blocking ? 'status-critical' : statusClass(item?.bucket)}`}>{item?.blocking ? 'BLOCKING' : formatText(item?.bucket)}</span>}
      className="mb-[1px]"
    >
      <div className={`industrial-panel-subtle p-3 mb-4 ${item?.ai_assisted ? 'border-l-2 border-[var(--status-safe)]' : ''}`}>
        <p className="caption-mono text-[var(--text)]">{displayLabel}</p>
      </div>

      {hasAiNarrative && (
        <div className="mb-4 bg-[var(--surface-panel)] border border-[var(--border-strong)] p-3">
          <p className="label-caps text-[var(--text-muted)] mb-2">AI Explanation</p>
          <p className="caption-mono text-[var(--data-mono)]">{item.ai_narrative}</p>
          {(aiEvidence.length > 0 || aiCounterEvidence.length > 0) && (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-[1px] bg-[var(--border-strong)] mt-3">
              {aiEvidence.length > 0 && (
                <div className="bg-[var(--surface-base)] p-3">
                  <p className="label-caps status-safe">AI Evidence</p>
                  <ul className="mt-2 space-y-1">
                    {aiEvidence.map((entry) => <li key={entry} className="caption-mono text-[var(--data-mono)]">{entry}</li>)}
                  </ul>
                </div>
              )}
              {aiCounterEvidence.length > 0 && (
                <div className="bg-[var(--surface-base)] p-3">
                  <p className="label-caps status-warning">AI Counter-Evidence</p>
                  <ul className="mt-2 space-y-1">
                    {aiCounterEvidence.map((entry) => <li key={entry} className="caption-mono text-[var(--data-mono)]">{entry}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

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
