/**
 * ComparisonPanel.jsx — the PRD "same reading, different trust" moment.
 *
 * Shows the SAME live level reading two ways, side by side:
 *   • Traditional HMI  — just the number; looks fine.
 *   • ConfidenceOS     — same number, but QUARANTINED, with confidence %,
 *                        the reason, the trusted substitute, and the physics gap.
 *
 * This is the Texas City contrast: a value that reads normal but should not be
 * trusted. Driven entirely by live data already in Runtime (confidence +
 * mass_balance), no new endpoint.
 */

function fmt(value, digits = 1) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '--';
}

export default function ComparisonPanel({ confidence = [], massBalance = {}, basis = {}, situation = {} }) {
  // Hero sensor = the quarantined one (PRD case), else the lowest non-HIGH.
  const ranked = [...confidence].sort((a, b) => (a.confidence_pct ?? 100) - (b.confidence_pct ?? 100));
  const hero =
    confidence.find((c) => c.trust_state === 'QUARANTINED') ||
    ranked.find((c) => c.tier && c.tier !== 'HIGH') ||
    null;

  if (!hero) {
    return (
      <div className="bg-[var(--surface-highest)] border border-[var(--border-strong)] p-4">
        <p className="label-caps text-[var(--text-muted)]">Traditional HMI vs ConfidenceOS</p>
        <p className="caption-mono status-safe mt-2">No active trust exception — both views agree the reading is usable.</p>
      </div>
    );
  }

  const sid = hero.sensor_id;
  const pct = Math.round(hero.confidence_pct ?? 0);
  const reason = hero.trust_reason || (hero.reasons || [])[0] || 'Independent evidence contradicts this reading.';
  const measured = massBalance?.measured_level;   // what the level sensor indicates
  const implied = massBalance?.implied_level;      // what the flow says it should be
  const hasReading = typeof measured === 'number' && Number.isFinite(measured);
  const substitute = (basis?.trusted_substitutes || situation?.action_contract?.trusted_substitutes || [])[0];
  const safeMove = basis?.operator_single_safe_move || situation?.action_contract?.first_safe_action;

  return (
    <div className="bg-[var(--surface-highest)] border-2 border-[var(--critical)] p-4">
      <p className="label-caps text-[var(--text-muted)]">Traditional HMI vs ConfidenceOS — {sid}</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-[2px] mt-3 bg-[var(--border-strong)] border border-[var(--border-strong)]">
        {/* Traditional HMI — looks fine */}
        <div className="bg-[var(--surface-base)] p-4">
          <p className="label-caps text-[var(--text-dim)]">Traditional HMI</p>
          <p className="text-[34px] leading-[40px] font-bold text-[var(--text)] mt-2 font-data">
            {hasReading ? `${fmt(measured)} ft` : '—'}
          </p>
          <p className="caption-mono status-safe mt-1">● Reading nominal</p>
          <p className="caption-mono text-[var(--text-muted)] mt-2">Shows the number. No way to know it is wrong.</p>
        </div>

        {/* ConfidenceOS — same number, different trust */}
        <div className="bg-[var(--surface-base)] p-4">
          <p className="label-caps text-[var(--text-dim)]">ConfidenceOS</p>
          <div className="flex items-baseline gap-2 mt-2">
            <p className="text-[34px] leading-[40px] font-bold text-[var(--text)] font-data">
              {hasReading ? `${fmt(measured)} ft` : '—'}
            </p>
            <span className="industrial-badge status-critical">{hero.trust_state || 'QUARANTINED'}</span>
          </div>
          <p className="caption-mono status-critical mt-1">Confidence {pct}% — do not use as decision basis</p>
          <p className="caption-mono text-[var(--text-muted)] mt-2">{reason}</p>
          {typeof implied === 'number' && (
            <p className="caption-mono status-warning mt-2">
              Physics implies ~{fmt(implied)} ft (gap {fmt(Math.abs((implied ?? 0) - (measured ?? 0)))} ft).
            </p>
          )}
          {substitute && (
            <p className="caption-mono status-safe mt-2">Use instead: {substitute}</p>
          )}
          {safeMove && (
            <p className="caption-mono font-semibold text-[var(--text)] mt-2">Safe move: {safeMove}</p>
          )}
        </div>
      </div>
    </div>
  );
}
