import { useState, useCallback } from 'react';

/**
 * HandoverBrief — Module 6: Shift Handover Brief Generator
 *
 * Generates a shift handover brief via POST {apiBase}/handover/generate,
 * displays the formatted result with source/timestamp metadata,
 * and provides Copy-to-Clipboard and Print actions.
 */

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Render brief text with basic markdown-like heading support.
 * Lines starting with "##" are rendered as styled headings.
 */
function renderBriefContent(text) {
  if (!text) return null;

  const lines = text.split('\n');

  return lines.map((line, idx) => {
    // ### h3 headings
    if (line.startsWith('### ')) {
      return (
        <h4 key={idx} className="text-sm font-bold text-cyan-400 mt-4 mb-1.5 uppercase tracking-wide">
          {line.slice(4)}
        </h4>
      );
    }
    // ## h2 headings
    if (line.startsWith('## ')) {
      return (
        <h3 key={idx} className="text-base font-bold text-cyan-300 mt-5 mb-2 border-b border-gray-700/50 pb-1">
          {line.slice(3)}
        </h3>
      );
    }
    // # h1 headings
    if (line.startsWith('# ')) {
      return (
        <h2 key={idx} className="text-lg font-extrabold text-gray-100 mt-5 mb-2">
          {line.slice(2)}
        </h2>
      );
    }
    // Blank lines → spacer
    if (line.trim() === '') {
      return <div key={idx} className="h-2" />;
    }
    // Regular text
    return (
      <p key={idx} className="text-gray-300 leading-relaxed text-sm">
        {line}
      </p>
    );
  });
}

/** Source badge styling */
function SourceBadge({ source }) {
  const isClaude = source?.toLowerCase() === 'claude';
  return (
    <span
      className={`
        text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wider
        ${isClaude
          ? 'bg-violet-500/15 text-violet-400 border-violet-500/30'
          : 'bg-gray-700/40 text-gray-400 border-gray-600/40'
        }
      `}
    >
      {source ?? 'unknown'}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function HandoverBrief({ apiBase = '/api' }) {
  const [brief, setBrief] = useState(null);       // { text, source, timestamp }
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  // ── Generate brief ─────────────────────────────────────────────────────

  const handleGenerate = useCallback(async () => {
    setLoading(true);
    setError(null);
    setBrief(null);

    try {
      const res = await fetch(`${apiBase}/handover/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!res.ok) {
        throw new Error(`Server responded with ${res.status}`);
      }

      const data = await res.json();
      setBrief(data);
    } catch (err) {
      console.error('[HandoverBrief] Generation failed:', err);
      setError(err.message ?? 'Failed to generate brief');
    } finally {
      setLoading(false);
    }
  }, [apiBase]);

  // ── Copy to clipboard ──────────────────────────────────────────────────

  const handleCopy = useCallback(async () => {
    if (!brief?.brief) return;

    try {
      await navigator.clipboard.writeText(brief.brief);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('[HandoverBrief] Copy failed:', err);
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = brief.brief;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [brief]);

  // ── Print ──────────────────────────────────────────────────────────────

  const handlePrint = useCallback(() => {
    window.print();
  }, []);

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div
      className="
        bg-gray-900/70 backdrop-blur-xl border border-gray-700/50
        rounded-2xl shadow-2xl p-5
        w-full max-w-2xl
      "
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-sm font-bold tracking-wide text-gray-200 uppercase">
          Shift Handover Brief
        </h2>

        {/* Action buttons — only visible when brief is loaded */}
        {brief && !loading && (
          <div className="flex items-center gap-2">
            {/* Copy button */}
            <button
              onClick={handleCopy}
              className="
                text-[11px] font-medium px-3 py-1.5 rounded-lg
                bg-gray-800/60 border border-gray-700/50
                text-gray-400 hover:text-gray-200 hover:border-gray-600
                transition-colors cursor-pointer
                focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500
              "
              title="Copy brief to clipboard"
            >
              {copied ? '✓ Copied' : '⧉ Copy'}
            </button>

            {/* Print button */}
            <button
              onClick={handlePrint}
              className="
                text-[11px] font-medium px-3 py-1.5 rounded-lg
                bg-gray-800/60 border border-gray-700/50
                text-gray-400 hover:text-gray-200 hover:border-gray-600
                transition-colors cursor-pointer
                focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500
              "
              title="Print brief"
            >
              🖨 Print
            </button>
          </div>
        )}
      </div>

      {/* Generate button — shown when no brief is loaded or as a re-generate */}
      {!loading && (
        <button
          onClick={handleGenerate}
          className="
            w-full py-3 rounded-xl font-semibold text-sm
            bg-gradient-to-r from-cyan-600 to-blue-600
            hover:from-cyan-500 hover:to-blue-500
            text-white shadow-lg shadow-cyan-500/20
            transition-all duration-200 cursor-pointer
            focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400
            mb-4
          "
        >
          {brief ? '↻ Regenerate Handover Brief' : 'Generate Shift Handover Brief'}
        </button>
      )}

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="relative">
            <div className="h-10 w-10 rounded-full border-2 border-gray-700" />
            <div className="absolute top-0 left-0 h-10 w-10 rounded-full border-2 border-t-cyan-400 animate-spin" />
          </div>
          <span className="ml-3 text-gray-400 text-sm">Generating handover brief…</span>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="text-center py-6">
          <p className="text-red-400 text-sm mb-2">⚠ {error}</p>
          <button
            onClick={handleGenerate}
            className="text-xs text-cyan-400 hover:text-cyan-300 underline underline-offset-2 cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {/* Brief content */}
      {brief && !loading && (
        <div className="bg-gray-800/40 border border-gray-700/40 rounded-xl p-5">
          {/* Metadata row */}
          <div className="flex items-center gap-3 mb-4 pb-3 border-b border-gray-700/40">
            <SourceBadge source={brief.source} />
            {brief.generated_at && (
              <span className="text-[10px] text-gray-600 font-mono">
                {new Date(brief.generated_at).toLocaleString()}
              </span>
            )}
          </div>

          {/* Formatted brief text with monospaced font */}
          <div className="font-mono text-[13px] leading-relaxed">
            {renderBriefContent(brief.brief)}
          </div>
        </div>
      )}
    </div>
  );
}
