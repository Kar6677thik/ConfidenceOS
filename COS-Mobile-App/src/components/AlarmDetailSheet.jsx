import useStore from '../store';
import PriorityBadge from './PriorityBadge';

function timeAgo(ts) {
  const diff = Math.floor((Date.now() - ts) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m ago`;
}

const PROCEDURE = {
  P1: 'ISA-18.2 P1 (Critical): Acknowledge immediately, notify shift supervisor, initiate emergency checklist. Do not clear without root-cause confirmation.',
  P2: 'ISA-18.2 P2 (Warning): Acknowledge within 10 minutes, log in shift handover, schedule maintenance follow-up.',
  P3: 'ISA-18.2 P3 (Advisory): Review at next convenient opportunity. Document in shift notes.',
};

export default function AlarmDetailSheet({ alarm, onClose }) {
  const acknowledgeAlarm = useStore((s) => s.acknowledgeAlarm);

  const handleAck = () => {
    acknowledgeAlarm(alarm.id);
    onClose();
  };

  return (
    <>
      {/* Backdrop */}
      <div className="sheet-backdrop" onClick={onClose} />

      {/* Sheet */}
      <div className="bottom-sheet" role="dialog" aria-modal="true" aria-label="Alarm detail">
        <div className="sheet-handle" />

        <div className="sheet-header">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', fontFamily: 'ui-monospace, monospace' }}>
                {alarm.tag}
              </span>
              <PriorityBadge priority={alarm.priority} />
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.4 }}>
              {alarm.desc}
            </div>
          </div>
          <button className="sheet-close-btn" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="sheet-body">
          {/* Detail rows */}
          <div className="sheet-row">
            <span className="sheet-label">Area</span>
            <span className="sheet-value">{alarm.area}</span>
          </div>
          <div className="sheet-row">
            <span className="sheet-label">Priority</span>
            <span className="sheet-value">{alarm.priority} — {alarm.priority === 'P1' ? 'Critical' : alarm.priority === 'P2' ? 'Warning' : 'Advisory'}</span>
          </div>
          <div className="sheet-row">
            <span className="sheet-label">Raised</span>
            <span className="sheet-value">{timeAgo(alarm.raisedAt)} · {new Date(alarm.raisedAt).toLocaleTimeString()}</span>
          </div>
          <div className="sheet-row">
            <span className="sheet-label">Status</span>
            <span className="sheet-value" style={{ color: alarm.acked ? 'var(--safe)' : 'var(--alarm-p1)', fontWeight: 600 }}>
              {alarm.acked ? '✓ Acknowledged' : 'Unacknowledged'}
            </span>
          </div>

          {/* Procedure guidance */}
          <div className="sheet-procedure">
            <span style={{ fontWeight: 600, color: 'var(--primary)', display: 'block', marginBottom: 6, fontSize: 11, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
              Procedure Guidance
            </span>
            {PROCEDURE[alarm.priority]}
          </div>

          {/* Acknowledge button */}
          {!alarm.acked && (
            <button className="sheet-ack-btn" onClick={handleAck}>
              Acknowledge Alarm
            </button>
          )}

          {alarm.acked && (
            <div style={{ marginTop: 14, textAlign: 'center', fontSize: 13, color: 'var(--safe)', fontWeight: 600 }}>
              ✓ This alarm has been acknowledged
            </div>
          )}
        </div>
      </div>
    </>
  );
}
