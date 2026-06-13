import { useMemo } from 'react';

const SEVERITY_ORDER = { CRITICAL: 0, WARNING: 1, LOW: 1, MEDIUM: 2, INFO: 3 };

const SEVERITY_CLASS = {
  CRITICAL: 'status-critical',
  WARNING: 'status-warning',
  LOW: 'status-warning',
  MEDIUM: 'status-caution',
  INFO: 'text-[var(--data-mono)]',
};

function fallbackIncidents(confidence = [], massBalance, staleFlags = []) {
  const incidents = [];
  const degraded = confidence.filter((item) => item.tier && item.tier !== 'HIGH');
  const mbFlags = massBalance?.flags || [];

  if (degraded.length || mbFlags.length) {
    const lead = [...degraded].sort((a, b) => (a.confidence_pct ?? 100) - (b.confidence_pct ?? 100))[0];
    const severity = mbFlags.some((flag) => flag.severity === 'CRITICAL') || lead?.tier === 'CRITICAL'
      ? 'CRITICAL'
      : mbFlags.length || lead?.tier === 'LOW'
        ? 'WARNING'
        : 'MEDIUM';
    incidents.push({
      incident_id: 'fallback-confidence',
      title: mbFlags.length ? 'Process integrity advisory' : 'Instrument confidence advisory',
      severity,
      affected_sensors: degraded.map((item) => item.sensor_id),
      summary: mbFlags[0]?.message || `${degraded.length} instrument(s) below HIGH confidence.`,
      first_action: lead?.recommended_action || 'Review degraded sensor evidence before relying on the value.',
      suggested_actions: ['Open evidence stack.', 'Compare adjacent tags.', 'Confirm field indication if needed.'],
    });
  }

  if (staleFlags.length) {
    incidents.push({
      incident_id: 'fallback-stale',
      title: 'Startup stale-reading verification',
      severity: 'WARNING',
      affected_sensors: staleFlags.map((flag) => flag.sensor_id ?? flag.sensorId ?? flag.id).filter(Boolean),
      summary: 'One or more startup readings are unchanged beyond the stale threshold.',
      first_action: 'Verify stale readings locally before accepting startup conditions.',
      suggested_actions: ['Confirm transmitter update at the field device.', 'Acknowledge only after verification.'],
    });
  }

  return incidents;
}

export default function IncidentQueue({ incidents, confidence, massBalance, staleFlags }) {
  const rows = useMemo(() => {
    const source = incidents?.length ? incidents : fallbackIncidents(confidence, massBalance, staleFlags);
    return [...source].sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99));
  }, [incidents, confidence, massBalance, staleFlags]);

  if (rows.length === 0) {
    return (
      <section className="industrial-panel px-4 py-3">
        <div className="flex items-center gap-3 caption-mono text-[var(--data-mono)]">
          <span className="led-square status-safe" />
          No active advisory incidents - operator action space is nominal
        </div>
      </section>
    );
  }

  return (
    <section className="industrial-panel">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Fused Incident Queue</p>
          <h2 className="industrial-panel-title">First-Action Advisories</h2>
        </div>
        <span className="industrial-badge status-warning">{rows.length}</span>
      </div>

      <div className="industrial-body space-y-[1px] bg-[var(--border-strong)]">
        {rows.map((incident) => {
          const statusClass = SEVERITY_CLASS[incident.severity] || SEVERITY_CLASS.INFO;
          return (
            <article key={incident.incident_id || incident.title} className="industrial-panel-subtle p-4 bg-[var(--surface-panel)]">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className={`label-caps ${statusClass}`}>{incident.severity || 'INFO'}</p>
                  <h3 className="text-lg font-bold text-[var(--text)] mt-1">{incident.title}</h3>
                </div>
                <span className="caption-mono text-[var(--data-mono)]">{incident.context || 'LIVE'}</span>
              </div>

              <p className="mt-3 text-[var(--text-muted)]">{incident.summary}</p>

              {!!incident.affected_sensors?.length && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {incident.affected_sensors.map((sensorId) => (
                    <span key={sensorId} className="industrial-badge text-[var(--data-mono)]">{sensorId}</span>
                  ))}
                </div>
              )}

              <div className="mt-4 border-l-2 border-[var(--safe)] pl-3">
                <p className="label-caps status-safe">First Action</p>
                <p className="caption-mono text-[var(--text)] mt-1">{incident.first_action}</p>
              </div>

              {!!incident.suggested_actions?.length && (
                <ul className="mt-3 space-y-1">
                  {incident.suggested_actions.slice(0, 3).map((action) => (
                    <li key={action} className="caption-mono text-[var(--data-mono)]">- {action}</li>
                  ))}
                </ul>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
