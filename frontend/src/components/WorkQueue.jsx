import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import useStore from '../store';
import PageIdentity from './hmi/PageIdentity';
import StatusTag from './hmi/StatusTag';
import apiFetch from '../lib/apiFetch';

const ROLE_TRANSITIONS = {
  Operator: new Set(['EXPIRED']),
  Maintenance: new Set(['ASSIGNED', 'FIELD_CHECK_DONE', 'EXPIRED']),
  Engineer: new Set(['ASSIGNED', 'ACCEPTED', 'REJECTED', 'EXPIRED']),
  Manager: new Set(['ASSIGNED', 'ACCEPTED', 'REJECTED', 'EXPIRED']),
  Auditor: new Set([]),
};

const NEXT_STATES = {
  REQUESTED: ['ASSIGNED', 'EXPIRED'],
  ASSIGNED: ['FIELD_CHECK_DONE', 'EXPIRED'],
  FIELD_CHECK_DONE: ['ACCEPTED', 'REJECTED', 'EXPIRED'],
  REJECTED: ['ASSIGNED', 'EXPIRED'],
};

const EVIDENCE_REQUIRED = new Set(['FIELD_CHECK_DONE', 'ACCEPTED', 'REJECTED']);

function statusClass(value) {
  const v = String(value || '').toUpperCase();
  if (['CRITICAL', 'QUARANTINED', 'BLOCKED'].includes(v)) return 'status-critical';
  if (['WARNING', 'LOW', 'DEGRADED', 'REQUESTED', 'ASSIGNED'].includes(v)) return 'status-warning';
  if (['FIELD_CHECK_DONE', 'SUBSTITUTED', 'MEDIUM'].includes(v)) return 'status-caution';
  if (['ACCEPTED', 'TRUSTED', 'HIGH', 'CLEAR'].includes(v)) return 'status-safe';
  return 'text-[var(--data-mono)]';
}

function formatText(value) {
  if (value == null || value === '') return '';
  if (Array.isArray(value)) return value.map(formatText).filter(Boolean).join(' / ');
  if (typeof value === 'object') {
    return formatText(value.title || value.message || value.required_action || value.sensor_id || value.type || '');
  }
  return String(value).replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function relativeExpiry(task) {
  const raw = task?.valid_until || task?.valid_until_iso;
  if (!raw) return 'No expiry recorded';
  const ts = typeof raw === 'number' ? raw * 1000 : Date.parse(raw);
  if (!Number.isFinite(ts)) return 'Expiry unavailable';
  const minutes = Math.round((ts - Date.now()) / 60000);
  return minutes >= 0 ? `Due in ${minutes} min` : `Expired ${Math.abs(minutes)} min ago`;
}

function actionLabel(state) {
  return {
    ASSIGNED: 'Assign to maintenance',
    FIELD_CHECK_DONE: 'Mark field check done',
    ACCEPTED: 'Accept evidence',
    REJECTED: 'Reject evidence',
    EXPIRED: 'Expire task',
  }[state] || formatText(state);
}

function QueueMetric({ label, value, tone = '' }) {
  return (
    <div className="bg-[var(--surface-panel)] border border-[var(--border-strong)] p-3 min-w-0">
      <p className="label-caps text-[var(--text-muted)]">{label}</p>
      <p className={`text-[24px] leading-[28px] font-bold mt-1 ${tone}`}>{value}</p>
    </div>
  );
}

function ExceptionCard({ item }) {
  return (
    <div className="bg-[var(--surface-panel)] border border-[var(--border-strong)] p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className={`label-caps ${statusClass(item.severity || item.trust_state)}`}>
            {formatText(item.type || item.severity || 'trust exception')}
          </p>
          <p className="caption-mono font-semibold mt-1 [overflow-wrap:anywhere]">
            {item.title || item.message || 'Unresolved operating-basis exception'}
          </p>
        </div>
        <StatusTag tier={item.severity || item.trust_state || 'LOW'} />
      </div>
      {item.required_action && (
        <>
          <p className="label-caps text-[var(--text-muted)] mt-3">Required Action</p>
          <p className="caption-mono status-warning [overflow-wrap:anywhere]">{item.required_action}</p>
        </>
      )}
    </div>
  );
}

function VerificationTaskCard({ task, role, plantId, onChanged }) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const allowedByRole = ROLE_TRANSITIONS[role] || new Set();
  const legalStates = (NEXT_STATES[task.state] || []).filter((state) => allowedByRole.has(state));

  const submit = async (state) => {
    if (EVIDENCE_REQUIRED.has(state) && !note.trim()) {
      setMessage('Evidence note required before this transition.');
      return;
    }
    const taskId = task.task_id || task.token_id;
    setBusy(state);
    setMessage('');
    try {
      const res = await apiFetch(`/api/verification-tasks/state?plant_id=${plantId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: taskId,
          state,
          actor: role,
          actor_role: role,
          evidence_note: note,
          evidence: note ? { technician_note: note, method: task.verification_method } : {},
        }),
      });
      const payload = await res.json().catch(() => null);
      if (!res.ok) throw new Error(payload?.detail || `Task update failed: ${res.status}`);
      setNote('');
      setMessage(`${task.sensor_id} moved to ${state}.`);
      onChanged?.();
    } catch (err) {
      setMessage(err.message || 'Task update failed.');
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="bg-[var(--surface-panel)] border border-[var(--border-strong)] p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label-caps text-[var(--text-muted)]">Field Verification Task</p>
          <p className="caption-mono font-semibold">{task.sensor_id}</p>
        </div>
        <span className={`caption-mono ${statusClass(task.state)}`}>{task.state}</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-3">
        <div>
          <p className="label-caps text-[var(--text-dim)]">Method</p>
          <p className="caption-mono">{formatText(task.verification_method || task.verification_type)}</p>
        </div>
        <div>
          <p className="label-caps text-[var(--text-dim)]">Owner</p>
          <p className="caption-mono">{task.assigned_role || 'Maintenance'}</p>
        </div>
        <div>
          <p className="label-caps text-[var(--text-dim)]">Due</p>
          <p className="caption-mono">{relativeExpiry(task)}</p>
        </div>
      </div>
      <p className="label-caps text-[var(--text-muted)] mt-3">Evidence Required</p>
      <p className="caption-mono text-[var(--text)]">
        {(task.evidence_required || []).length ? task.evidence_required.join(' / ') : 'local indication / field note / timestamp'}
      </p>
      {!!task.procedure_ref && (
        <div className="mt-2 flex items-center gap-2">
          <p className="label-caps text-[var(--text-dim)]">Procedure</p>
          <p className="caption-mono text-[var(--data-mono)] truncate">{task.procedure_ref}</p>
        </div>
      )}
      {!!task.field_location && (
        <div className="mt-1 flex items-center gap-2">
          <p className="label-caps text-[var(--text-dim)]">Location</p>
          <p className="caption-mono">{task.field_location}</p>
        </div>
      )}
      {!!task.cmms_work_order && (
        <div className="mt-1 flex items-center gap-2">
          <p className="label-caps text-[var(--text-dim)]">WO</p>
          <p className="caption-mono">{task.cmms_work_order}</p>
        </div>
      )}
      {!!task.last_evidence_summary && (
        <p className="caption-mono text-[var(--data-mono)] mt-2">Latest evidence: {task.last_evidence_summary}</p>
      )}
      {legalStates.length > 0 && (
        <div className="mt-3 grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-2">
          <input
            className="industrial-input"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Evidence note for task transition"
          />
          <div className="flex flex-wrap gap-2">
            {legalStates.map((state) => (
              <button
                key={state}
                type="button"
                disabled={!!busy}
                className="industrial-control"
                onClick={() => submit(state)}
              >
                {busy === state ? 'Working...' : actionLabel(state)}
              </button>
            ))}
          </div>
        </div>
      )}
      {legalStates.length === 0 && (
        <p className="caption-mono text-[var(--text-muted)] mt-3">
          {role === 'Auditor' ? 'Auditor view is read-only.' : 'No legal transition available for this task state.'}
        </p>
      )}
      {message && <p className="caption-mono text-[var(--text-muted)] mt-2">{message}</p>}
    </div>
  );
}

function ExpiredTaskRecoveryCard({ task, plantId, role, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const canRequest = role !== 'Auditor';

  const requestFreshTask = async () => {
    setBusy(true);
    setMessage('');
    try {
      const res = await apiFetch(`/api/verification-tokens?plant_id=${plantId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sensor_id: task.sensor_id,
          verification_type: task.verification_method || task.verification_type || 'field_check',
          valid_minutes: 30,
          note: `Fresh verification requested because prior task ${task.task_id || task.token_id} expired before acceptance.`,
        }),
      });
      const payload = await res.json().catch(() => null);
      if (!res.ok) throw new Error(payload?.detail || `Fresh task request failed: ${res.status}`);
      setMessage(`Fresh verification requested for ${task.sensor_id}.`);
      onChanged?.();
    } catch (err) {
      setMessage(err.message || 'Fresh task request failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-[var(--surface-panel)] border border-[var(--border-strong)] p-3 opacity-90">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label-caps text-[var(--text-muted)]">Expired Verification History</p>
          <p className="caption-mono font-semibold">{task.sensor_id}</p>
        </div>
        <span className="caption-mono status-warning">EXPIRED</span>
      </div>
      <p className="caption-mono text-[var(--text-muted)] mt-2">
        {relativeExpiry(task)}. Expired tasks are audit history only; they do not restore trust or clear handover debt.
      </p>
      {!!task.last_evidence_summary && (
        <p className="caption-mono text-[var(--data-mono)] mt-2">Latest evidence: {task.last_evidence_summary}</p>
      )}
      {canRequest ? (
        <button
          type="button"
          disabled={busy}
          onClick={requestFreshTask}
          className="industrial-control mt-3 disabled:opacity-40"
        >
          {busy ? 'Requesting...' : 'Request Fresh Verification'}
        </button>
      ) : (
        <p className="caption-mono text-[var(--text-muted)] mt-3">Auditor view is read-only. Maintenance or Engineer can request a fresh task.</p>
      )}
      {message && <p className="caption-mono text-[var(--text-muted)] mt-2">{message}</p>}
    </div>
  );
}

export default function WorkQueue() {
  const {
    plantId,
    role,
    incidents,
    confidence,
    confidenceDebt,
    verificationTasks: liveVerificationTasks,
    handoverDebt,
  } = useStore();
  const [channel, setChannel] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(() => {
    setError('');
    fetch(`/api/shift-channel?plant_id=${plantId}`)
      .then(async (res) => {
        const payload = await res.json().catch(() => null);
        if (!res.ok) throw new Error(payload?.detail || `Work queue unavailable: ${res.status}`);
        setChannel(payload);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || 'Work queue unavailable.');
        setLoading(false);
      });
  }, [plantId]);

  useEffect(() => {
    const initial = setTimeout(refresh, 0);
    const timer = setInterval(refresh, 4000);
    return () => {
      clearTimeout(initial);
      clearInterval(timer);
    };
  }, [refresh]);

  const pinned = useMemo(() => channel?.pinned || handoverDebt?.entries || [], [channel, handoverDebt]);
  const tasks = useMemo(() => {
    const fromChannel = channel?.verification_tasks || [];
    return (fromChannel.length ? fromChannel : liveVerificationTasks || [])
      .filter((task) => task.active || task.handover_required || ['REQUESTED', 'ASSIGNED', 'FIELD_CHECK_DONE', 'REJECTED'].includes(task.state));
  }, [channel, liveVerificationTasks]);
  const expiredTasks = useMemo(() => {
    const fromChannel = channel?.verification_tasks || [];
    return (fromChannel.length ? fromChannel : liveVerificationTasks || [])
      .filter((task) => task.state === 'EXPIRED' || task.expired)
      .slice(0, 4);
  }, [channel, liveVerificationTasks]);
  const degradedCritical = useMemo(
    () => (confidence || []).filter((item) => ['LOW', 'CRITICAL'].includes(item.tier) || ['QUARANTINED', 'DEGRADED'].includes(item.trust_state)),
    [confidence],
  );
  const debtRows = useMemo(() => confidenceDebt || [], [confidenceDebt]);
  const handoverBlocked = !!(channel?.handover_acceptance_blocked || handoverDebt?.handover_acceptance_blocked || handoverDebt?.handover_acceptance === 'blocked');

  if (loading) {
    return (
      <div className="industrial-page p-6">
        <p className="caption-mono text-[var(--data-mono)]">Loading operational work queue...</p>
      </div>
    );
  }

  return (
    <div className="industrial-page grid grid-rows-[auto_minmax(0,1fr)] overflow-hidden">
      <PageIdentity
        displayName="Work Queue"
        level={2}
        area="Operational Ownership Console"
        plant={plantId}
      />
      <div className="grid grid-cols-[minmax(280px,360px)_1fr] gap-[1px] bg-[var(--border-strong)] min-h-0 overflow-hidden">
        <aside className="bg-[var(--surface-panel)] overflow-y-auto scrollbar-thin">
          <section className="industrial-panel border-t-0">
            <div className="industrial-panel-header">
              <div>
                <p className="label-caps text-[var(--text-muted)]">Queue Basis</p>
                <h2 className="industrial-panel-title text-base">Live Ownership State</h2>
              </div>
            </div>
            <div className="industrial-body grid grid-cols-2 gap-2">
              <QueueMetric label="Open Tasks" value={tasks.length} tone={tasks.length ? 'status-warning' : 'status-safe'} />
              <QueueMetric label="Handover" value={handoverBlocked ? 'Blocked' : 'Clear'} tone={handoverBlocked ? 'status-critical' : 'status-safe'} />
              <QueueMetric label="Trust Exceptions" value={pinned.length + degradedCritical.length} tone={(pinned.length + degradedCritical.length) ? 'status-warning' : 'status-safe'} />
              <QueueMetric label="Expired Tasks" value={expiredTasks.length} tone={expiredTasks.length ? 'status-caution' : 'status-safe'} />
            </div>
            <div className="industrial-body border-t border-[var(--border)]">
              <p className="caption-mono text-[var(--text-muted)]">
                ConfidenceOS work items are read-only operating tasks. They do not acknowledge alarms, change setpoints, or write DCS/HMI commands.
              </p>
              {error && <p className="caption-mono status-critical mt-2">{error}</p>}
            </div>
          </section>

          <section className="industrial-panel border-t-0">
            <div className="industrial-panel-header">
              <h2 className="industrial-panel-title text-base">Next Best Workflow</h2>
            </div>
            <div className="industrial-body space-y-2">
              <Link to="/runtime" className="industrial-control inline-flex w-full justify-center">Open Runtime Operating Basis</Link>
              <Link to="/handover" className="industrial-control inline-flex w-full justify-center">Open Shift Channel</Link>
              {(role === 'Engineer' || role === 'Manager') && (
                <Link to="/studio" className="industrial-control inline-flex w-full justify-center">Open Studio Publish Gate</Link>
              )}
            </div>
          </section>
        </aside>

        <main className="bg-[var(--surface-base)] overflow-y-auto scrollbar-thin p-[1px]">
          <section className="industrial-panel">
            <div className="industrial-panel-header">
              <div>
                <p className="label-caps text-[var(--text-muted)]">Owned Work</p>
                <h1 className="industrial-panel-title">Verification And Operating-Basis Tasks</h1>
              </div>
              <StatusTag tier={handoverBlocked ? 'CRITICAL' : 'HIGH'} label={handoverBlocked ? 'Handover Blocked' : 'Handover Clear'} />
            </div>
            <div className="industrial-body space-y-3">
              {tasks.length ? tasks.map((task) => (
                <VerificationTaskCard
                  key={task.task_id || task.token_id}
                  task={task}
                  role={role}
                  plantId={plantId}
                  onChanged={refresh}
                />
              )) : (
                <div className="bg-[var(--surface-panel)] border border-[var(--border-strong)] p-4">
                  <p className="caption-mono status-safe">No active field verification tasks. Continue monitoring Runtime operating basis.</p>
                </div>
              )}
            </div>
          </section>

          {expiredTasks.length > 0 && (
            <section className="industrial-panel">
              <div className="industrial-panel-header">
                <div>
                  <p className="label-caps text-[var(--text-muted)]">Recovery</p>
                  <h2 className="industrial-panel-title text-base">Expired Verification Tasks</h2>
                </div>
                <span className="industrial-badge text-[var(--data-mono)]">{expiredTasks.length}</span>
              </div>
              <div className="industrial-body space-y-3">
                {expiredTasks.map((task) => (
                  <ExpiredTaskRecoveryCard
                    key={task.task_id || task.token_id}
                    task={task}
                    plantId={plantId}
                    role={role}
                    onChanged={refresh}
                  />
                ))}
              </div>
            </section>
          )}

          <section className="industrial-panel">
            <div className="industrial-panel-header">
              <h2 className="industrial-panel-title text-base">Operating Exceptions</h2>
              <span className="industrial-badge text-[var(--data-mono)]">{pinned.length || incidents.length}</span>
            </div>
            <div className="industrial-body grid grid-cols-1 xl:grid-cols-2 gap-3">
              {(pinned.length ? pinned : incidents).slice(0, 6).map((item, index) => (
                <ExceptionCard key={`${item.id || item.incident_id || item.title}-${index}`} item={item} />
              ))}
              {!pinned.length && !incidents.length && (
                <p className="caption-mono text-[var(--data-mono)]">No unresolved operating exceptions.</p>
              )}
            </div>
          </section>

          <section className="industrial-panel">
            <div className="industrial-panel-header">
              <h2 className="industrial-panel-title text-base">Maintenance Priority From Confidence Debt</h2>
              <span className="industrial-badge text-[var(--data-mono)]">{debtRows.length}</span>
            </div>
            <div className="industrial-body space-y-[1px] bg-[var(--border-strong)]">
              {debtRows.slice(0, 8).map((item) => (
                <div key={item.sensor_id} className="bg-[var(--surface-panel)] p-3 grid grid-cols-[150px_1fr_auto] gap-3 items-center">
                  <p className="caption-mono font-semibold">{item.sensor_id}</p>
                  <p className="caption-mono text-[var(--text-muted)] [overflow-wrap:anywhere]">
                    {item.priority_language || item.maintenance_priority || 'Track as confidence debt. Not a failure forecast.'}
                  </p>
                  <span className={`caption-mono ${statusClass(item.priority || item.tier)}`}>
                    {item.confidence_debt ?? item.debt_score ?? '--'}
                  </span>
                </div>
              ))}
              {!debtRows.length && (
                <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">No active confidence debt.</p>
              )}
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
