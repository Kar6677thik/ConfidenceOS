import { useMemo } from 'react';

const SEVERITY_ORDER = { CRITICAL: 0, WARNING: 1, LOW: 1, MEDIUM: 1, INFO: 2 };

const SEVERITY_CLASS = {
  CRITICAL: 'status-critical',
  WARNING: 'status-warning',
  LOW: 'status-warning',
  MEDIUM: 'status-caution',
  INFO: 'text-[var(--data-mono)]',
};

export default function FlagBar({ confidence, massBalance, staleFlags }) {
  const allFlags = useMemo(() => {
    const flags = [];

    for (const flag of massBalance?.flags || []) {
      flags.push({
        id: `mb-${flag.severity}`,
        severity: flag.severity,
        source: 'MASS-BAL',
        message: flag.message || `Discrepancy: ${flag.discrepancy?.toFixed(1)} ft`,
      });
    }

    for (const item of confidence || []) {
      if (item.tier && item.tier !== 'HIGH') {
        flags.push({
          id: `conf-${item.sensor_id}`,
          severity: item.tier,
          source: item.sensor_id,
          message: item.reasons?.[0] || `Confidence: ${item.confidence_pct?.toFixed(0)}%`,
        });
      }
    }

    for (const flag of staleFlags || []) {
      const sensorId = flag.sensor_id ?? flag.sensorId ?? flag.id;
      flags.push({
        id: `stale-${sensorId}`,
        severity: 'WARNING',
        source: sensorId,
        message: `Stale reading: unchanged for ${flag.duration_seconds?.toFixed(0) ?? '?'}s`,
      });
    }

    return flags.sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99));
  }, [confidence, massBalance, staleFlags]);

  if (allFlags.length === 0) {
    return (
      <div className="industrial-panel px-4 py-3">
        <div className="flex items-center gap-3 caption-mono text-[var(--data-mono)]">
          <span className="led-square status-safe" />
          No active flags - all systems nominal
        </div>
      </div>
    );
  }

  return (
    <div className="industrial-panel px-4 py-3">
      <div className="flex items-center gap-3 mb-2">
        <span className="label-caps text-[var(--text-muted)]">Active Flags</span>
        <span className="industrial-badge status-critical">{allFlags.length}</span>
      </div>
      <div className="flex flex-wrap gap-2 max-h-20 overflow-y-auto scrollbar-thin">
        {allFlags.map((flag) => {
          const statusClass = SEVERITY_CLASS[flag.severity] || SEVERITY_CLASS.INFO;
          return (
            <div key={flag.id} className={`industrial-badge max-w-full ${statusClass}`}>
              <span>{flag.severity}</span>
              <span>{flag.source}</span>
              <span className="truncate max-w-xs normal-case font-normal">{flag.message}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
