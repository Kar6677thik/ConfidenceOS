import { useCallback, useEffect, useMemo, useState } from 'react';
import useStore from '../store';
import apiFetch from '../lib/apiFetch';

function formatExpiry(value) {
  if (!value) return 'unknown expiry';
  return new Date(value).toLocaleTimeString();
}

function taskSensor(task) {
  return task.sensor_id || task.sensorId || 'UNKNOWN';
}

function evidenceRequirements(task) {
  const raw = Array.isArray(task?.evidence_required) ? task.evidence_required : [];
  return raw.map((item, index) => {
    if (typeof item === 'string') {
      return { id: item.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') || `evidence_${index + 1}`, label: item, type: 'text', required: true };
    }
    return {
      id: item?.id || `evidence_${index + 1}`,
      label: item?.label || item?.id || `Evidence item ${index + 1}`,
      type: item?.type || 'text',
      required: item?.required !== false,
    };
  });
}

export default function VerificationTokens({ selectedSensorId, confidence = [] }) {
  const { plantId, verificationTokens, verificationTasks } = useStore();
  const [tokens, setTokens] = useState([]);
  const [note, setNote] = useState('');
  const [evidenceValues, setEvidenceValues] = useState({});
  const [message, setMessage] = useState('');
  const [creating, setCreating] = useState(false);
  const lowSensors = useMemo(
    () => confidence.filter((item) => ['LOW', 'CRITICAL'].includes(item.tier)),
    [confidence],
  );
  const selectedConfidence = confidence.find((item) => item.sensor_id === selectedSensorId);
  const targetSensorId = ['LOW', 'CRITICAL'].includes(selectedConfidence?.tier)
    ? selectedSensorId
    : lowSensors[0]?.sensor_id;

  const refreshTokens = useCallback(() => {
    fetch(`/api/verification-tokens?plant_id=${plantId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((payload) => setTokens(payload?.tokens || []))
      .catch(() => setTokens([]));
  }, [plantId]);

  useEffect(() => {
    refreshTokens();
  }, [refreshTokens]);

  const visibleTokens = verificationTasks?.length
    ? verificationTasks
    : verificationTokens?.length
    ? verificationTokens
    : tokens;

  const createToken = async () => {
    if (!targetSensorId) return;
    setCreating(true);
    try {
      const res = await apiFetch(`/api/verification-tokens?plant_id=${plantId}`, {
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
    const values = evidenceValues[taskId] || {};
    if (state === 'FIELD_CHECK_DONE') {
      const missing = evidenceRequirements(task)
        .filter((item) => item.required && !String(values[item.id] || '').trim())
        .map((item) => item.label);
      if (missing.length) {
        setMessage(`Required field evidence missing: ${missing.join(', ')}.`);
        return;
      }
    }
    await apiFetch(`/api/verification-tasks/state?plant_id=${plantId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: taskId,
        state,
        accepted_by: state === 'ACCEPTED' ? 'Maintenance' : null,
        note: note || task.note || '',
        evidence: state === 'FIELD_CHECK_DONE'
          ? {
              method: task.verification_method || task.verification_type || 'field_check',
              technician_note: note || task.note || 'Field evidence captured.',
              evidence_items: evidenceRequirements(task).map((item) => ({
                id: item.id,
                label: item.label,
                value: values[item.id] || '',
              })),
            }
          : { technician_note: note || task.note || '' },
      }),
    });
    setEvidenceValues((current) => ({ ...current, [taskId]: {} }));
    setMessage('');
    refreshTokens();
  };

  return (
    <section className="industrial-panel border-t-0">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Temporary Field Evidence</p>
          <h2 className="industrial-panel-title text-base">Field Verification Tasks</h2>
        </div>
        <span className="industrial-badge text-[var(--data-mono)]">{visibleTokens.length}</span>
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
          {visibleTokens.map((token) => (
            <div key={token.task_id || token.token_id || `${taskSensor(token)}-${token.valid_until}`} className="bg-[var(--surface-panel)] p-3">
              <div className="flex items-center justify-between gap-3">
                <p className="font-data status-safe">{taskSensor(token)}</p>
                <span className={token.active === false ? 'caption-mono status-critical' : 'caption-mono status-warning'}>
                  {token.state || (token.active === false ? 'EXPIRED' : `until ${formatExpiry(token.valid_until_iso || token.valid_until)}`)}
                </span>
              </div>
              <p className="caption-mono text-[var(--data-mono)] mt-1">{token.verification_method || token.verification_type || 'field_check'}</p>
              <p className="caption-mono text-[var(--text)] mt-1">
                {evidenceRequirements(token).map((item) => `${item.label}${item.required ? ' *' : ''}`).join(' / ')}
              </p>
              {!['ACCEPTED', 'EXPIRED'].includes(token.state) && evidenceRequirements(token).length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-3">
                  {evidenceRequirements(token).map((item) => {
                    const taskId = token.task_id || token.token_id;
                    return (
                      <input
                        key={item.id}
                        className="industrial-input"
                        value={(evidenceValues[taskId] || {})[item.id] || ''}
                        onChange={(event) => setEvidenceValues((current) => ({
                          ...current,
                          [taskId]: { ...(current[taskId] || {}), [item.id]: event.target.value },
                        }))}
                        placeholder={`${item.label}${item.required ? ' *' : ''}`}
                        type={item.type === 'numeric' ? 'number' : 'text'}
                      />
                    );
                  })}
                </div>
              )}
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
          {visibleTokens.length === 0 && (
            <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">No active or recent field verification tasks.</p>
          )}
        </div>
        {message && <p className="caption-mono text-[var(--text-muted)]">{message}</p>}
      </div>
    </section>
  );
}
