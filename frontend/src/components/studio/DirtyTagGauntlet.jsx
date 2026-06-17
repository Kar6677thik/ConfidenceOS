import Panel from './Panel';
import { formatText, statusClass } from './studioUtils';

export default function DirtyTagGauntlet({ court, selectedRawTag, onSelect }) {
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
