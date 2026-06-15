import { useEffect, useState } from 'react';
import useStore from '../store';

function eventTime(timestamp) {
  if (!timestamp) return 'live';
  const millis = timestamp > 10_000_000_000 ? timestamp : timestamp * 1000;
  return new Date(millis).toLocaleTimeString();
}

function severityClass(value) {
  const severity = String(value || '').toUpperCase();
  if (severity === 'CRITICAL') return 'status-critical';
  if (severity === 'WARNING' || severity === 'LOW') return 'status-warning';
  if (severity === 'MEDIUM') return 'status-caution';
  return 'text-[var(--data-mono)]';
}

export default function ShiftChannel() {
  const { plantId } = useStore();
  const [channel, setChannel] = useState(null);
  const [message, setMessage] = useState('');
  const [author, setAuthor] = useState('Operator');
  const verificationTasks = channel?.verification_tasks || [];
  const activeTasks = verificationTasks.filter((item) => item.active || item.handover_required);
  const closedTasks = verificationTasks.filter((item) => !item.active && !item.handover_required);

  const refresh = () => {
    fetch(`/api/shift-channel?plant_id=${plantId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setChannel)
      .catch(() => setChannel(null));
  };

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [plantId]);

  const addNote = async (event) => {
    event.preventDefault();
    if (!message.trim()) return;
    await fetch('/api/shift-channel/note', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plant_id: plantId, author, message: message.trim() }),
    });
    setMessage('');
    refresh();
  };

  return (
    <div className="industrial-page grid grid-cols-[420px_1fr] gap-[1px] bg-[var(--border-strong)] overflow-hidden">
      <aside className="bg-[var(--surface-panel)] overflow-y-auto overflow-x-hidden scrollbar-thin">
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <div>
              <p className="label-caps text-[var(--text-muted)]">Persistent Shift Channel</p>
              <h1 className="industrial-panel-title text-base">{channel?.channel_id || plantId}</h1>
            </div>
            <span className="industrial-badge status-warning">{channel?.pinned?.length || 0} pinned</span>
          </div>
          <div className="industrial-body">
            <p className="caption-mono text-[var(--text)]">{channel?.summary || 'Loading shift channel.'}</p>
            <p className={`caption-mono mt-3 ${channel?.handover_acceptance_blocked ? 'status-critical' : 'status-safe'}`}>
              Handover acceptance: {channel?.handover_acceptance || 'unblocked'}
            </p>
          </div>
        </section>
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">Active Verification Tasks</h2>
            <span className="industrial-badge text-[var(--data-mono)]">{activeTasks.length}</span>
          </div>
          <div className="industrial-body space-y-[1px] bg-[var(--border-strong)]">
            {activeTasks.map((task) => (
              <div key={task.task_id || task.token_id} className="bg-[var(--surface-panel)] p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="label-caps status-warning min-w-0 truncate" title={task.sensor_id}>{task.sensor_id}</p>
                  <span className="industrial-badge status-warning">{task.state}</span>
                </div>
                <p className="caption-mono text-[var(--data-mono)] mt-1">{task.verification_method}</p>
                <p className="caption-mono text-[var(--text)] mt-1">{(task.evidence_required || []).join(' / ')}</p>
                {!!task.last_evidence_summary && (
                  <p className="caption-mono text-[var(--text-muted)] mt-1">evidence: {task.last_evidence_summary}</p>
                )}
                <p className="label-caps text-[var(--text-muted)] mt-1">
                  confidence override: no / usable as reference: {task.usable_as_reference ? 'yes' : 'no'}
                </p>
              </div>
            ))}
            {!activeTasks.length && (
              <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">No active field verification tasks.</p>
            )}
          </div>
        </section>
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">Recent Verification History</h2>
            <span className="industrial-badge text-[var(--data-mono)]">{closedTasks.length}</span>
          </div>
          <div className="industrial-body space-y-[1px] bg-[var(--border-strong)]">
            {closedTasks.slice(0, 5).map((task) => (
              <div key={task.task_id || task.token_id} className="bg-[var(--surface-panel)] p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="label-caps text-[var(--data-mono)]">{task.sensor_id}</p>
                  <span className={`industrial-badge ${task.state === 'ACCEPTED' ? 'status-safe' : 'status-warning'}`}>{task.state}</span>
                </div>
                <p className="caption-mono text-[var(--text-muted)] mt-1">
                  {task.accepted_by ? `accepted by ${task.accepted_by}` : task.rejected_by ? `rejected by ${task.rejected_by}` : task.closeout_status || 'closed'}
                </p>
                {!!task.last_evidence_summary && (
                  <p className="caption-mono text-[var(--data-mono)] mt-1">{task.last_evidence_summary}</p>
                )}
              </div>
            ))}
            {!closedTasks.length && (
              <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">No closed verification tasks yet.</p>
            )}
          </div>
        </section>
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">Pinned Operating Debt</h2>
          </div>
          <div className="industrial-body space-y-[1px] bg-[var(--border-strong)]">
            {(channel?.pinned || []).map((item) => (
              <div key={item.id} className="bg-[var(--surface-panel)] p-3">
                <p className={`label-caps ${severityClass(item.severity)}`}>{item.type}</p>
                <p className="caption-mono text-[var(--text)] mt-1">{item.title}</p>
                {!!item.required_action && <p className="caption-mono text-[var(--data-mono)] mt-1">{item.required_action}</p>}
              </div>
            ))}
            {(!channel?.pinned || channel.pinned.length === 0) && (
              <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">No unresolved handover debt pinned.</p>
            )}
          </div>
        </section>
      </aside>

      <main className="bg-[var(--surface-base)] p-[1px] overflow-y-auto overflow-x-hidden scrollbar-thin">
        <section className="industrial-panel mb-[1px]">
          <div className="industrial-panel-header">
            <div>
              <p className="label-caps text-[var(--text-muted)]">Teams-like Handover Thread</p>
              <h1 className="industrial-panel-title">Shift Continuity</h1>
            </div>
          </div>
          <form onSubmit={addNote} className="industrial-body grid grid-cols-[180px_1fr_130px] gap-2">
            <input value={author} onChange={(event) => setAuthor(event.target.value)} className="industrial-input" />
            <input value={message} onChange={(event) => setMessage(event.target.value)} className="industrial-input" placeholder="Add operator note for handover..." />
            <button className="industrial-control status-safe">Pin Note</button>
          </form>
        </section>
        <section className="industrial-panel">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">Thread</h2>
            <span className="industrial-badge text-[var(--data-mono)]">{channel?.thread?.length || 0}</span>
          </div>
          <div className="industrial-body space-y-[1px] bg-[var(--border-strong)]">
            {(channel?.thread || []).map((item) => (
              <div key={item.id} className="bg-[var(--surface-panel)] p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className={`label-caps min-w-0 truncate ${severityClass(item.severity)}`} title={`${item.author || 'ConfidenceOS'} / ${item.type}`}>{item.author || 'ConfidenceOS'} / {item.type}</p>
                  <span className="caption-mono text-[var(--data-mono)] shrink-0">{eventTime(item.timestamp)}</span>
                </div>
                <p className="text-[var(--text)] mt-2 [overflow-wrap:anywhere]">{item.message}</p>
              </div>
            ))}
            {(!channel?.thread || channel.thread.length === 0) && (
              <p className="bg-[var(--surface-panel)] p-4 caption-mono text-[var(--data-mono)]">No shift-channel events yet.</p>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
