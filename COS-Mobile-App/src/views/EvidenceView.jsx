import useStore from '../store';

export default function EvidenceView() {
  const tasks = useStore((s) => s.tasks);

  return (
    <div>
      {/* Header */}
      <div style={{ padding: '16px 16px 4px', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>
          Field Evidence Capture
        </span>
        <span className="beta-pill">BETA</span>
      </div>

      <div style={{ padding: '4px 16px 16px', fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>
        Attach photo or voice evidence to a verification task. AI will parse and pre-fill checklist fields automatically.
      </div>

      {/* Capture area */}
      <div style={{ padding: '0 12px' }}>
        <div className="evidence-capture-area">
          <span className="evidence-icon">📷</span>
          <div className="evidence-capture-label">
            Tap "Take Photo" to capture field evidence. The AI Root Cause Explainer will auto-populate the linked task.
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-dim)', textAlign: 'center' }}>
            Supports: photos, voice memos, handwritten notes
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <button
        className="evidence-btn"
        disabled
        title="AI integration coming soon"
        style={{ display: 'block' }}
      >
        📷 Take Photo
      </button>
      <button
        className="evidence-btn"
        disabled
        title="AI integration coming soon"
        style={{ display: 'block' }}
      >
        🎙 Record Voice Note
      </button>

      {/* Task connector */}
      <div className="section-label" style={{ marginTop: 8 }}>Connect to Task</div>
      <select className="connect-task-select" disabled>
        <option value="">Select a task to link evidence…</option>
        {tasks.filter((t) => t.status !== 'DONE').map((t) => (
          <option key={t.id} value={t.id}>
            {t.tag} — {t.desc}
          </option>
        ))}
      </select>

      {/* Info card */}
      <div className="mobile-card" style={{ marginTop: 12 }}>
        <div className="mobile-card-body">
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', marginBottom: 8 }}>
            Coming in next release
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              { icon: '◈', text: 'Voice-to-Evidence parser — dictate findings, AI fills checklist' },
              { icon: '▣', text: 'Image-to-Field Check — photo of gauge auto-reads the value' },
              { icon: '⊕', text: 'AI Root Cause Explainer — links evidence to probable fault' },
            ].map(({ icon, text }) => (
              <div key={text} style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <span style={{ color: 'var(--primary)', fontSize: 13, flexShrink: 0, marginTop: 1 }}>{icon}</span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.45 }}>{text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ height: 12 }} />
    </div>
  );
}
