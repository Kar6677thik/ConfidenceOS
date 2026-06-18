import Panel from './Panel';
import { formatText, statusClass } from './studioUtils';

const STAGE_LABELS = {
  import: 'Import',
  mapping: 'Mapping',
  template_binding: 'Template Binding',
  validation: 'Validation',
  screen_generation: 'Screen Generation',
  publish_readiness: 'Publish Readiness',
  runtime: 'Runtime',
};

const STATUS_LABELS = {
  PASS: 'PASS',
  PASS_WITH_WARNINGS: 'WARN',
  WARNING: 'WARN',
  BLOCKING: 'BLOCK',
  BLOCKED: 'BLOCK',
  FAILED: 'FAIL',
  NOT_RUN: 'WAIT',
};

function compactStatus(value) {
  const status = String(value || 'NOT_RUN').toUpperCase();
  return STATUS_LABELS[status] || status;
}

export default function CompilerPipeline({ build }) {
  const stages = build?.stages || [
    { id: 'import', status: 'NOT_RUN' },
    { id: 'mapping', status: 'NOT_RUN' },
    { id: 'template_binding', status: 'NOT_RUN' },
    { id: 'validation', status: 'NOT_RUN' },
    { id: 'screen_generation', status: 'NOT_RUN' },
    { id: 'publish_readiness', status: 'NOT_RUN' },
  ];
  return (
    <Panel
      eyebrow="HMI Compiler Pipeline"
      title="Raw Tags To Runtime Build"
      right={<span className={`industrial-badge ${statusClass(build?.status || 'NOT_RUN')}`}>{build?.status || 'NOT_RUN'}</span>}
      className="mb-[1px]"
    >
      <div className="overflow-x-auto overflow-y-hidden scrollbar-thin">
      <div className="grid min-w-[980px] grid-cols-6 gap-[1px] bg-[var(--border-strong)]">
        {stages.filter((stage) => stage.id !== 'runtime').map((stage) => (
          <div key={stage.id} className="bg-[var(--surface-panel)] p-3 min-h-[92px]">
            <span className={`industrial-badge ${statusClass(stage.status || 'NOT_RUN')}`} title={formatText(stage.status || 'NOT_RUN')}>
              {compactStatus(stage.status)}
            </span>
            <p className="label-caps text-[var(--text-muted)] mt-3">Stage</p>
            <p className="caption-mono text-[var(--text)] mt-1">{stage.label || STAGE_LABELS[stage.id] || formatText(stage.id)}</p>
          </div>
        ))}
      </div>
      </div>
      <div className="mt-4 grid grid-cols-1 xl:grid-cols-3 gap-[1px] bg-[var(--border-strong)]">
        <div className="bg-[var(--surface-panel)] p-3">
          <p className="label-caps text-[var(--text-muted)]">Build ID</p>
          <p className="caption-mono text-[var(--text)] mt-1">{build?.build_id || 'No build run yet'}</p>
        </div>
        <div className="bg-[var(--surface-panel)] p-3">
          <p className="label-caps text-[var(--text-muted)]">Publish Gate</p>
          <p className={`caption-mono mt-1 ${build?.can_publish ? 'status-safe' : 'status-critical'}`}>
            {build?.can_publish ? 'can publish latest build' : 'publish refused until blocking issues clear'}
          </p>
        </div>
        <div className="bg-[var(--surface-panel)] p-3">
          <p className="label-caps text-[var(--text-muted)]">Compiler Contract</p>
          <p className="caption-mono text-[var(--data-mono)] mt-1">read-only trust-aware HMI layer beside existing DCS/HMI</p>
          <p className="caption-mono text-[var(--text-muted)] mt-1">forbidden writes: tag values / setpoints / controller modes / DCS alarm acknowledgements</p>
        </div>
      </div>
    </Panel>
  );
}
