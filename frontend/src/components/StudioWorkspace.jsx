import { useEffect, useState } from 'react';
import useStore from '../store';

function formatText(value) {
  return String(value || '').replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

const ABB_ALIGNMENT_CHECKLIST = [
  ['auto-generated HMI screens', 'Runtime manifests and faceplates generated from asset metadata and approved templates.'],
  ['reusable templates', 'Studio template library covers vessel, valve, flow pair, and abnormal situation patterns.'],
  ['metadata-driven engineering', 'Asset/signal graph is the source of truth for navigation, evidence, and generated screens.'],
  ['AI-assisted configuration', 'AI suggests mappings when available; deterministic suggestions remain visible and engineer approval is required.'],
  ['low-code/no-code editing', 'Engineers approve mappings, change template assignments, preview, publish, and reset without editing code.'],
  ['role-based UI', 'Operator, Maintenance, Engineer, Manager, and Auditor roles receive different generated sections.'],
  ['context-aware UI', 'Runtime switches to stress mode when WARNING or CRITICAL context is inferred.'],
  ['modern UX pattern used', 'Semantic zoom, guided mapping, preview/diff, and persistent shift channel supersede fixed screen layouts.'],
  ['faster decision-making mechanism', 'Operating basis compresses situation, do-not-trust, trusted substitute, first action, and exit condition.'],
  ['alarm-fatigue reduction mechanism', 'Alarm collapse changes many low-level warnings into one abnormal situation workspace.'],
  ['safety/system-awareness mechanism', 'Decision freezes, verification-required states, assumptions, and read-only integration are visible.'],
  ['engineering-effort reduction mechanism', 'Import / auto-map / template assignment / generate / publish reduces hand-built screen work.'],
  ['consistency mechanism', 'Reusable templates, validation warnings, provenance, and published revisions standardize generated HMIs.'],
];

export default function StudioWorkspace() {
  const { role } = useStore();
  const [overview, setOverview] = useState(null);
  const [signals, setSignals] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => {
    Promise.all([
      fetch('/api/studio').then((res) => (res.ok ? res.json() : null)),
      fetch('/api/studio/imported-signals').then((res) => (res.ok ? res.json() : null)),
    ])
      .then(([studio, imported]) => {
        setOverview(studio);
        setSignals(imported);
        setSuggestions(studio?.state?.suggestions || []);
      })
      .catch(() => {
        setOverview(null);
        setSignals(null);
      });
  };

  useEffect(() => {
    refresh();
  }, []);

  const runAction = async (fn) => {
    setBusy(true);
    try {
      await fn();
      refresh();
    } finally {
      setBusy(false);
    }
  };

  const autoMap = () => runAction(async () => {
    const res = await fetch('/api/studio/auto-map', { method: 'POST' });
    const payload = await res.json();
    setSuggestions(payload.suggestions || []);
  });

  const approve = (item) => runAction(async () => {
    await fetch('/api/studio/assign-template', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_id: item.asset_id, template_id: item.template_id, approved: true }),
    });
  });

  const generate = () => runAction(async () => {
    const res = await fetch('/api/studio/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role, context: 'auto' }),
    });
    setPreview(await res.json());
  });

  const publish = () => runAction(async () => {
    await fetch('/api/studio/publish', { method: 'POST' });
  });

  const updateAssignment = (assetId, templateId) => runAction(async () => {
    await fetch('/api/studio/assign-template', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_id: assetId, template_id: templateId, approved: true }),
    });
  });

  const reset = () => runAction(async () => {
    await fetch('/api/studio/reset', { method: 'POST' });
    setPreview(null);
  });

  const templates = overview?.templates?.equipment_templates || [];
  const validation = overview?.validation || {};
  const diff = overview?.diff || {};

  return (
    <div className="industrial-page grid grid-cols-[340px_1fr_420px] gap-[1px] bg-[var(--border-strong)] overflow-hidden">
      <aside className="bg-[var(--surface-panel)] overflow-y-auto scrollbar-thin">
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <div>
              <p className="label-caps text-[var(--text-muted)]">ConfidenceOS Studio</p>
              <h1 className="industrial-panel-title text-base">Asset Model / Signal Binding</h1>
            </div>
          </div>
          <div className="industrial-body space-y-4">
            <button onClick={autoMap} disabled={busy} className="industrial-control status-safe w-full disabled:opacity-50">
              {busy ? 'Working...' : 'Suggest Signal Binding'}
            </button>
            <button onClick={generate} disabled={busy} className="industrial-control text-[var(--text)] w-full disabled:opacity-50">
              Generate Publish Preview
            </button>
            <button onClick={publish} disabled={busy} className="industrial-control status-warning w-full disabled:opacity-50">
              Publish To Runtime
            </button>
            <button onClick={reset} disabled={busy} className="industrial-control text-[var(--data-mono)] w-full disabled:opacity-50">
              Reset Demo Default
            </button>
            <div className="industrial-panel-subtle p-3">
              <p className="label-caps text-[var(--text-muted)]">Imported Signals</p>
              <p className="font-data text-3xl status-safe mt-2">{signals?.signals?.length || 0}</p>
              <p className="caption-mono text-[var(--data-mono)] mt-1">{signals?.source || 'waiting for asset model import'}</p>
            </div>
          </div>
        </section>
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">Template Library</h2>
          </div>
          <div className="industrial-body space-y-[1px] bg-[var(--border-strong)]">
            {templates.map((template) => (
              <div key={template.template_id} className="bg-[var(--surface-panel)] p-3">
                <p className="label-caps text-[var(--text)]">{template.label}</p>
                <p className="caption-mono text-[var(--data-mono)] mt-1">{template.required_signal_types?.join(', ') || 'no required signals'}</p>
              </div>
            ))}
          </div>
        </section>
      </aside>

      <main className="bg-[var(--surface-base)] p-[1px] overflow-y-auto scrollbar-thin">
        <section className="industrial-panel mb-[1px]">
          <div className="industrial-panel-header">
            <div>
              <p className="label-caps text-[var(--text-muted)]">Low-Code Engineering Flow</p>
              <h1 className="industrial-panel-title">Studio To Runtime Demo Path</h1>
              <p className="caption-mono text-[var(--data-mono)] mt-2">Studio / generate screens / Runtime / abnormal situation / role views / unresolved handover debt</p>
            </div>
            <span className={`industrial-badge ${validation.status === 'valid' ? 'status-safe' : 'status-warning'}`}>{validation.status || 'loading'}</span>
          </div>
        </section>

        <section className="industrial-panel mb-[1px]">
          <div className="industrial-panel-header">
            <div>
              <p className="label-caps text-[var(--text-muted)]">ABB Desired-Solution Checklist</p>
              <h2 className="industrial-panel-title text-base">Visible Demo Coverage</h2>
            </div>
            <span className="industrial-badge status-safe">{ABB_ALIGNMENT_CHECKLIST.length} represented</span>
          </div>
          <div className="industrial-body grid grid-cols-1 xl:grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
            {ABB_ALIGNMENT_CHECKLIST.map(([label, mechanism]) => (
              <div key={label} className="bg-[var(--surface-panel)] p-3 min-h-[92px]">
                <p className="label-caps status-safe">{label}</p>
                <p className="caption-mono text-[var(--data-mono)] mt-2">{mechanism}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="industrial-panel mb-[1px]">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">AI Suggests / Engineer Approves</h2>
            <span className="industrial-badge text-[var(--data-mono)]">approval required</span>
          </div>
          <div className="industrial-body space-y-[1px] bg-[var(--border-strong)]">
            {suggestions.map((item) => (
              <div key={`${item.asset_id}-${item.template_id}`} className="grid grid-cols-[1fr_140px] gap-[1px] bg-[var(--border-strong)]">
                <div className="bg-[var(--surface-panel)] p-4">
                  <p className="label-caps text-[var(--text)]">{item.asset_name}</p>
                  <p className="caption-mono text-[var(--data-mono)] mt-1">{item.reason}</p>
                  <p className="caption-mono status-safe mt-2">{item.signal_tags?.join(' / ')}</p>
                </div>
                <div className="bg-[var(--surface-panel)] p-4 flex flex-col gap-2">
                  <p className="caption-mono text-[var(--text)]">{formatText(item.template_id)}</p>
                  <button onClick={() => approve(item)} className="industrial-control status-safe">Approve</button>
                </div>
              </div>
            ))}
            {suggestions.length === 0 && (
              <p className="bg-[var(--surface-panel)] p-4 caption-mono text-[var(--data-mono)]">Run signal binding suggestions to generate deterministic, approval-required mappings.</p>
            )}
          </div>
        </section>

        <section className="industrial-panel">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">Publish Preview / Generated From Template</h2>
            <span className="industrial-badge text-[var(--data-mono)]">{preview?.faceplates?.length || 0} faceplates</span>
          </div>
          <div className="industrial-body">
            {preview ? (
              <div className="space-y-4">
                <p className="caption-mono text-[var(--text)]">{preview.manifest_id}</p>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
                  {(preview.faceplates || []).map((faceplate) => (
                    <div key={faceplate.equipment_id} className="bg-[var(--surface-panel)] p-4">
                      <p className="label-caps status-safe">{faceplate.template_label}</p>
                      <p className="text-[var(--text)] font-bold mt-1">{faceplate.title}</p>
                      <p className="caption-mono text-[var(--data-mono)] mt-2">
                        {faceplate.signals?.map((signal) => signal.tag).join(' / ')}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="caption-mono text-[var(--data-mono)]">Generate a publish preview to inspect Runtime screens, template provenance, and signal binding before publish.</p>
            )}
          </div>
        </section>
      </main>

      <aside className="bg-[var(--surface-panel)] overflow-y-auto scrollbar-thin">
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">Validation Warning</h2>
          </div>
          <div className="industrial-body space-y-[1px] bg-[var(--border-strong)]">
            {(validation.warnings || []).map((warning) => (
              <div key={`${warning.asset_id}-${warning.message}`} className="bg-[var(--surface-panel)] p-3">
                <p className="label-caps status-warning">{warning.asset_id}</p>
                <p className="caption-mono text-[var(--data-mono)] mt-1">{warning.message}</p>
              </div>
            ))}
            {(!validation.warnings || validation.warnings.length === 0) && (
              <p className="bg-[var(--surface-panel)] p-3 caption-mono status-safe">No blocking validation warnings.</p>
            )}
          </div>
        </section>
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">Publish Preview Diff</h2>
          </div>
          <div className="industrial-body">
            <p className="caption-mono text-[var(--data-mono)]">{diff.change_count || 0} change(s) from demo default.</p>
            <pre className="industrial-panel-subtle p-3 caption-mono text-[var(--data-mono)] whitespace-pre-wrap mt-3">
              {JSON.stringify(diff.changes || [], null, 2)}
            </pre>
          </div>
        </section>
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">Low-Code Template Assignment</h2>
          </div>
          <div className="industrial-body space-y-[1px] bg-[var(--border-strong)]">
            {(overview?.state?.assignments || []).map((item) => (
              <div key={`${item.asset_id}-${item.template_id}`} className="bg-[var(--surface-panel)] p-3">
                <p className="caption-mono text-[var(--text)]">{item.asset_id} / {item.template_id}</p>
                <p className="caption-mono text-[var(--data-mono)] mt-1">approved {String(item.approved)}</p>
                <select
                  value={item.template_id}
                  onChange={(event) => updateAssignment(item.asset_id, event.target.value)}
                  className="industrial-select mt-3"
                  disabled={busy}
                >
                  {templates.map((template) => (
                    <option key={template.template_id} value={template.template_id}>{template.label}</option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        </section>
      </aside>
    </div>
  );
}
