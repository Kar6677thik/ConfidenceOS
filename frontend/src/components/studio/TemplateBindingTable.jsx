import Panel from './Panel';
import { asList, formatText, statusClass } from './studioUtils';
import DescribeAssetPanel from './DescribeAssetPanel';

export default function TemplateBindingTable({ validation, busy }) {
  const rows = validation?.items || [];
  return (
    <Panel eyebrow="Template Binding Table" title="Asset Template Validation" className="mb-[1px]">
      <DescribeAssetPanel busy={busy} />
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
