import { useEffect, useState } from 'react';
import useStore from '../store';

function tierClass(tier) {
  if (tier === 'CRITICAL') return 'status-critical';
  if (tier === 'LOW') return 'status-warning';
  if (tier === 'MEDIUM') return 'status-caution';
  return 'status-safe';
}

export default function ConfidenceDebtPanel({ compact = false }) {
  const { plantId, confidenceDebt } = useStore();
  const [items, setItems] = useState([]);

  useEffect(() => {
    fetch(`/api/confidence/debt/${plantId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((payload) => setItems(payload?.items || []))
      .catch(() => setItems([]));
  }, [plantId]);

  const sourceItems = confidenceDebt?.length ? confidenceDebt : items;
  const rows = [...sourceItems].sort((a, b) => (b.confidence_debt || 0) - (a.confidence_debt || 0));
  const body = (
    <div className="space-y-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
      {rows.slice(0, compact ? 4 : 8).map((item) => (
        <div key={item.sensor_id} className="bg-[var(--surface-panel)] p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="font-data text-[var(--text)]">{item.sensor_id}</p>
            <span className={tierClass(item.tier)}>{item.confidence_debt ?? 0}</span>
          </div>
          <p className="caption-mono text-[var(--data-mono)] mt-1">
            {item.seconds_below_high ?? 0}s below HIGH / {item.tier}
          </p>
          <p className="caption-mono text-[var(--text)] mt-1">
            {item.maintenance_priority || 'Routine monitoring; confidence debt remains low.'}
          </p>
        </div>
      ))}
      {rows.length === 0 && (
        <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">Confidence debt has not accumulated yet.</p>
      )}
    </div>
  );

  if (compact) return body;

  return (
    <section className="industrial-panel border-t-0">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Maintenance Priority</p>
          <h2 className="industrial-panel-title text-base">Confidence Debt</h2>
        </div>
      </div>
      <div className="industrial-body space-y-3">
        <p className="caption-mono text-[var(--data-mono)]">
          Time below confidence tier x criticality x active context. Used for maintenance operating priority.
        </p>
        {body}
      </div>
    </section>
  );
}
