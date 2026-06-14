import { useEffect, useState } from 'react';
import useStore from '../store';

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

function statusClass(status) {
  return STATUS_CLASS[status] || STATUS_CLASS.INFO;
}

function formatAssumptionId(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function CourtroomRow({ label, children, tone = 'text-[var(--text)]' }) {
  return (
    <div className="border-l-2 border-[var(--border-strong)] pl-3">
      <p className={`label-caps ${tone}`}>{label}</p>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function EvidenceLine({ item }) {
  if (!item) return <p className="caption-mono text-[var(--data-mono)]">No evidence reported.</p>;
  return (
    <div className="caption-mono">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[var(--text)]">{FACTOR_LABELS[item.category] || formatAssumptionId(item.category)}</span>
        <span className={statusClass(item.status)}>{item.status || item.severity || 'INFO'}</span>
      </div>
      <p className="text-[var(--data-mono)] mt-1">{item.message || 'No message provided.'}</p>
    </div>
  );
}

function ConfidenceCourtroom({ selected, explanation, loading }) {
  const evidence = explanation?.strongest_evidence || selected.evidence?.find((item) => item.status !== 'OK') || selected.evidence?.[0];
  const counterEvidence = explanation?.counter_evidence || selected.evidence?.filter((item) => item.status === 'OK').slice(0, 3) || [];
  const assumptions = explanation?.related_assumptions || [];
  const charge = selected.tier === 'HIGH'
    ? `${selected.sensor_id} is currently acceptable as a primary reference.`
    : `${selected.sensor_id} may be unreliable as a primary operating reference.`;

  return (
    <div className="border border-[var(--border-strong)] bg-[var(--surface-base)] p-4 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Confidence Courtroom</p>
          <h3 className="text-base font-bold text-[var(--text)] mt-1">Evidence Ledger</h3>
        </div>
        {loading && <span className="caption-mono text-[var(--data-mono)]">Loading explanation</span>}
      </div>

      <CourtroomRow label="Charge" tone={selected.tier === 'HIGH' ? 'status-safe' : 'status-warning'}>
        <p className="caption-mono text-[var(--text)]">{charge}</p>
      </CourtroomRow>

      <CourtroomRow label="Evidence" tone={evidence?.status === 'BAD' ? 'status-critical' : 'status-warning'}>
        <EvidenceLine item={evidence} />
      </CourtroomRow>

      <CourtroomRow label="Counter-Evidence" tone="status-safe">
        {counterEvidence.length ? (
          <div className="space-y-2">
            {counterEvidence.map((item) => (
              <EvidenceLine key={`${item.category}-${item.message}`} item={item} />
            ))}
          </div>
        ) : (
          <p className="caption-mono text-[var(--data-mono)]">No counter-evidence available.</p>
        )}
      </CourtroomRow>

      <CourtroomRow label="Verdict" tone={selected.tier === 'HIGH' ? 'status-safe' : 'status-warning'}>
        <p className="caption-mono text-[var(--text)]">
          {explanation?.verdict || selected.recommended_action || 'Review confidence evidence before relying on this reading.'}
        </p>
      </CourtroomRow>

      <CourtroomRow label="Required Action" tone="status-safe">
        <p className="caption-mono text-[var(--text)]">
          {explanation?.recommended_action || selected.recommended_action || 'Continue normal monitoring.'}
        </p>
      </CourtroomRow>

      <CourtroomRow label="Engineering Assumptions Used">
        {assumptions.length ? (
          <div className="space-y-2">
            {assumptions.slice(0, 6).map((item) => (
              <div key={item.assumption_id} className="caption-mono border-t border-[var(--border-strong)] pt-2 first:border-t-0 first:pt-0">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[var(--text)]">{formatAssumptionId(item.assumption_id)}</span>
                  <span className={item.review_required ? 'status-warning' : 'status-safe'}>
                    {item.confidence_impact || 'impact unknown'}
                  </span>
                </div>
                <p className="text-[var(--data-mono)] mt-1">
                  {String(typeof item.value === 'object' ? 'structured' : item.value)} {item.unit} / {item.owner_role}
                </p>
                <p className="text-[var(--text-muted)] mt-1">{item.source}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="caption-mono text-[var(--data-mono)]">Assumption links unavailable.</p>
        )}
      </CourtroomRow>
    </div>
  );
}

export default function EvidenceStack({ selectedSensorId, confidence, incidents }) {
  const plantId = useStore((state) => state.plantId);
  const [explanation, setExplanation] = useState(null);
  const [loading, setLoading] = useState(false);
  const selected = confidence.find((item) => item.sensor_id === selectedSensorId);
  const leadIncident = incidents?.[0];

  useEffect(() => {
    if (!selectedSensorId) {
      setExplanation(null);
      return undefined;
    }

    let active = true;
    setLoading(true);
    fetch(`/api/confidence/explain/${selectedSensorId}?plant_id=${plantId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((payload) => {
        if (active) setExplanation(payload);
      })
      .catch(() => {
        if (active) setExplanation(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [plantId, selectedSensorId]);

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
  const formulaTerms = explanation?.formula?.terms || [];
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

        <ConfidenceCourtroom selected={selected} explanation={explanation} loading={loading} />

        {explanation?.formula?.expression && (
          <div className="border border-[var(--border-strong)] bg-[var(--surface-base)] p-3">
            <p className="label-caps text-[var(--text-muted)]">Formula</p>
            <p className="caption-mono text-[var(--data-mono)] mt-2">{explanation.formula.expression}</p>
          </div>
        )}

        {!!formulaTerms.length && (
          <div className="border border-[var(--border-strong)] bg-[var(--surface-base)]">
            <div className="grid grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
              {formulaTerms.map((term) => (
                <div key={term.factor} className="bg-[var(--surface-panel)] p-3">
                  <p className="label-caps text-[var(--text-muted)]">{FACTOR_LABELS[term.factor] || formatAssumptionId(term.factor)}</p>
                  <p className="caption-mono text-[var(--text)] mt-2">
                    {Math.round((term.sub_score ?? 0) * 100)}% x {Math.round((term.weight ?? 0) * 100)}%
                  </p>
                  <p className="caption-mono text-[var(--data-mono)] mt-1">{term.contribution_pct ?? 0}% contribution</p>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
          {evidence.map((item) => {
            const itemStatusClass = statusClass(item.status);
            return (
              <div key={`${item.category}-${item.message}`} className="industrial-panel-subtle p-3 bg-[var(--surface-panel)]">
                <div className="flex items-center justify-between gap-3">
                  <span className="label-caps text-[var(--text)]">{FACTOR_LABELS[item.category] || item.category}</span>
                  <span className={`caption-mono ${itemStatusClass}`}>{item.status}</span>
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
