import Panel from './Panel';
import { formatText, statusClass } from './studioUtils';

export default function DirtyTagGauntlet({ court, selectedRawTag, onSelect }) {
  const counts = court?.counts || {};
  const rows = court?.items || [];
  const buckets = ['mapped', 'ambiguous', 'unmapped', 'ignored', 'blocking'];
  return (
    <Panel eyebrow="Dirty Tag Import Gauntlet" title="Imported Raw Tags" className="mb-[1px]">
      <div className="industrial-panel-subtle p-3 mb-4">
        <p className="caption-mono text-[var(--text)]">
          {court?.raw_import_only
            ? 'Raw import only: canonical mappings are derived by Mapping Court from the active asset model.'
            : 'Legacy import shape detected: Mapping Court still re-derives suggestions before approval.'}
        </p>
      </div>
      <div className="overflow-x-auto overflow-y-hidden scrollbar-thin mb-4">
      <div className="grid min-w-[520px] grid-cols-5 gap-[1px] bg-[var(--border-strong)]">
        {buckets.map((bucket) => (
          <div key={bucket} className="bg-[var(--surface-panel)] p-3">
            <p className="label-caps text-[var(--text-muted)]">{bucket}</p>
            <p className={`font-data text-2xl mt-1 ${bucket === 'blocking' && counts[bucket] ? 'status-critical' : 'status-safe'}`}>{counts[bucket] || 0}</p>
          </div>
        ))}
      </div>
      </div>
      <div className="space-y-[1px] bg-[var(--border-strong)]">
        {rows.map((row) => (
          <button
            key={row.raw_tag}
            onClick={() => onSelect(row.raw_tag)}
            className={`w-full grid grid-cols-1 lg:grid-cols-[minmax(160px,1fr)_minmax(160px,1fr)_112px] gap-[1px] text-left bg-[var(--border-strong)] ${selectedRawTag === row.raw_tag ? 'outline outline-1 outline-[var(--primary)]' : ''}`}
          >
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="caption-mono text-[var(--text)] machine-token">{row.raw_tag}</p>
              <p className="label-caps text-[var(--text-muted)] mt-1">raw import row</p>
            </div>
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="caption-mono text-[var(--data-mono)] machine-token">{row.proposed_canonical_tag || 'unresolved'}</p>
              <p className="label-caps text-[var(--text-muted)] mt-1">derived suggestion</p>
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
