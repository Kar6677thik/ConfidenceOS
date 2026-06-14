import { useEffect, useState } from 'react';
import useStore from '../store';

function tierClass(tier) {
  if (tier === 'CRITICAL') return 'status-critical';
  if (tier === 'LOW') return 'status-warning';
  if (tier === 'MEDIUM') return 'status-caution';
  if (tier === 'HIGH') return 'status-safe';
  return 'text-[var(--data-mono)]';
}

function formatScenario(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export default function ScoreSensitivityPanel({ selectedSensorId }) {
  const { plantId, role } = useStore();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!selectedSensorId || role !== 'Engineer') {
      setData(null);
      return undefined;
    }

    let active = true;
    fetch(`/api/confidence/sensitivity/${selectedSensorId}?plant_id=${plantId}&role=${role}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Server responded ${res.status}`);
        return res.json();
      })
      .then((payload) => {
        if (active) {
          setData(payload);
          setError(null);
        }
      })
      .catch((err) => {
        if (active) {
          setData(null);
          setError(err.message);
        }
      });

    return () => {
      active = false;
    };
  }, [plantId, role, selectedSensorId]);

  if (role !== 'Engineer') return null;

  return (
    <section className="industrial-panel border-t-0">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Engineer View</p>
          <h2 className="industrial-panel-title text-base">Score Sensitivity</h2>
        </div>
      </div>
      <div className="industrial-body">
        {!selectedSensorId && (
          <p className="caption-mono text-[var(--data-mono)]">Select a sensor to inspect sensitivity.</p>
        )}
        {error && <p className="caption-mono status-critical">{error}</p>}
        {data?.baseline && (
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <span className="caption-mono text-[var(--data-mono)]">Baseline</span>
              <span className={`font-data text-xl font-bold ${tierClass(data.baseline.tier)}`}>
                {Math.round(data.baseline.confidence_pct)}% {data.baseline.tier}
              </span>
            </div>
            <div className="space-y-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
              {(data.scenarios || []).map((item) => (
                <div key={item.scenario} className="bg-[var(--surface-panel)] p-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="label-caps text-[var(--text)]">{formatScenario(item.scenario)}</p>
                    <span className={tierClass(item.tier)}>{item.confidence_pct}%</span>
                  </div>
                  <p className="caption-mono text-[var(--data-mono)] mt-1">
                    Delta {item.delta_pct > 0 ? '+' : ''}{item.delta_pct} pts if {formatScenario(item.ignored_factor)} is ignored.
                  </p>
                </div>
              ))}
            </div>
            <p className="caption-mono text-[var(--text-muted)]">{data.conclusion}</p>
          </div>
        )}
      </div>
    </section>
  );
}
