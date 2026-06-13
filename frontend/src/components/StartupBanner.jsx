import { useCallback } from 'react';

function ModeToggle({ isActive, onToggle }) {
  const handleClick = useCallback(() => {
    onToggle?.(!isActive);
  }, [isActive, onToggle]);

  return (
    <button
      onClick={handleClick}
      className={`industrial-control ${isActive ? 'status-warning' : 'status-safe'}`}
      aria-pressed={isActive}
      aria-label={isActive ? 'Deactivate startup mode' : 'Activate startup mode'}
    >
      {isActive ? 'Startup' : 'Normal'}
    </button>
  );
}

function StaleFlagItem({ flag, onAcknowledge }) {
  const sensorId = flag.sensor_id ?? flag.sensorId ?? flag.id;

  return (
    <li className="industrial-panel-subtle flex items-center justify-between gap-3 p-3">
      <div className="min-w-0">
        <p className="font-data status-warning truncate">{sensorId ?? 'UNKNOWN SENSOR'}</p>
        {flag.message && <p className="caption-mono text-[var(--data-mono)] truncate">{flag.message}</p>}
      </div>
      <button
        onClick={() => sensorId && onAcknowledge?.(sensorId)}
        className="industrial-control status-warning shrink-0"
      >
        Acknowledge
      </button>
    </li>
  );
}

export default function StartupBanner({
  isActive = false,
  onToggle,
  staleFlags = [],
  onAcknowledge,
}) {
  return (
    <section className={`industrial-panel ${isActive ? 'border-[var(--warning)]' : ''}`}>
      <div className="industrial-panel-header">
        <div className="flex items-center gap-3">
          <span className={`led-square ${isActive ? 'status-warning dot-blink' : 'status-safe'}`} />
          <div>
            <p className={`label-caps ${isActive ? 'status-warning' : 'status-safe'}`}>
              {isActive ? 'Startup Mode Active' : 'Normal Mode'}
            </p>
            <p className="caption-mono text-[var(--data-mono)]">
              {isActive ? 'Heightened scrutiny enabled. Verify flagged sensors before increasing load.' : 'Standard operating envelope active.'}
            </p>
          </div>
        </div>
        <ModeToggle isActive={isActive} onToggle={onToggle} />
      </div>

      {isActive && staleFlags.length > 0 && (
        <div className="industrial-body pt-3">
          <div className="flex items-center justify-between mb-3">
            <h3 className="label-caps text-[var(--text-muted)]">Stale Reading Flags</h3>
            <span className="industrial-badge status-warning">{staleFlags.length}</span>
          </div>
          <ul className="space-y-[1px] bg-[var(--border-strong)] max-h-48 overflow-y-auto scrollbar-thin border border-[var(--border-strong)]">
            {staleFlags.map((flag, index) => (
              <StaleFlagItem
                key={flag.sensor_id ?? flag.sensorId ?? flag.id ?? index}
                flag={flag}
                onAcknowledge={onAcknowledge}
              />
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
