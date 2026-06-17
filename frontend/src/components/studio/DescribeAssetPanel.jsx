import { useState } from 'react';
import { fetchJson, statusClass } from './studioUtils';

export default function DescribeAssetPanel({ busy }) {
  const [description, setDescription] = useState('');
  const [suggesting, setSuggesting] = useState(false);
  const [result, setResult] = useState(null);

  const suggest = async () => {
    if (!description.trim()) return;
    setSuggesting(true);
    setResult(null);
    try {
      const payload = await fetchJson('/api/studio/suggest-template', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description }),
      });
      setResult(payload);
    } catch (err) {
      setResult({ error: err.payload?.detail || err.message });
    } finally {
      setSuggesting(false);
    }
  };

  return (
    <div className="border border-[var(--border-strong)] bg-[var(--surface-base)] p-3 mb-4">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Low-Code Template Authoring</p>
          <p className="caption-mono text-[var(--data-mono)] mt-1">Describe this asset in plain English. Deterministic template suggestions are compiler-validated and engineer-approved.</p>
        </div>
        <span className="industrial-badge text-[var(--data-mono)]">Engineer approves</span>
      </div>
      <div className="flex gap-3">
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') suggest(); }}
          className="industrial-input flex-1"
          placeholder="e.g. A centrifugal pump with discharge pressure and vibration monitoring"
          disabled={busy || suggesting}
        />
        <button
          onClick={suggest}
          disabled={busy || suggesting || !description.trim()}
          className="industrial-control status-safe disabled:opacity-40 shrink-0"
        >
          {suggesting ? 'Asking...' : 'Suggest Template'}
        </button>
      </div>
      {result && !result.error && (
        <div className="mt-3 space-y-[1px] bg-[var(--border-strong)]">
          <div className={`p-3 ${result.ai_assisted ? 'bg-[var(--surface-raised)]' : 'bg-[var(--surface-panel)]'}`}>
            <p className="label-caps text-[var(--text-muted)]">AI Label</p>
            <p className="caption-mono text-[var(--data-mono)] mt-1">{result.ai_label || result.note}</p>
          </div>
          {result.proposed_template_id && (
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="label-caps text-[var(--text-muted)]">Proposed Template</p>
              <p className="caption-mono status-safe mt-1 font-semibold">{result.proposed_template_id}</p>
              {result.rationale && <p className="caption-mono text-[var(--data-mono)] mt-2">{result.rationale}</p>}
              {result.required_roles?.length > 0 && (
                <p className="label-caps text-[var(--text-muted)] mt-2">Required roles: {result.required_roles.join(', ')}</p>
              )}
              {result.validation_preview && (
                <p className={`caption-mono mt-2 ${statusClass(result.validation_preview.status)}`}>
                  Compiler validation preview: {result.validation_preview.status || 'unknown'}
                </p>
              )}
              <p className="label-caps text-[var(--text-muted)] mt-2">Use the Assignment dropdown to apply this suggestion, then run build.</p>
            </div>
          )}
          {!result.proposed_template_id && (
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="label-caps status-warning">No confident template match</p>
              <p className="caption-mono text-[var(--data-mono)] mt-1">{result.rationale}</p>
            </div>
          )}
        </div>
      )}
      {result?.error && (
        <p className="caption-mono status-critical mt-3">{result.error}</p>
      )}
    </div>
  );
}
