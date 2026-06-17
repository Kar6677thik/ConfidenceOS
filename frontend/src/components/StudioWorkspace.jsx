import { useEffect, useMemo, useState } from 'react';
import useStore from '../store';
import PageIdentity from './hmi/PageIdentity';
import { PanelSkeleton, LoadFailed } from './PanelSkeleton';
import Panel from './studio/Panel';
import CompilerPipeline from './studio/CompilerPipeline';
import DirtyTagGauntlet from './studio/DirtyTagGauntlet';
import MappingCourt from './studio/MappingCourt';
import PasteImportPanel from './studio/PasteImportPanel';
import TemplateBindingTable from './studio/TemplateBindingTable';
import TemplateTestSuite from './studio/TemplateTestSuite';
import PublishDiff from './studio/PublishDiff';
import PublishGuardrails from './studio/PublishGuardrails';
import RuntimePreview from './studio/RuntimePreview';
import ScreenReceipts from './studio/ScreenReceipts';
import { fetchJson, statusClass } from './studio/studioUtils';

export default function StudioWorkspace() {
  const { role } = useStore();
  const [overview, setOverview] = useState(null);
  const [imported, setImported] = useState(null);
  const [build, setBuild] = useState(null);
  const [tests, setTests] = useState(null);
  const [court, setCourt] = useState(null);
  const [courtAiLabel, setCourtAiLabel] = useState('');
  const [preview, setPreview] = useState(null);
  const [selectedRawTag, setSelectedRawTag] = useState('');
  const [ignoreReason, setIgnoreReason] = useState('');
  const [manualCanonical, setManualCanonical] = useState('');
  const [manualAsset, setManualAsset] = useState('');
  const [manualRole, setManualRole] = useState('');
  const [manualReason, setManualReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionMessage, setActionMessage] = useState('');
  const [publishResult, setPublishResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const refresh = async () => {
    const [studio, importedSignals, buildPayload, testPayload, courtPayload] = await Promise.all([
      fetchJson('/api/studio'),
      fetchJson('/api/studio/imported-signals'),
      fetchJson('/api/studio/build'),
      fetchJson('/api/studio/template-tests'),
      fetchJson('/api/studio/mapping-court'),
    ]);
    setOverview(studio);
    setImported(importedSignals);
    setBuild(buildPayload);
    setTests(testPayload);
    setCourt(courtPayload);
    if (!selectedRawTag && courtPayload?.items?.length) {
      const first = courtPayload.items.find((item) => item.blocking) || courtPayload.items[0];
      setSelectedRawTag(first.raw_tag);
    }
  };

  const doLoad = () => {
    setLoading(true);
    setLoadError('');
    refresh()
      .then(() => setLoading(false))
      // eslint-disable-next-line react-hooks/set-state-in-effect
      .catch((err) => {
        setLoading(false);
        setLoadError(err.message || 'Studio data unavailable — check API connection.');
        setOverview(null);
        setImported(null);
        setBuild(null);
        setTests(null);
        setCourt(null);
      });
  };

  useEffect(() => {
    doLoad();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const mappingItems = useMemo(
    () => court?.items || build?.imported_tags?.items || imported?.raw_tags || [],
    [build, court, imported],
  );
  const selectedItem = useMemo(
    () => mappingItems.find((item) => item.raw_tag === selectedRawTag) || mappingItems[0],
    [mappingItems, selectedRawTag],
  );
  const validation = build?.validation || overview?.validation?.compiler || overview?.validation || {};
  const runtimeManifest = (build?.generated_manifest && Object.keys(build.generated_manifest).length > 0)
    ? build.generated_manifest
    : preview;
  const graphSignals = overview?.graph?.signals || [];
  const graphAssets = (overview?.graph?.assets || overview?.assets || []).filter((asset) => ['process_vessel', 'valve', 'flow_pair', 'pump'].includes(asset.asset_type));
  const signalRoles = [...new Set(graphSignals.map((signal) => signal.role || signal.sensor_type).filter(Boolean))];

  useEffect(() => {
    if (!selectedItem) return;
    /* eslint-disable react-hooks/set-state-in-effect */
    setManualCanonical(selectedItem.proposed_canonical_tag || '');
    setManualAsset(selectedItem.proposed_asset_id || '');
    setManualRole(selectedItem.proposed_role || '');
    setManualReason('');
    /* eslint-enable react-hooks/set-state-in-effect */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedItem?.raw_tag]);

  const runAction = async (fn) => {
    setBusy(true);
    setActionMessage('');
    try {
      await fn();
      await refresh();
    } catch (err) {
      setActionMessage(err.payload?.detail?.reason || err.payload?.reason || err.message || 'Action failed.');
    } finally {
      setBusy(false);
    }
  };

  const runAutoMap = () => runAction(async () => {
    const payload = await fetchJson('/api/studio/auto-map', { method: 'POST' });
    const newCourt = payload.mapping_court || court;
    if (newCourt) setCourt(newCourt);
    setCourtAiLabel(payload.ai_label || '');
    setActionMessage(
      payload.ai_assisted
        ? 'Optional AI explanations attached to Mapping Court items. Deterministic mapping remains authoritative; review and approve each tag.'
        : 'Deterministic mapping complete. AI explanation unavailable (no key). Review and approve each tag.',
    );
  });

  const runBuild = () => runAction(async () => {
    const payload = await fetchJson('/api/studio/build/run', { method: 'POST' });
    setBuild(payload);
    setPublishResult(null);
    setActionMessage(payload.can_publish ? 'Build passed with publish readiness.' : 'Build failed. Resolve blocking guardrails and run again.');
  });

  const generatePreview = () => runAction(async () => {
    const payload = await fetchJson('/api/studio/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role, context: 'auto' }),
    });
    setPreview(payload);
  });

  const publish = () => runAction(async () => {
    try {
      const payload = await fetchJson('/api/studio/publish', { method: 'POST' });
      setPublishResult(payload);
    } catch (err) {
      setPublishResult(err.payload?.detail || err.payload || { status: 'blocked', reason: err.message });
      throw err;
    }
  });

  const reset = () => runAction(async () => {
    await fetchJson('/api/studio/reset', { method: 'POST' });
    setPreview(null);
    setPublishResult(null);
    setIgnoreReason('');
    setSelectedRawTag('');
    setManualCanonical('');
    setManualAsset('');
    setManualRole('');
    setManualReason('');
  });

  const approveSelected = () => runAction(async () => {
    if (!selectedItem) return;
    const payload = await fetchJson('/api/studio/mapping-court/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_tag: selectedItem.raw_tag }),
    });
    setActionMessage(`${payload.mapping?.raw_tag || selectedItem.raw_tag} approved. Run build again.`);
  });

  const ignoreSelected = () => runAction(async () => {
    if (!selectedItem) return;
    const payload = await fetchJson('/api/studio/mapping-court/ignore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_tag: selectedItem.raw_tag, reason: ignoreReason }),
    });
    setActionMessage(`${payload.mapping?.raw_tag || selectedItem.raw_tag} ignored. Run build again.`);
  });

  const keepBlocking = () => runAction(async () => {
    if (!selectedItem) return;
    await fetchJson('/api/studio/mapping-court/keep-blocking', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_tag: selectedItem.raw_tag }),
    });
    setActionMessage(`${selectedItem.raw_tag} remains blocking. Publish stays disabled.`);
  });

  const manualMapSelected = () => runAction(async () => {
    if (!selectedItem) return;
    const payload = await fetchJson('/api/studio/mapping-court/manual-map', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_tag: selectedItem.raw_tag,
        canonical_tag: manualCanonical,
        asset_id: manualAsset,
        signal_role: manualRole,
        reason: manualReason,
      }),
    });
    setActionMessage(`${payload.mapping?.raw_tag || selectedItem.raw_tag} manually mapped. Run build again.`);
  });

  const switchAssetModel = (modelKey) => runAction(async () => {
    await fetchJson('/api/studio/asset-model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_key: modelKey }),
    });
    setPreview(null);
    setPublishResult(null);
    setSelectedRawTag('');
    setManualCanonical('');
    setManualAsset('');
    setManualRole('');
    setManualReason('');
    setActionMessage('Asset model switched. Run build to compile the selected model.');
  });

  const toggleVerificationMutation = (enabled) => runAction(async () => {
    await fetchJson('/api/studio/template-mutation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ require_manual_verification_when_level_quarantined: enabled }),
    });
    setPreview(null);
    setPublishResult(null);
    setActionMessage('Template mutation updated. Run build to see publish diff and receipts.');
  });

  return (
    <div className="industrial-page grid grid-rows-[48px_minmax(0,1fr)] bg-[var(--border-strong)] gap-[1px] overflow-hidden">
      <div className="hmi-alarm-band">
        <div className={`hmi-band-cell ${build?.can_publish ? '' : 'hmi-band-warning'}`}>
          <span className={`hmi-status-symbol ${build?.can_publish ? 'normal' : 'p2'}`}>{build?.can_publish ? 'N' : '2'}</span>
          <div className="min-w-0">
            <p className="label-caps text-[var(--text-muted)]">HMI Compiler</p>
            <p className="caption-mono font-semibold truncate">Raw Tags {'->'} Asset Graph {'->'} Template Binding {'->'} Runtime</p>
          </div>
        </div>
        <div className="hmi-band-cell">
          <span className={`caption-mono font-semibold ${statusClass(build?.status || 'NOT_RUN')}`}>{build?.status || 'NOT_RUN'}</span>
          <span className="caption-mono text-[var(--text-muted)]">publish gate: {build?.can_publish ? 'ready' : 'blocked until validation clears'}</span>
          <span className="caption-mono text-[var(--text-dim)]">{build?.build_id || 'no build run yet'}</span>
        </div>
        <div className="hmi-band-cell justify-end">
          <span className="caption-mono">{role}</span>
          <span className="caption-mono">read-only trust-aware HMI compiler</span>
        </div>
      </div>
      <div className="grid grid-cols-[minmax(280px,320px)_minmax(520px,1fr)_minmax(320px,380px)] gap-[1px] bg-[var(--border-strong)] overflow-hidden min-h-0">
      <aside className="bg-[var(--surface-panel)] overflow-y-auto overflow-x-hidden scrollbar-thin">
        <Panel
          eyebrow="ConfidenceOS Studio"
          title="HMI Compiler Controls"
          right={<span className={`industrial-badge ${busy ? 'status-warning' : 'status-safe'}`}>{busy ? 'working' : 'ready'}</span>}
          className="border-t-0"
        >
          <div className="space-y-3">
            <div>
              <label className="label-caps text-[var(--text-muted)]" htmlFor="asset-model-select">Asset Model</label>
              <select
                id="asset-model-select"
                value={overview?.selected_asset_model || overview?.state?.selected_asset_model || 'texas_city_vessel'}
                onChange={(event) => switchAssetModel(event.target.value)}
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
            <div className="border border-[var(--border-strong)] bg-[var(--surface-base)] p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="label-caps text-[var(--text-muted)]">Controlled Template Mutation</p>
                  <p className="caption-mono text-[var(--text)] mt-1">Require manual verification when primary level is quarantined.</p>
                </div>
                <input
                  type="checkbox"
                  checked={!!(overview?.template_mutations || overview?.state?.template_mutations)?.require_manual_verification_when_level_quarantined}
                  onChange={(event) => toggleVerificationMutation(event.target.checked)}
                  disabled={busy}
                  className="mt-1"
                />
              </div>
            </div>
            <button onClick={runAutoMap} disabled={busy} className="industrial-control w-full disabled:opacity-40" style={{borderColor: 'var(--safe)', color: 'var(--safe-text)'}}>Run Deterministic Mapping</button>
            <button onClick={runBuild} disabled={busy} className="industrial-control status-safe w-full disabled:opacity-40">Run Build</button>
            <button onClick={generatePreview} disabled={busy} className="industrial-control text-[var(--text)] w-full disabled:opacity-40">Generate Preview</button>
            <button onClick={publish} disabled={busy || !build?.can_publish} className="industrial-control status-warning w-full disabled:opacity-40">Publish Latest Build</button>
            <button onClick={reset} disabled={busy} className="industrial-control text-[var(--data-mono)] w-full disabled:opacity-40">Reset Demo Default</button>
          </div>
          <div className="industrial-panel-subtle p-3 mt-4">
            <p className="label-caps text-[var(--text-muted)]">Demo Loop</p>
            <p className="caption-mono text-[var(--data-mono)] mt-2">Run build / resolve dirty tag / run build again / publish latest build.</p>
          </div>
        </Panel>
        <DirtyTagGauntlet court={court} selectedRawTag={selectedItem?.raw_tag} onSelect={(tag) => { setSelectedRawTag(tag); setIgnoreReason(''); setActionMessage(''); }} />
        <Panel eyebrow="Imported Source" title="Read-Only Tag Provider">
          <div className="grid grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="label-caps text-[var(--text-muted)]">Asset Signals</p>
              <p className="font-data text-2xl status-safe mt-1">{imported?.signals?.length || 0}</p>
            </div>
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="label-caps text-[var(--text-muted)]">Raw Tags</p>
              <p className="font-data text-2xl status-safe mt-1">{mappingItems.length}</p>
            </div>
          </div>
          <p className="caption-mono text-[var(--data-mono)] mt-3">{imported?.source || 'Waiting for Studio import.'}</p>
        </Panel>
      </aside>

      <main className="bg-[var(--surface-base)] flex flex-col overflow-hidden">
        <PageIdentity
          displayName={overview?.selected_asset_model
            ? overview.selected_asset_model.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
            : 'Studio'}
          level={2}
          area="Engineering Configuration Workspace"
        />
        <div className="flex-1 overflow-y-auto overflow-x-hidden scrollbar-thin p-[1px]">
          {loading && !overview ? (
            <PanelSkeleton rows={6} />
          ) : loadError ? (
            <LoadFailed message={loadError} onRetry={doLoad} />
          ) : (
            <>
              <CompilerPipeline build={build} />
              <MappingCourt
                item={selectedItem}
                aiLabel={courtAiLabel}
                assets={graphAssets}
                signals={graphSignals}
                signalRoles={signalRoles}
                ignoreReason={ignoreReason}
                onIgnoreReason={setIgnoreReason}
                manualCanonical={manualCanonical}
                onManualCanonical={setManualCanonical}
                manualAsset={manualAsset}
                onManualAsset={setManualAsset}
                manualRole={manualRole}
                onManualRole={setManualRole}
                manualReason={manualReason}
                onManualReason={setManualReason}
                onManualMap={manualMapSelected}
                onApprove={approveSelected}
                onIgnore={ignoreSelected}
                onKeepBlocking={keepBlocking}
                busy={busy}
                actionMessage={actionMessage}
              />
              <TemplateBindingTable validation={validation} busy={busy} />
              <TemplateTestSuite tests={tests} />
              <PublishDiff diff={build?.publish_diff || overview?.diff?.compiler_publish_diff} />
              <RuntimePreview manifest={runtimeManifest} />
            </>
          )}
        </div>
      </main>

      <aside className="bg-[var(--surface-panel)] overflow-y-auto overflow-x-hidden scrollbar-thin">
        <PasteImportPanel busy={busy} onImportResult={() => {}} />
        <PublishGuardrails build={build} onPublish={publish} busy={busy} result={publishResult} />
        <ScreenReceipts manifest={runtimeManifest} />
      </aside>
      </div>
    </div>
  );
}
