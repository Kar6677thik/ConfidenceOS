import { useCallback } from 'react';

/**
 * StartupBanner — Module 5: Startup Mode Banner & Toggle
 *
 * Shows a prominent pulsing amber banner when startup mode is active,
 * lists stale reading flags with per-sensor acknowledge buttons,
 * and provides a toggle to switch between startup / normal mode.
 */

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Toggle switch with label */
function ModeToggle({ isActive, onToggle }) {
  const handleClick = useCallback(() => {
    onToggle?.(!isActive);
  }, [isActive, onToggle]);

  return (
    <button
      onClick={handleClick}
      className="
        group flex items-center gap-2.5 px-3 py-1.5 rounded-lg
        bg-gray-800/60 border border-gray-700/50
        hover:border-gray-600 transition-colors cursor-pointer
        focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500
      "
      aria-pressed={isActive}
      aria-label={isActive ? 'Deactivate startup mode' : 'Activate startup mode'}
    >
      {/* Toggle track */}
      <span
        className={`
          relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors duration-200
          ${isActive ? 'bg-amber-500' : 'bg-gray-600'}
        `}
      >
        {/* Toggle knob */}
        <span
          className={`
            inline-block h-4 w-4 rounded-full bg-white shadow-md
            transform transition-transform duration-200 mt-0.5
            ${isActive ? 'translate-x-4 ml-0.5' : 'translate-x-0.5'}
          `}
        />
      </span>
      <span className="text-xs font-medium text-gray-400 group-hover:text-gray-300">
        {isActive ? 'Startup' : 'Normal'}
      </span>
    </button>
  );
}

/** Single stale flag row with acknowledge button */
function StaleFlagItem({ flag, onAcknowledge }) {
  return (
    <li className="flex items-center justify-between gap-3 bg-gray-800/50 rounded-lg px-3 py-2 border border-gray-700/40">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-mono text-amber-300 truncate">
          {flag.sensorId ?? flag.id ?? 'Unknown sensor'}
        </p>
        {flag.message && (
          <p className="text-[11px] text-gray-500 mt-0.5 truncate">{flag.message}</p>
        )}
      </div>
      <button
        onClick={() => onAcknowledge?.(flag.sensorId ?? flag.id)}
        className="
          shrink-0 text-[11px] font-semibold px-3 py-1 rounded-md
          bg-amber-500/15 text-amber-400 border border-amber-500/30
          hover:bg-amber-500/25 hover:text-amber-300
          transition-colors cursor-pointer
          focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400
        "
      >
        Acknowledge
      </button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function StartupBanner({
  isActive = false,
  onToggle,
  staleFlags = [],
  onAcknowledge,
}) {
  // ── Active banner (Startup Mode ON) ────────────────────────────────────
  if (isActive) {
    return (
      <div className="w-full">
        {/* Pulsing amber banner */}
        <div
          className="
            relative overflow-hidden
            bg-amber-500/10 border border-amber-500/30
            rounded-2xl shadow-lg shadow-amber-500/5
            px-5 py-4
            animate-pulse
          "
          role="alert"
        >
          {/* Subtle glow effect behind text */}
          <div className="absolute inset-0 bg-gradient-to-r from-amber-500/5 via-transparent to-amber-500/5 pointer-events-none" />

          <div className="relative flex items-start justify-between gap-4">
            {/* Warning message */}
            <div className="flex-1 min-w-0">
              <p className="text-amber-400 font-bold text-sm leading-snug">
                ⚠ STARTUP MODE ACTIVE
              </p>
              <p className="text-amber-500/80 text-xs mt-1 leading-relaxed">
                Heightened scrutiny enabled. Verify flagged sensors before increasing load.
              </p>
            </div>

            {/* Toggle */}
            <ModeToggle isActive={isActive} onToggle={onToggle} />
          </div>
        </div>

        {/* Stale flags list */}
        {staleFlags.length > 0 && (
          <div className="mt-3 bg-gray-900/70 backdrop-blur-xl border border-gray-700/50 rounded-xl p-4">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 mb-2.5">
              Stale Reading Flags
              <span className="ml-1.5 text-amber-400">({staleFlags.length})</span>
            </h3>
            <ul className="space-y-2 max-h-48 overflow-y-auto pr-1">
              {staleFlags.map((flag, idx) => (
                <StaleFlagItem
                  key={flag.sensorId ?? flag.id ?? idx}
                  flag={flag}
                  onAcknowledge={onAcknowledge}
                />
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  // ── Inactive banner (Normal Mode) ──────────────────────────────────────
  return (
    <div
      className="
        w-full flex items-center justify-between gap-4
        bg-gray-900/50 backdrop-blur-xl border border-gray-700/40
        rounded-2xl px-5 py-3
      "
    >
      <div className="flex items-center gap-2.5">
        <span className="inline-block h-2 w-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50" />
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Normal Mode
        </span>
      </div>
      <ModeToggle isActive={isActive} onToggle={onToggle} />
    </div>
  );
}
