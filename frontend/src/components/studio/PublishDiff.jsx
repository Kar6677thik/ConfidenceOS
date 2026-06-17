import Panel from './Panel';
import { formatText, statusClass } from './studioUtils';

export default function PublishDiff({ diff }) {
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
