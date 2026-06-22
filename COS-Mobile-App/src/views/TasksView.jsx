import { useState } from 'react';
import useStore from '../store';
import TaskCard from '../components/TaskCard';

const FILTERS = ['All', 'Pending', 'In Progress', 'Done'];

const FILTER_STATUS = {
  'All':        null,
  'Pending':    'PENDING',
  'In Progress': 'IN_PROGRESS',
  'Done':       'DONE',
};

export default function TasksView() {
  const tasks = useStore((s) => s.tasks);
  const [filter, setFilter] = useState('All');

  const statusKey = FILTER_STATUS[filter];
  const visible = statusKey ? tasks.filter((t) => t.status === statusKey) : tasks;

  const pendingCount = tasks.filter((t) => t.status === 'PENDING').length;
  const inProgressCount = tasks.filter((t) => t.status === 'IN_PROGRESS').length;

  return (
    <div>
      {/* Summary */}
      <div className="summary-strip" style={{ color: pendingCount > 0 ? 'var(--warning)' : 'var(--safe)' }}>
        <span>{pendingCount} Pending</span>
        {inProgressCount > 0 && (
          <>
            <span style={{ color: 'var(--text-dim)' }}>·</span>
            <span style={{ color: '#0a84ff' }}>{inProgressCount} In Progress</span>
          </>
        )}
      </div>

      {/* Filter pills */}
      <div className="filter-bar">
        {FILTERS.map((f) => (
          <button
            key={f}
            className={`filter-pill ${filter === f ? 'active' : ''}`}
            onClick={() => setFilter(f)}
          >
            {f}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <div className="empty-state">
          <span className="empty-icon">☑</span>
          <span className="empty-label">No {filter.toLowerCase()} tasks</span>
        </div>
      ) : (
        <div style={{ paddingTop: 8 }}>
          {visible.map((task) => (
            <TaskCard key={task.id} task={task} />
          ))}
        </div>
      )}

      <div style={{ height: 8 }} />
    </div>
  );
}
