export function PanelSkeleton({ rows = 4 }) {
  return (
    <div className="p-4 space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-4 rounded bg-[var(--bg-elevated)]"
          style={{ width: `${85 - i * 10}%`, opacity: 0.6 - i * 0.1 }}
        />
      ))}
    </div>
  );
}

export function EmptyState({ icon = 'inbox', title, body }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 p-8 text-center">
      <span className="material-symbols-outlined text-[48px] text-[var(--border)]">{icon}</span>
      {title && <p className="text-[16px] font-semibold text-[var(--text-muted)]">{title}</p>}
      {body && <p className="caption-mono text-[var(--text-dim)] max-w-xs leading-relaxed">{body}</p>}
    </div>
  );
}

export function LoadFailed({ message, onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 p-6 text-center">
      <span className="material-symbols-outlined text-[36px] text-[var(--critical)]">cloud_off</span>
      <p className="caption-mono text-[var(--text-muted)]">
        {message || 'Data unavailable — check API connection.'}
      </p>
      {onRetry && (
        <button onClick={onRetry} className="industrial-control text-[var(--text-muted)] text-[12px] mt-1">
          Retry
        </button>
      )}
    </div>
  );
}
