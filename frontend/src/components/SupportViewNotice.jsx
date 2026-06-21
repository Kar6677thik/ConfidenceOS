export default function SupportViewNotice({
  title = 'Support View',
  status = 'support',
  source = 'live/support data',
  boundary = 'Runtime, Studio, and Shift Channel remain the primary ConfidenceOS demo path.',
}) {
  const tone = status === 'live'
    ? 'status-safe'
    : status === 'training' || status === 'limited'
    ? 'status-warning'
    : status === 'planned-boundary'
    ? 'status-critical'
    : 'text-[var(--data-mono)]';

  return (
    <section className="industrial-panel mb-[1px]">
      <div className="industrial-panel-header">
        <div className="min-w-0">
          <p className="label-caps text-[var(--text-muted)]">Secondary Support View</p>
          <h2 className="industrial-panel-title text-base truncate">{title}</h2>
        </div>
        <span className={`industrial-badge ${tone}`}>{status}</span>
      </div>
      <div className="industrial-body grid gap-2 xl:grid-cols-3">
        <div className="min-w-0">
          <p className="label-caps text-[var(--text-muted)]">Evidence Source</p>
          <p className="caption-mono text-[var(--text)] [overflow-wrap:anywhere]">{source}</p>
        </div>
        <div className="min-w-0">
          <p className="label-caps text-[var(--text-muted)]">Primary Path</p>
          <p className="caption-mono text-[var(--data-mono)]">{'Studio -> Runtime -> Shift Channel'}</p>
        </div>
        <div className="min-w-0">
          <p className="label-caps text-[var(--text-muted)]">Read-Only Boundary</p>
          <p className="caption-mono text-[var(--text)] [overflow-wrap:anywhere]">
            {boundary} ConfidenceOS does not replace DCS/HMI records or write control commands.
          </p>
        </div>
      </div>
    </section>
  );
}
