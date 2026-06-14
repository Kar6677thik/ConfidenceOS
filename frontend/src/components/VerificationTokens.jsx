import { useEffect, useMemo, useState } from 'react';
import useStore from '../store';

function formatExpiry(value) {
  if (!value) return 'unknown expiry';
  return new Date(value).toLocaleTimeString();
}

function taskSensor(task) {
  return task.sensor_id || task.sensorId || 'UNKNOWN';
}

export default function VerificationTokens({ selectedSensorId, confidence = [] }) {
  const { plantId, verificationTokens, verificationTasks } = useStore();
  const [tokens, setTokens] = useState([]);
  const [note, setNote] = useState('');
  const [creating, setCreating] = useState(false);
  const lowSensors = useMemo(
    () => confidence.filter((item) => ['LOW', 'CRITICAL'].includes(item.tier)),
    [confidence],
  );
  const selectedConfidence = confidence.find((item) => item.sensor_id === selectedSensorId);
  const targetSensorId = ['LOW', 'CRITICAL'].includes(selectedConfidence?.tier)
    ? selectedSensorId
    : lowSensors[0]?.sensor_id;

  const refreshTokens = () => {
    fetch(`/api/verification-tokens?plant_id=${plantId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((payload) => setTokens(payload?.tokens || []))
      .catch(() => setTokens([]));
  };

  useEffect(() => {
    refreshTokens();
  }, [plantId]);

  useEffect(() => {
    if (verificationTasks?.length) setTokens(verificationTasks);
    else if (verificationTokens?.length) setTokens(verificationTokens);
  }, [verificationTokens, verificationTasks]);

  const createToken = async () => {
    if (!targetSensorId) return;
    setCreating(true);
    try {
      const res = await fetch(`/api/verification-tokens?plant_id=${plantId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sensor_id: targetSensorId,
          verification_type: 'field_check',
          valid_minutes: 30,
          note: note || 'Manual field verification recorded from operator UI.',
        }),
      });
      if (res.ok) {
        setNote('');
        refreshTokens();
      }
    } finally {
      setCreating(false);
    }
  };

  const advanceTask = async (task, state) => {
    const taskId = task.task_id || task.token_id;
    if (!taskId) return;
    await fetch(`/api/verification-tasks/state?plant_id=${plantId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: taskId,
        state,
        accepted_by: state === 'ACCEPTED' ? 'Maintenance' : null,
        note: note || task.note || '',
      }),
    });
    refreshTokens();
  };

  return (
    <section className="industrial-panel border-t-0">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Temporary Field Evidence</p>
          <h2 className="industrial-panel-title text-base">Field Verification Tasks</h2>
        </div>
        <span className="industrial-badge text-[var(--data-mono)]">{tokens.length}</span>
      </div>
      <div className="industrial-body space-y-4">
        <div className="border border-[var(--border-strong)] bg-[var(--surface-base)] p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="label-caps status-warning">{targetSensorId || 'No low-confidence sensor'}</p>
            <span className="caption-mono text-[var(--data-mono)]">No confidence override</span>
          </div>
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            disabled={!targetSensorId}
            placeholder="field note"
            className="industrial-input mt-3 min-h-20 resize-none"
          />
          <button
            onClick={createToken}
            disabled={!targetSensorId || creating}
            className="industrial-control status-safe w-full mt-3 disabled:opacity-40"
          >
            {creating ? 'Creating Task' : 'Request Field Verification'}
          </button>
        </div>

        <div className="space-y-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
          {tokens.map((token) => (
            <div key={token.task_id || token.token_id || `${taskSensor(token)}-${token.valid_until}`} className="bg-[var(--surface-panel)] p-3">
              <div className="flex items-center justify-between gap-3">
                <p className="font-data status-safe">{taskSensor(token)}</p>
                <span className={token.active === false ? 'caption-mono status-critical' : 'caption-mono status-warning'}>
                  {token.state || (token.active === false ? 'EXPIRED' : `until ${formatExpiry(token.valid_until_iso || token.valid_until)}`)}
                </span>
              </div>
              <p className="caption-mono text-[var(--data-mono)] mt-1">{token.verification_method || token.verification_type || 'field_check'}</p>
              <p className="caption-mono text-[var(--text)] mt-1">{(token.evidence_required || []).join(' / ')}</p>
              {!!token.note && <p className="caption-mono text-[var(--text)] mt-1">{token.note}</p>}
              {!['ACCEPTED', 'EXPIRED'].includes(token.state) && (
                <div className="grid grid-cols-2 gap-2 mt-3">
                  <button onClick={() => advanceTask(token, 'ASSIGNED')} className="industrial-control caption-mono">Assign</button>
                  <button onClick={() => advanceTask(token, 'FIELD_CHECK_DONE')} className="industrial-control caption-mono">Field Done</button>
                  <button onClick={() => advanceTask(token, 'ACCEPTED')} className="industrial-control caption-mono status-safe col-span-2">Accept Evidence</button>
                </div>
              )}
            </div>
          ))}
          {tokens.length === 0 && (
            <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">No active or recent field verification tasks.</p>
          )}
        </div>
      </div>
    </section>
  );
}
