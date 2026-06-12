import { useMemo } from 'react';

/**
 * FlagBar — Bottom bar showing all active alerts sorted by severity.
 *
 * Sources:
 *   - Mass-balance flags (from WebSocket mass_balance.flags)
 *   - Low-confidence sensors (below HIGH tier)
 *   - Stale reading flags (from stale_flags)
 *
 * Sorted: CRITICAL → WARNING → INFO
 */

const SEVERITY_ORDER = { CRITICAL: 0, WARNING: 1, LOW: 1, INFO: 2 };

const SEVERITY_STYLES = {
  CRITICAL: 'bg-red-500/15 text-red-400 border-red-500/30',
  WARNING:  'bg-amber-500/15 text-amber-400 border-amber-500/30',
  LOW:      'bg-orange-500/15 text-orange-400 border-orange-500/30',
  INFO:     'bg-blue-500/15 text-blue-400 border-blue-500/30',
  MEDIUM:   'bg-amber-500/15 text-amber-400 border-amber-500/30',
};

export default function FlagBar({ confidence, massBalance, staleFlags }) {
  const allFlags = useMemo(() => {
    const flags = [];

    // Mass-balance flags
    const mbFlags = massBalance?.flags || [];
    for (const f of mbFlags) {
      flags.push({
        id: `mb-${f.severity}`,
        severity: f.severity,
        source: 'MASS-BAL',
        message: f.message || `Discrepancy: ${f.discrepancy?.toFixed(1)} ft`,
      });
    }

    // Low-confidence sensors (not HIGH)
    const confList = confidence || [];
    for (const c of confList) {
      if (c.tier && c.tier !== 'HIGH') {
        const reason = c.reasons?.[0] || `Confidence: ${c.confidence_pct?.toFixed(0)}%`;
        flags.push({
          id: `conf-${c.sensor_id}`,
          severity: c.tier,
          source: c.sensor_id,
          message: reason,
        });
      }
    }

    // Stale readings
    const stale = staleFlags || [];
    for (const sf of stale) {
      flags.push({
        id: `stale-${sf.sensor_id}`,
        severity: 'WARNING',
        source: sf.sensor_id,
        message: `Stale reading: unchanged for ${sf.duration_seconds?.toFixed(0) ?? '?'}s`,
      });
    }

    // Sort by severity (CRITICAL first)
    flags.sort((a, b) => {
      return (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99);
    });

    return flags;
  }, [confidence, massBalance, staleFlags]);

  if (allFlags.length === 0) {
    return (
      <div className="bg-gray-900/50 backdrop-blur-xl border border-gray-700/40 rounded-2xl px-5 py-3">
        <div className="flex items-center gap-2.5">
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50" />
          <span className="text-xs font-medium text-gray-500">
            No active flags — all systems nominal
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900/50 backdrop-blur-xl border border-gray-700/40 rounded-2xl px-4 py-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
          Active Flags
        </span>
        <span className="text-[10px] font-bold text-red-400">
          ({allFlags.length})
        </span>
      </div>

      <div className="flex flex-wrap gap-2 max-h-20 overflow-y-auto scrollbar-thin">
        {allFlags.map((flag) => {
          const style = SEVERITY_STYLES[flag.severity] || SEVERITY_STYLES.INFO;
          return (
            <div
              key={flag.id}
              className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs ${style}`}
            >
              <span className="font-bold shrink-0">{flag.severity}</span>
              <span className="font-mono text-[10px] opacity-75 shrink-0">{flag.source}</span>
              <span className="truncate max-w-xs opacity-90">{flag.message}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
