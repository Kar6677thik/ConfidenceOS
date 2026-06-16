/**
 * PageIdentity — consistent display name in a fixed position.
 *
 * ABB guideline: every display has a unique, unambiguous name in a stable
 * position with level/area context (4-level display hierarchy).
 */
export default function PageIdentity({ displayName, level, area, plant, className = '' }) {
  return (
    <div
      className={`flex items-baseline gap-3 px-5 py-2 border-b border-[var(--border)] bg-[var(--bg-low)] flex-shrink-0 ${className}`}
    >
      <span className="text-[17px] font-semibold text-[var(--text)] leading-tight">{displayName}</span>
      {level != null && (
        <span className="label-caps text-[var(--text-muted)]">L{level}</span>
      )}
      {area && (
        <span className="caption-mono text-[var(--text-dim)]">{area}</span>
      )}
      {plant && (
        <span className="caption-mono text-[var(--text-dim)]">· {plant}</span>
      )}
    </div>
  );
}
