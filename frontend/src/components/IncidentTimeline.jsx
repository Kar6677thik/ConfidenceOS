const EVENT_LABELS = {
  mode_detected: 'Startup / Mode Detected',
  confidence_degraded: 'Confidence Degraded',
  mass_balance_divergence: 'Mass-Balance Divergence Detected',
  action_contract_created: 'Action Contract Created',
  decision_freeze_created: 'Decision Freeze Created',
  handover_debt_created: 'Handover Debt Created',
  handover_debt: 'Handover Debt Created',
};

const EVENT_CLASS = {
  CRITICAL: 'status-critical',
  WARNING: 'status-warning',
  MEDIUM: 'status-caution',
  LOW: 'status-warning',
  INFO: 'text-[var(--data-mono)]',
};

const EVENT_ORDER = [
  'mode_detected',
  'confidence_degraded',
  'mass_balance_divergence',
  'action_contract_created',
  'decision_freeze_created',
  'handover_debt_created',
  'handover_debt',
];

function eventClass(severity) {
  return EVENT_CLASS[severity] || EVENT_CLASS.INFO;
}

function formatTime(timestamp) {
  if (!timestamp) return 'live';
  const millis = timestamp > 10_000_000_000 ? timestamp : timestamp * 1000;
  return new Date(millis).toLocaleTimeString();
}

function eventRank(event) {
  const index = EVENT_ORDER.indexOf(event.event_type);
  return index === -1 ? EVENT_ORDER.length : index;
}

function normalizeEvents(events = []) {
  return [...events]
    .filter((event) => event && (EVENT_LABELS[event.event_type] || event.event_type))
    .sort((a, b) => {
      const rankDelta = eventRank(a) - eventRank(b);
      if (rankDelta !== 0) return rankDelta;
      return (b.timestamp || 0) - (a.timestamp || 0);
    });
}

export default function IncidentTimeline({ events = [], compact = false }) {
  const rows = normalizeEvents(events);

  if (rows.length === 0) {
    return (
      <section className={compact ? '' : 'industrial-panel border-t-0'}>
        {!compact && (
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">Incident Timeline</h2>
          </div>
        )}
        <div className={compact ? '' : 'industrial-body'}>
          <p className="caption-mono text-[var(--data-mono)]">No decision-integrity timeline events yet.</p>
        </div>
      </section>
    );
  }

  const body = (
    <div className="space-y-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
      {rows.slice(0, compact ? 8 : 12).map((event) => {
        const cls = eventClass(event.severity);
        const details = event.details || {};
        const exitConditions = details.exit_conditions || details.action_contract?.exit_conditions || [];
        return (
          <div key={event.event_id || `${event.event_type}-${event.subject}`} className="bg-[var(--surface-panel)] p-3">
            <div className="flex items-center justify-between gap-3">
              <p className={`label-caps ${cls}`}>{EVENT_LABELS[event.event_type] || event.event_type}</p>
              <span className="caption-mono text-[var(--data-mono)]">{formatTime(event.timestamp)}</span>
            </div>
            <p className="caption-mono text-[var(--text)] mt-1">{event.message || event.subject}</p>
            {!!details.rule_id && <p className="caption-mono text-[var(--data-mono)] mt-1">Rule: {details.rule_id}</p>}
            {!!details.decision && <p className="caption-mono text-[var(--data-mono)] mt-1">Frozen: {details.decision}</p>}
            {!!exitConditions.length && (
              <p className="caption-mono text-[var(--data-mono)] mt-1">Exit: {exitConditions.slice(0, 2).join(' / ')}</p>
            )}
          </div>
        );
      })}
    </div>
  );

  if (compact) return body;

  return (
    <section className="industrial-panel border-t-0">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Decision Integrity</p>
          <h2 className="industrial-panel-title text-base">Incident Timeline</h2>
        </div>
        <span className="industrial-badge text-[var(--data-mono)]">{rows.length}</span>
      </div>
      <div className="industrial-body">{body}</div>
    </section>
  );
}
