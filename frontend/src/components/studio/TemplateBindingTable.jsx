import Panel from './Panel';
import { asList, formatText, statusClass } from './studioUtils';
import DescribeAssetPanel from './DescribeAssetPanel';

function RoleList({ values, tone = 'text-[var(--data-mono)]' }) {
  const roles = asList(values);
  if (!roles.length) {
    return <p className="caption-mono text-[var(--text-muted)]">none</p>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {roles.map((role) => (
        <span key={role} className={`industrial-badge normal-case tracking-normal ${tone}`} title={role}>
          {formatText(role)}
        </span>
      ))}
    </div>
  );
}

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
            <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--text)] machine-token">{row.asset_id}</p>
            <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)] machine-token">{row.template_id}</p>
            <div className="bg-[var(--surface-panel)] p-3 min-w-0"><RoleList values={row.required_signal_types} /></div>
            <div className="bg-[var(--surface-panel)] p-3 min-w-0"><RoleList values={row.present_signal_types} tone="status-safe" /></div>
            <div className="bg-[var(--surface-panel)] p-3 min-w-0"><RoleList values={row.missing_signal_types} tone="status-warning" /></div>
            <p className={`bg-[var(--surface-panel)] p-3 caption-mono ${statusClass(row.status)}`}>{formatText(row.status)}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}
