import { useCallback, useEffect, useState } from 'react';
import useStore from '../store';
import PageIdentity from './hmi/PageIdentity';
import StatusTag from './hmi/StatusTag';

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

function relativeExpiry(task) {
  const value = task?.valid_until || task?.valid_until_iso;
  if (!value) return 'no expiry recorded';
  const ts = typeof value === 'number' ? value * 1000 : Date.parse(value);
  if (!Number.isFinite(ts)) return 'expiry unavailable';
  const diffMinutes = Math.round((ts - Date.now()) / 60000);
  if (diffMinutes >= 0) return `active for ${diffMinutes} min`;
  return `expired ${Math.abs(diffMinutes)} min ago`;
}

export default function ShiftChannel() {
  const { plantId } = useStore();
  const [channel, setChannel] = useState(null);
  const [message, setMessage] = useState('');
  const [author, setAuthor] = useState('Operator');
  const [showClosedTasks, setShowClosedTasks] = useState(false);
  const verificationTasks = channel?.verification_tasks || [];
  const activeTasks = verificationTasks.filter((item) => item.active || item.handover_required);
  const closedTasks = verificationTasks.filter((item) => !item.active && !item.handover_required);

  const refresh = useCallback(() => {
    fetch(`/api/shift-channel?plant_id=${plantId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setChannel)
      .catch(() => setChannel(null));
  }, [plantId]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [refresh]);

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
    <div className="industrial-page grid grid-rows-[48px_minmax(0,1fr)] bg-[var(--border-strong)] gap-[1px] overflow-hidden">
      <div className="hmi-alarm-band">
        <div className={`hmi-band-cell ${channel?.handover_acceptance_blocked ? 'hmi-band-critical' : ''}`}>
          <span className={`hmi-status-symbol ${channel?.handover_acceptance_blocked ? 'p1' : 'normal'}`}>
            {channel?.handover_acceptance_blocked ? '1' : 'N'}
          </span>
          <div className="min-w-0">
            <p className="label-caps text-[var(--text-muted)]">Pinned Handover Debt</p>
            <p className="caption-mono font-semibold truncate">
              {(channel?.pinned?.length || 0) > 0 ? `${channel.pinned.length} unresolved item(s)` : 'No unresolved handover debt pinned'}
            </p>
          </div>
        </div>
        <div className="hmi-band-cell">
          <span className={`caption-mono ${channel?.handover_acceptance_blocked ? 'status-critical' : 'status-safe'}`}>
            Handover {channel?.handover_acceptance || 'unblocked'}
          </span>
          <span className="caption-mono text-[var(--text-muted)]">active verification tasks: {activeTasks.length}</span>
        </div>
        <div className="hmi-band-cell justify-end">
          <span className="caption-mono">{channel?.channel_id || plantId}</span>
          <span className="caption-mono">shift continuity console</span>
        </div>
      </div>
      <div className="grid grid-cols-[360px_1fr] gap-[1px] bg-[var(--border-strong)] overflow-hidden min-h-0">
      <aside className="bg-[var(--surface-panel)] overflow-y-auto overflow-x-hidden scrollbar-thin">
        {/* 1. Unresolved trust debt — first priority in the console */}
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">Unresolved Trust Debt</h2>
            <span className={`industrial-badge ${(channel?.pinned?.length || 0) > 0 ? 'status-warning' : 'text-[var(--text-dim)]'}`}>
              {channel?.pinned?.length || 0} items
            </span>
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

        {/* 2. Active verification tasks — handover blockers */}
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
                  <StatusTag tier="LOW" label={task.state} />
                </div>
                <p className="caption-mono text-[var(--data-mono)] mt-1">{task.verification_method}</p>
                <p className="caption-mono text-[var(--text-muted)] mt-1">{relativeExpiry(task)}</p>
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

        {/* 3. Closed history — de-emphasized (static layer) */}
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base text-[var(--text-muted)]">Closed Verification History</h2>
            <button
              type="button"
              onClick={() => setShowClosedTasks((value) => !value)}
              className="industrial-control text-[var(--data-mono)]"
            >
              {showClosedTasks ? 'Hide' : `Show ${closedTasks.length}`}
            </button>
          </div>
          <div className="industrial-body">
            <p className="caption-mono text-[var(--data-mono)]">
              Closed and expired tasks are audit history. They do not restore confidence and do not block handover unless listed above.
            </p>
            {showClosedTasks && (
            <div className="space-y-[1px] bg-[var(--border-strong)] mt-3">
            {closedTasks.slice(0, 5).map((task) => (
              <div key={task.task_id || task.token_id} className="bg-[var(--surface-panel)] p-3 opacity-75">
                <div className="flex items-center justify-between gap-3">
                  <p className="label-caps text-[var(--data-mono)] min-w-0 truncate" title={task.sensor_id}>{task.sensor_id}</p>
                  <StatusTag tier={task.state === 'ACCEPTED' ? 'HIGH' : 'MEDIUM'} label={task.state} />
                </div>
                <p className="caption-mono text-[var(--text-muted)] mt-1">
                  {task.accepted_by ? `accepted by ${task.accepted_by}` : task.rejected_by ? `rejected by ${task.rejected_by}` : task.closeout_status || relativeExpiry(task)}
                </p>
                {!!task.last_evidence_summary && (
                  <p className="caption-mono text-[var(--data-mono)] mt-1">{task.last_evidence_summary}</p>
                )}
              </div>
            ))}
            {!closedTasks.length && (
              <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--text-dim)]">No closed verification tasks yet.</p>
            )}
            </div>
            )}
          </div>
        </section>
      </aside>

      <main className="bg-[var(--surface-base)] flex flex-col overflow-hidden">
        <PageIdentity
          displayName="Shift Channel"
          level={2}
          area="Handover & Operating Debt Console"
          plant={channel?.channel_id || plantId}
        />
        <div className="px-5 py-2 flex items-center gap-3 border-b flex-shrink-0"
          style={{ borderBottomColor: channel?.handover_acceptance_blocked ? 'var(--alarm-p1)' : 'var(--border)' }}>
          <StatusTag
            tier={channel?.handover_acceptance_blocked ? 'CRITICAL' : 'HIGH'}
            label={`Handover ${channel?.handover_acceptance || 'unblocked'}`}
          />
          {channel?.handover_acceptance_blocked && (
            <span className="caption-mono text-[var(--text-muted)]">
              Clear active verification tasks to unblock handover
            </span>
          )}
        </div>
        <div className="flex-1 overflow-y-auto overflow-x-hidden scrollbar-thin p-[1px]">
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
        </div>
      </main>
      </div>
    </div>
  );
}
