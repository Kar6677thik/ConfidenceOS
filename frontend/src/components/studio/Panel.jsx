export default function Panel({ title, eyebrow, right, children, className = '' }) {
  return (
    <section className={`industrial-panel ${className}`}>
      <div className="industrial-panel-header">
        <div>
          {eyebrow && <p className="label-caps text-[var(--text-muted)]">{eyebrow}</p>}
          <h2 className="industrial-panel-title text-base">{title}</h2>
        </div>
        {right}
      </div>
      <div className="industrial-body">{children}</div>
    </section>
  );
}
