export default function PriorityBadge({ priority }) {
  const cls = priority === 'P1' ? 'priority-p1' : priority === 'P2' ? 'priority-p2' : 'priority-p3';
  return <span className={`priority-badge ${cls}`}>{priority}</span>;
}
