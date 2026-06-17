import { useState } from 'react';
import Panel from './Panel';
import { fetchJson } from './studioUtils';

export default function PasteImportPanel({ busy, onImportResult }) {
  const [tagText, setTagText] = useState('');
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);

  const importTags = async () => {
    const tags = tagText.split(/[\n,;]+/).map((t) => t.trim()).filter(Boolean);
    if (!tags.length) return;
    setImporting(true);
    setResult(null);
    try {
      const payload = await fetchJson('/api/studio/import-tags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags }),
      });
      setResult(payload);
      if (onImportResult) onImportResult(payload);
    } catch (err) {
      setResult({ error: err.payload?.detail || err.message });
    } finally {
      setImporting(false);
    }
  };

  return (
    <Panel eyebrow="Arbitrary Tag Import" title="Paste Tag List" className="mb-[1px]">
      <div className="industrial-panel-subtle p-3 mb-4">
        <p className="caption-mono text-[var(--text)]">Paste any raw tag list - one per line, or comma-separated. Deterministic mapping proposes bindings; engineer approval is required before publish.</p>
      </div>
      <textarea
        value={tagText}
        onChange={(e) => setTagText(e.target.value)}
        className="industrial-input w-full font-mono text-xs min-h-[100px] resize-y"
        placeholder={"U15_LT_5100.PV\n15-FI-2010\nPT_3100_PROCESS\nMY_CUSTOM_TAG.01"}
        disabled={busy || importing}
      />
      <div className="flex gap-3 mt-3 items-center">
        <button
          onClick={importTags}
          disabled={busy || importing || !tagText.trim()}
          className="industrial-control status-safe disabled:opacity-40"
        >
          {importing ? 'Parsing...' : 'Parse Tags'}
        </button>
        <button
          onClick={() => { setTagText(''); setResult(null); }}
          disabled={busy || importing}
          className="industrial-control text-[var(--data-mono)] disabled:opacity-40"
        >
          Clear
        </button>
      </div>
      {result && !result.error && (
        <div className="mt-4 space-y-[1px] bg-[var(--border-strong)] max-h-96 overflow-y-auto overflow-x-hidden scrollbar-thin">
          <div className={`p-3 ${result.ai_assisted ? 'bg-[var(--surface-raised)]' : 'bg-[var(--surface-panel)]'}`}>
            <p className="label-caps text-[var(--text-muted)]">Result</p>
            <p className="caption-mono text-[var(--data-mono)] mt-1">{result.ai_label}</p>
          </div>
          {result.proposals?.map((prop) => (
            <div key={prop.raw_tag} className="bg-[var(--surface-panel)] p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="caption-mono text-[var(--text)] min-w-0 truncate" title={prop.raw_tag}>{prop.raw_tag}</p>
                <span className={`industrial-badge ${prop.ai_confidence_band === 'HIGH' ? 'status-safe' : prop.ai_confidence_band === 'UNCERTAIN' ? 'status-critical' : 'status-warning'}`}>
                  {prop.ai_confidence_band || prop.ai_proposed_canonical_tag ? 'PROPOSED' : 'UNRESOLVED'}
                </span>
              </div>
              {prop.ai_proposed_canonical_tag && (
                <p className="caption-mono text-[var(--data-mono)] mt-1">{'->'} {prop.ai_proposed_canonical_tag}</p>
              )}
              {prop.ai_rationale && (
                <p className="caption-mono text-[var(--text-muted)] mt-1 text-xs">{prop.ai_rationale}</p>
              )}
              <p className="label-caps text-[var(--text-muted)] mt-1">Approval required in Mapping Court</p>
            </div>
          ))}
          {result.unresolved?.length > 0 && (
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="label-caps status-critical">Unresolved Tags - Manual Mapping Required</p>
              <ul className="mt-2 space-y-1">
                {result.unresolved.map((tag) => <li key={tag} className="caption-mono text-[var(--data-mono)]">{tag}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
      {result?.error && (
        <p className="caption-mono status-critical mt-3">{result.error}</p>
      )}
    </Panel>
  );
}
