import Panel from './Panel';
import { asList, statusClass } from './studioUtils';

function ReceiptPanel({ item, label }) {
  const receipt = item?.receipt || {};
  return (
    <div className="bg-[var(--surface-panel)] p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label-caps text-[var(--text-muted)]">{label}</p>
          <p className="caption-mono text-[var(--text)] mt-1 machine-token">{item?.generated_id}</p>
        </div>
        <span className={`industrial-badge ${statusClass(item?.validation_status)}`}>{item?.validation_status}</span>
      </div>
      <div className="grid grid-cols-2 gap-[1px] bg-[var(--border-strong)] mt-3">
        <p className="bg-[var(--surface-base)] p-2 caption-mono text-[var(--data-mono)] machine-token">Asset {item?.asset_id}</p>
        <p className="bg-[var(--surface-base)] p-2 caption-mono text-[var(--data-mono)] machine-token">Template {item?.template_id}</p>
        <p className="bg-[var(--surface-base)] p-2 caption-mono text-[var(--data-mono)] machine-token">Role {item?.role_policy}</p>
        <p className="bg-[var(--surface-base)] p-2 caption-mono text-[var(--data-mono)] machine-token">Context {item?.context_policy}</p>
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
      <p className="caption-mono text-[var(--data-mono)] mt-1 machine-token">{asList(receipt.source_files).join(' / ') || 'none listed'}</p>
    </div>
  );
}

export default function ScreenReceipts({ manifest }) {
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
