import Panel from './Panel';
import { formatText, statusClass } from './studioUtils';

function nextAction(row) {
  const bucket = String(row?.bucket || '').toLowerCase();
  if (bucket === 'mapped') return 'Approved. Run build to validate.';
  if (bucket === 'ignored') return 'Ignored with engineering reason.';
  if (bucket === 'ambiguous') return 'Select row: approve, manual-map, or keep blocking.';
  if (bucket === 'unmapped') return 'Select row: manual-map to a known signal or ignore with reason.';
  if (row?.blocking || bucket === 'blocking') return 'Select row: resolve in Mapping Court before publish.';
  return 'Select row for Mapping Court evidence.';
}

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
              <p className="caption-mono text-[var(--data-mono)] machine-token">
                {row.bucket === 'mapped'
                  ? (row.proposed_canonical_tag || '—')
                  : row.bucket === 'ignored'
                  ? '—'
                  : (row.proposed_canonical_tag || 'no match found')}
              </p>
              <p className="label-caps text-[var(--text-muted)] mt-1">
                {row.bucket === 'mapped' ? 'approved mapping' : row.bucket === 'ignored' ? 'ignored' : 'suggested mapping'}
              </p>
              {row.bucket !== 'mapped' && row.bucket !== 'ignored' && (
                <p className="caption-mono text-[var(--text-muted)] mt-2">{nextAction(row)}</p>
              )}
            </div>
            <div className="bg-[var(--surface-panel)] p-3">
              <p className={`caption-mono ${row.blocking ? 'status-critical' : statusClass(row.bucket)}`}>{formatText(row.bucket)}</p>
              <p className="label-caps text-[var(--text-muted)] mt-1">court verdict</p>
            </div>
          </button>
        ))}
      </div>
    </Panel>
  );
}
