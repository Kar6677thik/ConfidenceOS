import { useState } from 'react';
import useStore from '../store';
import AlarmCard from '../components/AlarmCard';
import AlarmDetailSheet from '../components/AlarmDetailSheet';

export default function AlarmsView() {
  const alarms         = useStore((s) => s.alarms);
  const acknowledgeAll = useStore((s) => s.acknowledgeAll);
  const [selected, setSelected] = useState(null);

  const unacked      = alarms.filter((a) => !a.acked);
  const criticalCount = unacked.filter((a) => a.priority === 'P1').length;

  const sorted = [
    ...alarms.filter((a) => !a.acked).sort((a, b) => {
      const order = { P1: 0, P2: 1, P3: 2 };
      return order[a.priority] - order[b.priority];
    }),
    ...alarms.filter((a) => a.acked),
  ];

  return (
    <div>
      {/* Summary strip */}
      <div className={`summary-strip ${unacked.length > 0 ? 'summary-strip-critical' : 'summary-strip-ok'}`}>
        <span style={{ flex: 1 }}>
          {unacked.length > 0
            ? `${unacked.length} Unacknowledged${criticalCount > 0 ? ` · ${criticalCount} Critical` : ''}`
            : 'All alarms acknowledged'}
        </span>
        {unacked.length > 1 && (
          <button
            onClick={acknowledgeAll}
            style={{
              fontSize: 11,
              fontWeight: 600,
              padding: '4px 10px',
              border: '1px solid var(--alarm-p1)',
              borderRadius: 'var(--radius-sm)',
              background: 'transparent',
              color: 'var(--alarm-p1)',
              flexShrink: 0,
            }}
          >
            Ack All
          </button>
        )}
      </div>

      {/* Swipe hint — shown only when there are unacked alarms */}
      {unacked.length > 0 && (
        <div className="alarm-swipe-hint">← swipe to acknowledge</div>
      )}

      {sorted.length === 0 ? (
        <div className="empty-state">
          <span className="empty-icon" style={{ color: 'var(--safe)' }}>✓</span>
          <span className="empty-label">No active alarms</span>
          <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>System operating normally</span>
        </div>
      ) : (
        <div style={{ paddingTop: 6 }}>
          {sorted.map((alarm) => (
            <AlarmCard key={alarm.id} alarm={alarm} onTap={setSelected} />
          ))}
        </div>
      )}

      {/* Alarm detail bottom sheet */}
      {selected && (
        <AlarmDetailSheet alarm={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
