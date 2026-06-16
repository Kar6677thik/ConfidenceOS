import { useEffect, useState } from 'react';
import useStore from '../store';

const TYPE_LABELS = {
  unresolved_incident: 'Unresolved Incident',
  active_decision_freeze: 'Active Decision Freeze',
  low_confidence_critical_sensor: 'Low-Confidence Critical Sensor',
  active_verification_token: 'Active Verification Token',
};

function severityClass(severity) {
  if (severity === 'CRITICAL') return 'status-critical';
  if (severity === 'LOW' || severity === 'WARNING') return 'status-warning';
  if (severity === 'MEDIUM') return 'status-caution';
  return 'text-[var(--data-mono)]';
}

export default function HandoverDebtLedger({ compact = false }) {
  const { plantId, handoverDebt } = useStore();
  const [debt, setDebt] = useState(null);

  useEffect(() => {
    fetch(`/api/handover/debt?plant_id=${plantId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setDebt)
      .catch(() => setDebt(null));
  }, [plantId]);

  const activeDebt = handoverDebt || debt;
  const entries = activeDebt?.entries || [];
  const body = (
    <div className="space-y-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
      {entries.slice(0, compact ? 5 : 10).map((item) => (
        <div key={item.id} className="bg-[var(--surface-panel)] p-3">
          <div className="flex items-center justify-between gap-3">
            <p className={`label-caps ${severityClass(item.severity)}`}>{TYPE_LABELS[item.type] || item.type}</p>
            <span className="caption-mono text-[var(--data-mono)]">handover</span>
          </div>
          <p className="caption-mono text-[var(--text)] mt-1">{item.title}</p>
          {!!item.required_action && (
            <p className="caption-mono text-[var(--data-mono)] mt-1">{item.required_action}</p>
          )}
          {item.confidence_debt != null && (
            <p className="caption-mono status-warning mt-1">Confidence debt {item.confidence_debt}</p>
          )}
        </div>
      ))}
      {entries.length === 0 && (
        <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">No unresolved handover debt.</p>
      )}
    </div>
  );

  if (compact) return body;

  return (
    <section className="industrial-panel border-t-0">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Operational Continuity</p>
          <h2 className="industrial-panel-title text-base">Handover Debt Ledger</h2>
        </div>
        <span className={`industrial-badge ${entries.length ? 'status-warning' : 'status-safe'}`}>{entries.length}</span>
      </div>
      <div className="industrial-body">{body}</div>
    </section>
  );
}
