import { useEffect, useMemo, useState } from 'react';
import useStore from '../store';

function formatExpiry(value) {
  if (!value) return 'unknown expiry';
  return new Date(value).toLocaleTimeString();
}

function tokenSensor(token) {
  return token.sensor_id || token.sensorId || 'UNKNOWN';
}

export default function VerificationTokens({ selectedSensorId, confidence = [] }) {
  const { plantId, verificationTokens } = useStore();
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
    if (verificationTokens?.length) setTokens(verificationTokens);
  }, [verificationTokens]);

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

  return (
    <section className="industrial-panel border-t-0">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Temporary Field Evidence</p>
          <h2 className="industrial-panel-title text-base">Verification Tokens</h2>
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
            {creating ? 'Creating Token' : 'Create 30 Min Token'}
          </button>
        </div>

        <div className="space-y-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
          {tokens.map((token) => (
            <div key={token.token_id || `${tokenSensor(token)}-${token.valid_until}`} className="bg-[var(--surface-panel)] p-3">
              <div className="flex items-center justify-between gap-3">
                <p className="font-data status-safe">{tokenSensor(token)}</p>
                <span className={token.active === false ? 'caption-mono status-critical' : 'caption-mono status-warning'}>
                  {token.active === false ? 'expired' : `until ${formatExpiry(token.valid_until_iso || token.valid_until)}`}
                </span>
              </div>
              <p className="caption-mono text-[var(--data-mono)] mt-1">{token.verification_type || 'field_check'}</p>
              {!!token.note && <p className="caption-mono text-[var(--text)] mt-1">{token.note}</p>}
            </div>
          ))}
          {tokens.length === 0 && (
            <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--data-mono)]">No active or recent verification tokens.</p>
          )}
        </div>
      </div>
    </section>
  );
}
