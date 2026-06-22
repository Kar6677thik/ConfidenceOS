import useStore from '../store';
import IncidentCard from '../components/IncidentCard';

export default function IncidentsView() {
  const incidents = useStore((s) => s.incidents);
  const handoverDebt = useStore((s) => s.handoverDebt);

  const urgencyClass = (urgency) => {
    if (urgency === 'High') return 'urgency-high';
    if (urgency === 'Medium') return 'urgency-medium';
    return 'urgency-low';
  };

  return (
    <div>
      {/* Active Incidents */}
      <div className="section-label">
        Active Incidents ({incidents.length})
      </div>

      {incidents.length === 0 ? (
        <div className="empty-state">
          <span className="empty-icon" style={{ color: 'var(--safe)' }}>◉</span>
          <span className="empty-label">No active incidents</span>
        </div>
      ) : (
        incidents.map((incident) => (
          <IncidentCard key={incident.id} incident={incident} />
        ))
      )}

      {/* Handover Debt */}
      {handoverDebt.length > 0 && (
        <>
          <div className="section-label" style={{ marginTop: 8 }}>
            Handover Debt ({handoverDebt.length})
          </div>
          {handoverDebt.map((entry) => (
            <div key={entry.id} className="mobile-card">
              <div className="mobile-card-body">
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10, marginBottom: 6 }}>
                  <span style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.4, flex: 1 }}>
                    {entry.topic}
                  </span>
                  <span className={`urgency-badge ${urgencyClass(entry.urgency)}`}>
                    {entry.urgency}
                  </span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
                  From shift: {entry.fromShift}
                </div>
              </div>
            </div>
          ))}
        </>
      )}

      <div style={{ height: 8 }} />
    </div>
  );
}
