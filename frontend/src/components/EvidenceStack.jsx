const STATUS_CLASS = {
  OK: 'status-safe',
  DEGRADED: 'status-warning',
  BAD: 'status-critical',
  INFO: 'text-[var(--data-mono)]',
};

const FACTOR_LABELS = {
  calibration: 'Calibration',
  stability: 'Signal Stability',
  cross_sensor: 'Cross-Sensor Check',
  physical_plausibility: 'Physical Plausibility',
  none: 'No Dominant Weakness',
};

export default function EvidenceStack({ selectedSensorId, confidence, incidents }) {
  const selected = confidence.find((item) => item.sensor_id === selectedSensorId);
  const leadIncident = incidents?.[0];

  if (!selected) {
    return (
      <section className="industrial-panel border-t-0">
        <div className="industrial-panel-header">
          <h2 className="industrial-panel-title text-base">Evidence Stack</h2>
        </div>
        <div className="industrial-body">
          {leadIncident ? (
            <div className="industrial-panel-subtle p-4 border-[var(--warning)]">
              <p className="label-caps status-warning">Top Advisory</p>
              <p className="text-[var(--text)] font-bold mt-2">{leadIncident.title}</p>
              <p className="caption-mono text-[var(--data-mono)] mt-3">{leadIncident.first_action}</p>
            </div>
          ) : (
            <p className="caption-mono text-[var(--data-mono)]">Select a sensor to inspect confidence evidence.</p>
          )}
        </div>
      </section>
    );
  }

  const evidence = selected.evidence || [];
  const namurClass = selected.namur_state === 'FAILURE'
    ? 'status-critical'
    : selected.namur_state === 'OUT_OF_SPECIFICATION'
      ? 'status-warning'
      : selected.namur_state === 'MAINTENANCE_REQUIRED'
        ? 'status-caution'
        : 'status-safe';

  return (
    <section className="industrial-panel border-t-0">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">{selected.sensor_id}</p>
          <h2 className="industrial-panel-title text-base">Evidence Stack</h2>
        </div>
        <span className={`industrial-badge ${namurClass}`}>{selected.namur_state || 'NORMAL'}</span>
      </div>

      <div className="industrial-body space-y-4">
        <div className="industrial-grid-shell grid-cols-2">
          <div className="industrial-panel-subtle p-3">
            <p className="label-caps text-[var(--text-muted)]">Confidence</p>
            <p className={`font-data text-3xl font-bold ${namurClass}`}>{Math.round(selected.confidence_pct ?? 0)}%</p>
          </div>
          <div className="industrial-panel-subtle p-3">
            <p className="label-caps text-[var(--text-muted)]">Dominant Factor</p>
            <p className="caption-mono text-[var(--text)] mt-2">{FACTOR_LABELS[selected.dominant_factor] || selected.dominant_factor || 'Unknown'}</p>
          </div>
        </div>

        <div className="industrial-panel-subtle p-4 border-[var(--safe)]">
          <p className="label-caps status-safe">Recommended Action</p>
          <p className="caption-mono text-[var(--text)] mt-2">{selected.recommended_action || 'Review evidence before relying on this reading.'}</p>
        </div>

        <div className="space-y-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
          {evidence.map((item) => {
            const statusClass = STATUS_CLASS[item.status] || STATUS_CLASS.INFO;
            return (
              <div key={`${item.category}-${item.message}`} className="industrial-panel-subtle p-3 bg-[var(--surface-panel)]">
                <div className="flex items-center justify-between gap-3">
                  <span className="label-caps text-[var(--text)]">{FACTOR_LABELS[item.category] || item.category}</span>
                  <span className={`caption-mono ${statusClass}`}>{item.status}</span>
                </div>
                <p className="caption-mono text-[var(--data-mono)] mt-2">{item.message}</p>
                <p className="caption-mono text-[var(--text-muted)] mt-2">Action: {item.action}</p>
              </div>
            );
          })}
          {evidence.length === 0 && (
            <p className="industrial-panel-subtle p-3 caption-mono text-[var(--data-mono)]">No structured evidence reported yet.</p>
          )}
        </div>
      </div>
    </section>
  );
}
