import { useEffect, useMemo, useState } from 'react';
import useStore from '../store';
import PageIdentity from './hmi/PageIdentity';
import { PanelSkeleton, LoadFailed } from './PanelSkeleton';
import WorkflowRail from './studio/WorkflowRail';
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

function modelLabel(value) {
  return String(value || 'Studio')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function selectBestMappingItem(items, currentRawTag) {
  if (!items?.length) return '';
  if (currentRawTag && items.some((item) => item.raw_tag === currentRawTag)) return currentRawTag;
  return (
    items.find((item) => item.blocking)?.raw_tag
    || items.find((item) => String(item.bucket || '').toLowerCase() === 'unmapped')?.raw_tag
    || items.find((item) => String(item.bucket || '').toLowerCase() === 'ambiguous')?.raw_tag
    || items[0].raw_tag
  );
}

export default function StudioWorkspace() {
  const { role, plantId, setRole } = useStore();
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
    setSelectedRawTag((current) => selectBestMappingItem(courtPayload?.items, current));
  };

  const doLoad = () => {
    setLoading(true);
    setLoadError('');
    refresh()
      .then(() => setLoading(false))
      .catch((err) => {
        setLoading(false);
        setLoadError(err.message || 'Studio data unavailable - check API connection.');
        setOverview(null);
        setImported(null);
        setBuild(null);
        setTests(null);
        setCourt(null);
      });
  };

  useEffect(() => {
    // Initial load synchronizes Studio with backend compiler state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh()
      .then(() => setLoading(false))
      .catch((err) => {
        setLoading(false);
        setLoadError(err.message || 'Studio data unavailable - check API connection.');
        setOverview(null);
        setImported(null);
        setBuild(null);
        setTests(null);
        setCourt(null);
      });
  }, []);

  useEffect(() => {
    if (!['Engineer', 'Manager'].includes(role)) {
      // Route guard: Studio is an engineering workspace even if opened by URL.
      setRole('Engineer');
    }
  }, [role, setRole]);

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
        ? 'Optional AI explanations attached. Deterministic mapping remains authoritative; review and approve each tag.'
        : 'Deterministic mapping complete. AI explanation unavailable; review and approve each tag.',
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
    await fetchJson(`/api/simulation/reset-source?plant_id=${plantId}`, { method: 'POST' }).catch(() => null);
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
    setActionMessage('Asset model switched. Run deterministic mapping, then build to compile the selected model.');
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

  const importResult = () => {
    setActionMessage('Imported tag list parsed. Run deterministic mapping to update Mapping Court.');
    refresh().catch((err) => {
      setActionMessage(err.message || 'Imported tags parsed, but Studio refresh failed.');
    });
  };

  const pageTitle = modelLabel(overview?.selected_asset_model);

  const studioContent = loading && !overview ? (
    <PanelSkeleton rows={6} />
  ) : loadError ? (
    <LoadFailed message={loadError} onRetry={doLoad} />
  ) : (
    <div className="studio-professional-layout">
      <WorkflowRail
        overview={overview}
        imported={imported}
        court={court}
        build={build}
        preview={runtimeManifest}
        busy={busy}
        actionMessage={actionMessage}
        onRunAutoMap={runAutoMap}
        onRunBuild={runBuild}
        onGeneratePreview={generatePreview}
        onPublish={publish}
        onReset={reset}
        onSwitchAssetModel={switchAssetModel}
        onToggleVerificationMutation={toggleVerificationMutation}
      />

      <main className="studio-professional-main">
        <section className="studio-board-section">
          <CompilerPipeline build={build} />
          <div className="grid grid-cols-1 2xl:grid-cols-[minmax(360px,0.8fr)_minmax(0,1.2fr)] gap-[1px] bg-[var(--border-strong)]">
            <DirtyTagGauntlet
              court={court}
              selectedRawTag={selectedItem?.raw_tag}
              onSelect={(tag) => {
                setSelectedRawTag(tag);
                setIgnoreReason('');
                setActionMessage('');
              }}
            />
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
          </div>
        </section>

        <section className="studio-board-section">
          <TemplateBindingTable validation={validation} busy={busy} />
          <TemplateTestSuite tests={tests} />
        </section>

        <section className="studio-board-section">
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.7fr)] gap-[1px] bg-[var(--border-strong)]">
            <PasteImportPanel busy={busy} onImportResult={importResult} />
            <PublishGuardrails build={build} onPublish={publish} busy={busy} result={publishResult} />
          </div>
          <PublishDiff diff={build?.publish_diff || overview?.diff?.compiler_publish_diff} />
          <RuntimePreview manifest={runtimeManifest} />
          <ScreenReceipts manifest={runtimeManifest} />
        </section>
      </main>
    </div>
  );

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

      <main className="bg-[var(--surface-base)] overflow-y-auto overflow-x-hidden scrollbar-thin min-h-0">
        <PageIdentity displayName={pageTitle} level={2} area="Engineering Configuration Workspace" />
        <div className="p-[1px]">
          {studioContent}
        </div>
      </main>
    </div>
  );
}
