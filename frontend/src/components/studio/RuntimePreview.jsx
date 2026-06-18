import Panel from './Panel';

export default function RuntimePreview({ manifest }) {
  const screens = manifest?.screens || [];
  const faceplates = manifest?.faceplates || [];
  return (
    <Panel
      eyebrow="Generated Runtime Preview"
      title={manifest?.manifest_id || 'No Generated Manifest'}
      right={<span className="industrial-badge text-[var(--data-mono)]">{faceplates.length} faceplates</span>}
      className="mb-[1px]"
    >
      {manifest ? (
        <div className="space-y-4">
          <div>
            <p className="label-caps text-[var(--text-muted)]">Screens</p>
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-[1px] bg-[var(--border-strong)] mt-2">
              {screens.map((screen) => (
                <div key={screen.generated_id || screen.screen_id} className="bg-[var(--surface-panel)] p-3">
                  <p className="caption-mono text-[var(--text)]">{screen.title}</p>
                  <p className="caption-mono text-[var(--data-mono)] mt-1 machine-token">{screen.sections?.join(' / ')}</p>
                </div>
              ))}
            </div>
          </div>
          <div>
            <p className="label-caps text-[var(--text-muted)]">Faceplates</p>
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-[1px] bg-[var(--border-strong)] mt-2">
              {faceplates.map((faceplate) => (
                <div key={faceplate.generated_id || faceplate.equipment_id} className="bg-[var(--surface-panel)] p-3">
                  <p className="label-caps status-safe">{faceplate.template_label}</p>
                  <p className="caption-mono text-[var(--text)] mt-1">{faceplate.title}</p>
                  <p className="caption-mono text-[var(--data-mono)] mt-1 machine-token">{faceplate.signals?.map((signal) => signal.tag).join(' / ')}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <p className="caption-mono text-[var(--data-mono)]">Run a passing build to generate Runtime screens and faceplates.</p>
      )}
    </Panel>
  );
}
