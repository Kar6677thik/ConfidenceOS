function durationLabel(openSince) {
  const diff = Math.floor((Date.now() - openSince) / 60000);
  if (diff < 60) return `${diff}m open`;
  return `${Math.floor(diff / 60)}h ${diff % 60}m open`;
}

export default function IncidentCard({ incident }) {
  const sevClass = incident.severity === 'High'
    ? 'severity-high'
    : incident.severity === 'Medium'
    ? 'severity-medium'
    : 'severity-low';

  return (
    <div className="incident-card">
      <div className="incident-card-top">
        <span className="incident-title">{incident.title}</span>
        <span className={`severity-badge ${sevClass}`}>{incident.severity}</span>
      </div>
      <div className="incident-meta">
        <span>{incident.area}</span>
        <span>·</span>
        <span>{durationLabel(incident.openSince)}</span>
      </div>
    </div>
  );
}
