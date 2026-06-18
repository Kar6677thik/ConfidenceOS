import Panel from './Panel';
import { formatText, statusClass } from './studioUtils';

export default function PublishGuardrails({ build, onPublish, busy, result }) {
  const blocking = build?.validation?.blocking || [];
  const grouped = Object.values(blocking.reduce((acc, item) => {
    const key = item.rule || 'blocking';
    if (!acc[key]) {
      acc[key] = { rule: key, items: [], message: item.message };
    }
    acc[key].items.push(item);
    return acc;
  }, {}));
  return (
    <Panel
      eyebrow="Publish Guardrails"
      title="Readiness Gate"
      right={<button disabled={busy || !build?.can_publish} onClick={onPublish} className="industrial-control status-safe disabled:opacity-40">Publish Runtime</button>}
      className="mb-[1px]"
    >
      <div className="space-y-[1px] bg-[var(--border-strong)]">
        {grouped.length ? grouped.slice(0, 4).map((group) => (
          <div key={group.rule} className="bg-[var(--surface-panel)] p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="label-caps status-critical">{formatText(group.rule)}</p>
              <span className="industrial-badge status-critical">{group.items.length}</span>
            </div>
            <p className="caption-mono text-[var(--text)] mt-1">{group.message}</p>
            <p className="caption-mono text-[var(--data-mono)] mt-1 machine-token">
              {group.items.slice(0, 3).map((item) => [item.raw_tag, item.asset_id].filter(Boolean).join(' / ')).filter(Boolean).join(' ; ')}
              {group.items.length > 3 ? ` ; +${group.items.length - 3} more` : ''}
            </p>
          </div>
        )) : <p className="bg-[var(--surface-panel)] p-3 caption-mono status-safe">No blocking guardrails. Publish is enabled for the latest build.</p>}
        {grouped.length > 4 && (
          <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">
            {grouped.length - 4} additional blocker group(s) hidden from preview. Resolve Mapping Court items to clear publish.
          </p>
        )}
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
