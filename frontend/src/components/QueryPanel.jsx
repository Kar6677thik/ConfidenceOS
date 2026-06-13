import { useState, useRef, useEffect } from 'react';
import useStore from '../store';

export default function QueryPanel() {
  const { queryHistory, queryLoading, askQuestion } = useStore();
  const [input, setInput] = useState('');
  const scrollRef = useRef(null);

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

  const suggestions = [
    'Why is LT-5100 flagged?',
    'Is the mass balance healthy?',
    'Which sensor needs attention?',
    'What is the current risk level?',
  ];

  return (
    <section className="industrial-panel h-full min-h-[360px] flex flex-col overflow-hidden">
      <div className="industrial-panel-header">
        <div>
          <h2 className="industrial-panel-title">Plant Query</h2>
          <p className="caption-mono text-[var(--data-mono)]">SYSTEM LOG / GROUNDED ANSWERS</p>
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
              <p className="label-caps text-[var(--text-muted)] mb-2">System Analysis</p>
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
                {entry.source_type === 'claude' ? 'CLAUDE' : 'STRUCTURED'} / {new Date(entry.timestamp).toLocaleTimeString()}
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
            placeholder="Ask anything about this plant..."
            className="industrial-input flex-1"
            disabled={queryLoading}
          />
          <button
            type="submit"
            disabled={queryLoading || !input.trim()}
            className="industrial-control text-[var(--safe)] disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </form>
    </section>
  );
}
