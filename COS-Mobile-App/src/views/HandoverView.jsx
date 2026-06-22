import { useState } from 'react';
import useStore from '../store';

const PIP_CLASS = { safe: 'pip-safe', warning: 'pip-warning', critical: 'pip-critical' };

const URGENCY_CLASS = {
  High:   { badge: 'urgency-badge urgency-high',   dot: 'var(--alarm-p1)' },
  Medium: { badge: 'urgency-badge urgency-medium',  dot: '#cc8800' },
  Low:    { badge: 'urgency-badge urgency-low',     dot: 'var(--safe)' },
};

export default function HandoverView() {
  const handoverData = useStore((s) => s.handoverData);
  const [showToast, setShowToast] = useState(false);

  const handleRecord = () => {
    setShowToast(true);
    setTimeout(() => setShowToast(false), 2200);
  };

  return (
    <div>
      {/* Shift meta bar */}
      <div className="handover-meta-bar">
        <span className="handover-shift-name">{handoverData.shift}</span>
        <span className="handover-meta-item">Supervisor: {handoverData.supervisor}</span>
        <span className="handover-meta-item" style={{ marginLeft: 'auto' }}>Start: {handoverData.startTime}</span>
      </div>

      {/* Open items */}
      <div className="section-label">Open Items ({handoverData.openItems.length})</div>
      <div className="mobile-card">
        <div className="mobile-card-body" style={{ padding: '4px 14px' }}>
          {handoverData.openItems.map((item, i) => (
            <div key={i} className="handover-open-item">
              <span className={URGENCY_CLASS[item.urgency].badge}>{item.urgency}</span>
              <span className="handover-open-text">{item.text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Equipment status */}
      <div className="section-label">Equipment Status</div>
      <div className="mobile-card">
        <div className="mobile-card-body" style={{ padding: '4px 14px' }}>
          {handoverData.equipmentStatus.map((eq) => (
            <div key={eq.tag} className="equipment-row">
              <span className={`status-pip ${PIP_CLASS[eq.status] ?? 'pip-offline'}`} />
              <span className="equipment-tag">{eq.tag}</span>
              <span className="equipment-area">{eq.area}</span>
              <span style={{ fontSize: 11, fontWeight: 600, color: eq.status === 'safe' ? 'var(--safe)' : eq.status === 'warning' ? '#cc8800' : 'var(--alarm-p1)', textTransform: 'capitalize' }}>
                {eq.status}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Notes */}
      <div className="section-label">Notes from Last Shift</div>
      <div className="mobile-card">
        <div className="mobile-card-body">
          <span className="handover-notes">{handoverData.notes}</span>
        </div>
      </div>

      {/* Record button */}
      <button className="handover-record-btn" onClick={handleRecord}>
        Record Handover
      </button>

      {showToast && (
        <div className="toast">Handover recording coming soon</div>
      )}
    </div>
  );
}
