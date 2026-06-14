function asList(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  if (value == null || value === '') return [];
  return [value];
}

function formatText(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function ReceiptSummary({ item }) {
  if (!item) return null;
  return (
    <div className="mt-3 border border-[var(--border-strong)] bg-[var(--surface-lowest)] p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="industrial-badge text-[var(--data-mono)]">{item.template_id || 'template'}</span>
        <span className="industrial-badge text-[var(--data-mono)]">v{item.template_version || '1.0'}</span>
        <span className="industrial-badge text-[var(--data-mono)]">{item.generated_id || item.build_id || 'generated'}</span>
      </div>
      <p className="caption-mono text-[var(--data-mono)] mt-2">
        generated from {asList(item.source_tags).slice(0, 5).join(', ') || 'asset model metadata'}
      </p>
    </div>
  );
}

export default function GenerationReceipt({ item, title = 'Screen Receipt', compact = false }) {
  if (!item) return null;
  const receipt = item.receipt || {};
  const generatedBecause = asList(receipt.generated_because);
  const warnings = asList(receipt.warnings);
  const sourceFiles = asList(receipt.source_files);

  return (
    <section className="border border-[var(--border-strong)] bg-[var(--surface-panel)] p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="label-caps text-[var(--text-muted)]">{title}</p>
          <h3 className="caption-mono text-[var(--text)] mt-1">{item.asset_id || item.screen_id || 'generated runtime object'}</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="industrial-badge text-[var(--data-mono)]">{item.template_id || 'template'}</span>
          <span className="industrial-badge text-[var(--data-mono)]">v{item.template_version || '1.0'}</span>
        </div>
      </div>

      {!compact && (
        <div className="mt-3 grid grid-cols-1 gap-[1px] bg-[var(--border-strong)]">
          <div className="bg-[var(--surface-base)] p-3">
            <p className="label-caps text-[var(--text-muted)]">Generated Because</p>
            {generatedBecause.length ? generatedBecause.map((itemText) => (
              <p key={itemText} className="caption-mono text-[var(--text)] mt-1">{itemText}</p>
            )) : <p className="caption-mono text-[var(--data-mono)] mt-1">No receipt reason supplied.</p>}
          </div>
          <div className="bg-[var(--surface-base)] p-3">
            <p className="label-caps text-[var(--text-muted)]">Warnings</p>
            {warnings.length ? warnings.map((warning) => (
              <p key={warning} className="caption-mono status-warning mt-1">{warning}</p>
            )) : <p className="caption-mono status-safe mt-1">No validation warning attached to this generated object.</p>}
          </div>
          <div className="bg-[var(--surface-base)] p-3">
            <p className="label-caps text-[var(--text-muted)]">Source</p>
            <p className="caption-mono text-[var(--data-mono)] mt-1">
              {sourceFiles.map(formatText).join(' / ') || 'Asset model and template library'}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
