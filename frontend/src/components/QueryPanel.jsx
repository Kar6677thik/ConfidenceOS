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

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || queryLoading) return;
    const q = input.trim();
    setInput('');
    await askQuestion(q);
  };

  const suggestions = [
    'Why is LT-5100 flagged?',
    'Is the mass balance healthy?',
    'Which sensor needs attention?',
    'What is the current risk level?',
  ];

  return (
    <div className="flex flex-col h-full bg-gray-900/50 rounded-2xl border border-gray-800/50 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800/50">
        <h3 className="text-sm font-bold text-gray-200 flex items-center gap-2">
          <span className="text-cyan-400">⬡</span> Ask ConfidenceOS
        </h3>
        <p className="text-[10px] text-gray-500 mt-0.5">Ask anything about this plant in plain English</p>
      </div>

      {/* Conversation history */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3 scrollbar-thin">
        {queryHistory.length === 0 && (
          <div className="space-y-2">
            <p className="text-xs text-gray-500 italic">Try asking:</p>
            {suggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => { setInput(s); }}
                className="block w-full text-left text-xs px-3 py-2 rounded-lg bg-gray-800/40 text-gray-400 hover:text-gray-200 hover:bg-gray-800/70 transition-colors"
              >
                "{s}"
              </button>
            ))}
          </div>
        )}

        {queryHistory.map((entry, i) => (
          <div key={i} className="space-y-2">
            {/* User question */}
            <div className="flex justify-end">
              <div className="max-w-[85%] bg-cyan-500/15 text-cyan-100 px-3 py-2 rounded-xl rounded-tr-sm text-xs">
                {entry.question}
              </div>
            </div>
            {/* AI answer */}
            <div className="flex justify-start">
              <div className="max-w-[90%] bg-gray-800/60 text-gray-200 px-3 py-2 rounded-xl rounded-tl-sm text-xs leading-relaxed">
                {entry.answer}
                {entry.sources && entry.sources.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {entry.sources.map((s, j) => (
                      <span key={j} className="text-[9px] px-1.5 py-0.5 bg-gray-700/50 rounded text-gray-400 font-mono">
                        {s.sensor_id}
                      </span>
                    ))}
                  </div>
                )}
                <div className="text-[9px] text-gray-600 mt-1">
                  {entry.source_type === 'claude' ? '🤖 Claude' : '📊 Structured'} · {new Date(entry.timestamp).toLocaleTimeString()}
                </div>
              </div>
            </div>
          </div>
        ))}

        {queryLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-800/60 px-3 py-2 rounded-xl rounded-tl-sm text-xs text-gray-400">
              <span className="inline-flex gap-1">
                <span className="animate-bounce" style={{ animationDelay: '0ms' }}>●</span>
                <span className="animate-bounce" style={{ animationDelay: '150ms' }}>●</span>
                <span className="animate-bounce" style={{ animationDelay: '300ms' }}>●</span>
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="px-3 py-2 border-t border-gray-800/50">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about this plant..."
            className="flex-1 bg-gray-800/50 border border-gray-700/50 rounded-lg px-3 py-2 text-xs text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-1 focus:ring-cyan-500/40"
            disabled={queryLoading}
          />
          <button
            type="submit"
            disabled={queryLoading || !input.trim()}
            className="px-3 py-2 bg-cyan-500/20 text-cyan-400 rounded-lg text-xs font-semibold hover:bg-cyan-500/30 disabled:opacity-30 transition-colors"
          >
            Ask
          </button>
        </div>
      </form>
    </div>
  );
}
