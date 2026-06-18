import Panel from './Panel';
import { statusClass } from './studioUtils';

function modelLabel(value) {
  return String(value || 'Studio')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function actionState(step, build) {
  if (step.id === 'map') return step.courtItems > 0 ? 'READY' : 'WAIT';
  if (step.id === 'build') return build?.status || 'NOT_RUN';
  if (step.id === 'preview') return step.hasPreview ? 'READY' : 'WAIT';
  if (step.id === 'publish') return build?.can_publish ? 'READY' : 'BLOCKED';
  return 'OPTIONAL';
}

export default function WorkflowRail({
  overview,
  imported,
  court,
  build,
  preview,
  busy,
  actionMessage,
  onRunAutoMap,
  onRunBuild,
  onGeneratePreview,
  onPublish,
  onReset,
  onSwitchAssetModel,
  onToggleVerificationMutation,
}) {
  const selectedModel = overview?.selected_asset_model || overview?.state?.selected_asset_model || 'texas_city_vessel';
  const mutationEnabled = !!(overview?.template_mutations || overview?.state?.template_mutations)?.require_manual_verification_when_level_quarantined;
  const blockerCount = build?.validation?.blocking?.length || court?.counts?.blocking || 0;
  const courtItems = court?.items?.length || 0;
  const hasPreview = !!preview || !!(build?.generated_manifest && Object.keys(build.generated_manifest).length > 0);

  const nextStep = build?.can_publish
    ? 'Publish the generated Runtime when the preview matches the engineering intent.'
    : blockerCount
      ? 'Resolve blocking Mapping Court items, then run the build again.'
      : build?.status === 'PASS_WITH_WARNINGS'
        ? 'Review warnings and publish when acceptable for the demo.'
        : 'Run deterministic mapping, then run the compiler build.';

  const actions = [
    {
      id: 'map',
      label: 'Map Tags',
      description: 'Generate deterministic tag-to-asset proposals for Mapping Court.',
      onClick: onRunAutoMap,
      disabled: busy,
    },
    {
      id: 'build',
      label: 'Run Build',
      description: 'Validate asset graph, template bindings, guardrails, and publish readiness.',
      onClick: onRunBuild,
      disabled: busy,
    },
    {
      id: 'preview',
      label: 'Preview Runtime',
      description: 'Generate read-only Runtime screens without publishing them.',
      onClick: onGeneratePreview,
      disabled: busy,
    },
    {
      id: 'publish',
      label: 'Publish Runtime',
      description: build?.can_publish ? 'Make the latest generated manifest available to Runtime.' : 'Disabled until blocking validation clears.',
      onClick: onPublish,
      disabled: busy || !build?.can_publish,
    },
  ];

  return (
    <aside className="bg-[var(--surface-panel)] overflow-y-auto overflow-x-hidden scrollbar-thin">
      <Panel
        eyebrow="ConfidenceOS Studio"
        title="Compiler Workflow"
        right={<span className={`industrial-badge ${busy ? 'status-warning' : 'status-safe'}`}>{busy ? 'WORKING' : 'READY'}</span>}
        className="border-t-0"
      >
        <div className="space-y-4">
          <div>
            <label className="label-caps text-[var(--text-muted)]" htmlFor="asset-model-select">Asset Model</label>
            <select
              id="asset-model-select"
              value={selectedModel}
              onChange={(event) => onSwitchAssetModel(event.target.value)}
              className="industrial-input mt-2"
              disabled={busy}
            >
              {(overview?.asset_models || [
                { key: 'texas_city_vessel', label: 'Texas City Demo Vessel' },
                { key: 'pump_station', label: 'Pump Station Demo' },
              ]).map((model) => (
                <option key={model.key} value={model.key}>{model.label}</option>
              ))}
            </select>
          </div>

          <div className="industrial-panel-subtle p-3">
            <p className="label-caps text-[var(--text-muted)]">Next Engineering Step</p>
            <p className="caption-mono text-[var(--text)] mt-2">{nextStep}</p>
          </div>

          <div className="space-y-2">
            {actions.map((action, index) => {
              const state = actionState({ ...action, courtItems, hasPreview }, build);
              return (
                <button
                  key={action.id}
                  type="button"
                  onClick={action.onClick}
                  disabled={action.disabled}
                  className="w-full border border-[var(--border)] bg-[var(--surface-base)] p-3 text-left hover:border-[var(--primary)] disabled:opacity-40"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="label-caps text-[var(--text-muted)]">Step {index + 1}</span>
                    <span className={`industrial-badge ${statusClass(state)}`}>{state}</span>
                  </div>
                  <p className="text-[15px] font-semibold text-[var(--text)] mt-2">{action.label}</p>
                  <p className="caption-mono text-[var(--data-mono)] mt-1">{action.description}</p>
                </button>
              );
            })}
          </div>

          <button
            type="button"
            onClick={onReset}
            disabled={busy}
            className="industrial-control w-full text-[var(--data-mono)] disabled:opacity-40"
          >
            Reset Demo Default
          </button>

          {actionMessage && (
            <div className="industrial-panel-subtle p-3">
              <p className="label-caps text-[var(--text-muted)]">Latest Action</p>
              <p className="caption-mono text-[var(--data-mono)] mt-2">{actionMessage}</p>
            </div>
          )}
        </div>
      </Panel>

      <Panel eyebrow="Template Mutation" title="Controlled Change" className="mb-[1px]">
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={mutationEnabled}
            onChange={(event) => onToggleVerificationMutation(event.target.checked)}
            disabled={busy}
            className="mt-1 shrink-0"
          />
          <span>
            <span className="caption-mono text-[var(--text)] block">Require manual verification when primary level is quarantined.</span>
            <span className="caption-mono text-[var(--text-muted)] block mt-1">Run build to see the effect in publish diff and receipts.</span>
          </span>
        </label>
      </Panel>

      <Panel eyebrow="Imported Source" title="Read-Only Tag Provider">
        <div className="grid grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
          <div className="bg-[var(--surface-panel)] p-3">
            <p className="label-caps text-[var(--text-muted)]">Asset Signals</p>
            <p className="font-data text-2xl status-safe mt-1">{imported?.signals?.length || 0}</p>
          </div>
          <div className="bg-[var(--surface-panel)] p-3">
            <p className="label-caps text-[var(--text-muted)]">Raw Tags</p>
            <p className="font-data text-2xl status-safe mt-1">{courtItems}</p>
          </div>
        </div>
        <p className="caption-mono text-[var(--data-mono)] mt-3">{imported?.source || `${modelLabel(selectedModel)} asset model`}</p>
      </Panel>
    </aside>
  );
}
