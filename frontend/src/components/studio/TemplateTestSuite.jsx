import Panel from './Panel';
import { formatText, statusClass } from './studioUtils';

export default function TemplateTestSuite({ tests }) {
  const rows = tests?.tests || [];
  return (
    <Panel
      eyebrow="Template Test Suite"
      title="Deterministic Runtime Checks"
      right={<span className={`industrial-badge ${statusClass(tests?.status || 'NOT_RUN')}`}>{tests?.status || 'NOT_RUN'}</span>}
      className="mb-[1px]"
    >
      <div className="space-y-[1px] bg-[var(--border-strong)]">
        {rows.map((test) => (
          <div key={test.test_id} className="grid grid-cols-1 xl:grid-cols-[180px_110px_1fr] gap-[1px] bg-[var(--border-strong)]">
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="label-caps text-[var(--text-muted)]">{test.template_id}</p>
              <p className={`caption-mono mt-1 ${statusClass(test.status)}`}>{test.status}</p>
            </div>
            <p className="bg-[var(--surface-panel)] p-3 caption-mono text-[var(--text)]">{formatText(test.template_id)}</p>
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="caption-mono text-[var(--text)]">{formatText(test.test_id)}</p>
              <p className="caption-mono text-[var(--data-mono)] mt-1">{test.message}</p>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}
