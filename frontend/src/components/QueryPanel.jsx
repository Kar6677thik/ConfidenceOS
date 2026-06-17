import { useState, useRef, useEffect } from 'react';
import useStore from '../store';

export default function QueryPanel() {
  const { queryHistory, queryLoading, askQuestion, plantContext, incidents, confidence } = useStore();
  const [input, setInput] = useState('');
  const scrollRef = useRef(null);
  const activeDecisionFreeze = (incidents || []).some((incident) => (
    incident.action_contract?.blocked_decisions?.length || incident.blocked_decisions?.length
  ));
  const stressContext = ['WARNING', 'CRITICAL'].includes(String(plantContext?.severity || '').toUpperCase())
    || ['MASS_BALANCE_DIVERGENCE', 'MANUAL_VERIFICATION_REQUIRED'].includes(String(plantContext?.state || '').toUpperCase());

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [queryHistory]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!input.trim() || queryLoading) return;
    const question = input.trim();
    setInput('');
    await askQuestion(question);
  };

  // Name the actually-degraded sensor rather than a hardcoded tag, so the
  // prompt reflects the live model/plant. Falls back to a generic question.
  const flagged = (confidence || [])
    .filter((c) => c.tier && c.tier !== 'HIGH')
    .sort((a, b) => (a.confidence_pct ?? 100) - (b.confidence_pct ?? 100));
  const flaggedSensor = flagged[0]?.sensor_id;
  const suggestions = [
    flaggedSensor ? `Why is ${flaggedSensor} flagged?` : 'Why is the primary signal flagged?',
    'What is the operating basis?',
    'Which trusted substitute should I use?',
    'What verification is required?',
  ];

  if (stressContext || activeDecisionFreeze) {
    return (
      <section className="industrial-panel h-full min-h-[220px] flex flex-col overflow-hidden">
        <div className="industrial-panel-header">
          <div>
            <h2 className="industrial-panel-title">Grounded Operator Explanation</h2>
            <p className="caption-mono status-warning">DISABLED DURING ACTIVE DECISION FREEZE</p>
          </div>
        </div>
        <div className="industrial-body">
          <p className="caption-mono text-[var(--text)]">
            Grounded explanation disabled during active decision freeze. Use operating-basis workflow.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="industrial-panel h-full min-h-[360px] flex flex-col overflow-hidden">
      <div className="industrial-panel-header">
        <div>
          <h2 className="industrial-panel-title">Grounded Operator Explanation</h2>
          <p className="caption-mono text-[var(--data-mono)]">SYSTEM LOG / EVIDENCE-LINKED ANSWERS</p>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin p-5 space-y-5">
        {queryHistory.length === 0 && (
          <div className="space-y-3">
            <p className="label-caps text-[var(--text-muted)]">Try Asking</p>
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                onClick={() => setInput(suggestion)}
                className="w-full text-left industrial-panel-subtle p-3 caption-mono text-[var(--data-mono)] hover:text-[var(--text)] hover:border-[var(--outline)]"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}

        {queryHistory.map((entry, index) => (
          <div key={`${entry.timestamp}-${index}`} className="space-y-3">
            <div className="ml-8 bg-[var(--surface-high)] border border-[var(--border-subtle)] p-4 text-right">
              <p className="label-caps text-[var(--text-muted)] mb-2">Operator</p>
              <p className="text-[var(--text)]">{entry.question}</p>
            </div>
            <div className="border border-[var(--border-strong)] bg-[var(--surface-panel)] p-4">
              <p className="label-caps text-[var(--text-muted)] mb-2">Operating Basis</p>
              <p className="leading-relaxed text-[var(--text)]">{entry.answer}</p>
              {entry.sources?.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-3">
                  {entry.sources.map((source, sourceIndex) => (
                    <span key={`${source.sensor_id}-${sourceIndex}`} className="industrial-badge text-[var(--data-mono)]">
                      {source.sensor_id || source.id || 'source'}
                    </span>
                  ))}
                </div>
              )}
              <div className="caption-mono text-[var(--data-mono)] mt-3">
                {entry.source_type === 'claude' ? 'GROUNDED MODEL' : 'STRUCTURED'} / {new Date(entry.timestamp).toLocaleTimeString()}
              </div>
            </div>
          </div>
        ))}

        {queryLoading && (
          <div className="border border-[var(--border-strong)] p-4 caption-mono text-[var(--safe)]">
            ANALYZING...
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="border-t border-[var(--border-strong)] p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask for operating basis, evidence, or verification..."
            className="industrial-input flex-1"
            disabled={queryLoading}
          />
          <button
            type="submit"
            disabled={queryLoading || !input.trim()}
            className="industrial-control text-[var(--safe)] disabled:opacity-40"
          >
            Explain
          </button>
        </div>
      </form>
    </section>
  );
}
