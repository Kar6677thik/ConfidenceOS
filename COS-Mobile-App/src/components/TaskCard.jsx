import useStore from '../store';

const ROLE_COLOR = {
  Operator:    'var(--role-operator)',
  Maintenance: 'var(--role-maintenance)',
  Engineer:    'var(--role-engineer)',
  Manager:     'var(--role-manager)',
  Auditor:     'var(--role-auditor)',
};

const STATUS_CLASS = {
  PENDING:     'task-status-pending',
  IN_PROGRESS: 'task-status-in_progress',
  DONE:        'task-status-done',
};

const STATUS_LABEL = {
  PENDING:     'Pending',
  IN_PROGRESS: 'In Progress',
  DONE:        'Done',
};

export default function TaskCard({ task }) {
  const completeTask = useStore((s) => s.completeTask);
  const isDone = task.status === 'DONE';

  return (
    <div className={`task-card ${isDone ? 'done' : ''}`}>
      <button
        className={`task-checkbox ${isDone ? 'checked' : ''}`}
        onClick={() => !isDone && completeTask(task.id)}
        aria-label={isDone ? 'Task complete' : 'Mark complete'}
      >
        {isDone ? '✓' : ''}
      </button>
      <div className="task-body">
        <div className="task-tag">{task.tag}</div>
        <div className="task-desc">{task.desc}</div>
        <div className="task-meta">
          <span
            className="role-badge"
            style={{ color: ROLE_COLOR[task.role] ?? 'var(--text-muted)' }}
          >
            {task.role}
          </span>
          <span className={`task-status ${STATUS_CLASS[task.status]}`}>
            {STATUS_LABEL[task.status]}
          </span>
          {task.dueIn && (
            <span className="task-due">Due in {task.dueIn}</span>
          )}
        </div>
      </div>
    </div>
  );
}
