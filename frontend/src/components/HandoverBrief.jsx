import { useState, useCallback } from 'react';
import useStore from '../store';

function renderBriefContent(text) {
  if (!text) return null;

  return text.split('\n').map((line, index) => {
    if (line.startsWith('### ')) {
      return <h4 key={index} className="label-caps status-safe mt-4 mb-1">{line.slice(4)}</h4>;
    }
    if (line.startsWith('## ')) {
      return <h3 key={index} className="text-base font-bold text-[var(--text)] mt-5 mb-2 border-b border-[var(--border-strong)] pb-1">{line.slice(3)}</h3>;
    }
    if (line.startsWith('# ')) {
      return <h2 key={index} className="text-lg font-bold text-[var(--text)] mt-5 mb-2">{line.slice(2)}</h2>;
    }
    if (line.trim() === '') return <div key={index} className="h-2" />;
    return <p key={index} className="caption-mono text-[var(--text)] leading-relaxed">{line}</p>;
  });
}

function SourceBadge({ source }) {
  return (
    <span className="industrial-badge text-[var(--data-mono)]">
      {source ?? 'unknown'}
    </span>
  );
}

export default function HandoverBrief({ apiBase = '/api' }) {
  const { plantId, handoverDebt } = useStore();
  const [brief, setBrief] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  const handleGenerate = useCallback(async () => {
    setLoading(true);
    setError(null);
    setBrief(null);

    try {
      const res = await fetch(`${apiBase}/handover/generate?plant_id=${plantId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new Error(`Server responded with ${res.status}`);
      setBrief(await res.json());
    } catch (err) {
      console.error('[HandoverBrief] Generation failed:', err);
      setError(err.message ?? 'Failed to generate brief');
    } finally {
      setLoading(false);
    }
  }, [apiBase, plantId]);

  const handleCopy = useCallback(async () => {
    if (!brief?.brief) return;

    try {
      await navigator.clipboard.writeText(brief.brief);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = brief.brief;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }

    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [brief]);

  return (
    <section className="industrial-panel w-full">
      <div className="industrial-panel-header">
        <h2 className="industrial-panel-title text-base">Shift Handover Brief</h2>
        {brief && !loading && (
          <div className="flex gap-2">
            <button onClick={handleCopy} className="industrial-control text-[var(--data-mono)]">
              {copied ? 'Copied' : 'Copy'}
            </button>
            <button onClick={() => window.print()} className="industrial-control text-[var(--data-mono)]">
              Print
            </button>
          </div>
        )}
      </div>

      <div className="industrial-body">
        {!loading && (
          <button onClick={handleGenerate} className="industrial-control w-full status-safe mb-4">
            {brief ? 'Regenerate Handover Brief' : 'Generate Shift Handover Brief'}
          </button>
        )}

        {loading && <div className="py-10 caption-mono text-[var(--data-mono)]">Generating handover brief...</div>}

        {!!handoverDebt?.entries?.length && (
          <div className="mb-4 border border-[var(--border-strong)] bg-[var(--surface-base)] p-3">
            <div className="flex items-center justify-between gap-3">
              <p className="label-caps status-warning">Handover Debt</p>
              <span className="industrial-badge status-warning">{handoverDebt.entries.length}</span>
            </div>
            <p className="caption-mono text-[var(--data-mono)] mt-2">
              Unresolved operational debt will be carried into the generated brief.
            </p>
          </div>
        )}

        {error && (
          <div className="py-6 text-center">
            <p className="caption-mono status-critical mb-3">{error}</p>
            <button onClick={handleGenerate} className="industrial-control status-safe">Retry</button>
          </div>
        )}

        {brief && !loading && (
          <div className="industrial-panel-subtle p-4">
            <div className="flex items-center gap-3 mb-4 pb-3 border-b border-[var(--border-strong)]">
              <SourceBadge source={brief.source} />
              {brief.generated_at && (
                <span className="caption-mono text-[var(--data-mono)]">
                  {new Date(brief.generated_at).toLocaleString()}
                </span>
              )}
            </div>
            {!!brief.system_state_summary?.incidents?.length && (
              <div className="mb-4 border border-[var(--border-strong)] bg-[var(--surface-panel)] p-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="label-caps status-warning">Active Incidents</p>
                  <span className="industrial-badge status-warning">{brief.system_state_summary.incidents.length}</span>
                </div>
                <p className="caption-mono text-[var(--text)] mt-2">
                  {brief.system_state_summary.incidents[0].first_action}
                </p>
              </div>
            )}
            <div className="space-y-1">
              {renderBriefContent(brief.brief)}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
