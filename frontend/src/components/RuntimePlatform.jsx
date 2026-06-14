import { useEffect, useMemo, useState } from 'react';
import useStore from '../store';
import IncidentTimeline from './IncidentTimeline';

function statusClass(value) {
  const status = String(value || '').toUpperCase();
  if (status === 'CRITICAL') return 'status-critical';
  if (status === 'WARNING' || status === 'LOW') return 'status-warning';
  if (status === 'MEDIUM') return 'status-caution';
  return 'status-safe';
}

function formatText(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function asList(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  if (value == null || value === '') return [];
  return [value];
}

function NavigationTree({ navigation, selected, onSelect }) {
  const areas = navigation?.areas || [];
  return (
    <aside className="bg-[var(--surface-panel)] border-r border-[var(--border-strong)] overflow-y-auto scrollbar-thin">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Semantic Navigation</p>
          <h2 className="industrial-panel-title text-base">{navigation?.name || 'Plant'}</h2>
        </div>
      </div>
      <div className="industrial-body space-y-3">
        {areas.map((area) => (
          <div key={area.id} className="border border-[var(--border-strong)] bg-[var(--surface-base)]">
            <button onClick={() => onSelect(area.id)} className={`w-full text-left p-3 ${selected === area.id ? 'status-safe' : 'text-[var(--text)]'}`}>
              <p className="label-caps">Area</p>
              <p className="caption-mono mt-1">{area.name}</p>
            </button>
            {(area.units || []).map((unit) => (
              <div key={unit.id} className="border-t border-[var(--border-strong)]">
                <button onClick={() => onSelect(unit.id)} className={`w-full text-left p-3 pl-5 ${selected === unit.id ? 'status-safe' : 'text-[var(--data-mono)]'}`}>
                  <p className="label-caps">Unit</p>
                  <p className="caption-mono mt-1">{unit.name}</p>
                </button>
                {(unit.modules || []).map((module) => (
                  <div key={module.id} className="border-t border-[var(--border-strong)] p-3 pl-7">
                    <p className="label-caps text-[var(--text-muted)]">Module</p>
                    <p className="caption-mono text-[var(--text)] mt-1">{module.name}</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {(module.equipment || []).map((equipmentId) => (
                        <button
                          key={equipmentId}
                          onClick={() => onSelect(equipmentId)}
                          className={`industrial-badge ${selected === equipmentId ? 'status-safe' : 'text-[var(--data-mono)]'}`}
                        >
                          {equipmentId}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>
    </aside>
  );
}

function OperatingBasis({ basis, compact = false }) {
  const rows = [
    ['Abnormal Situation', basis?.abnormal_situation, 'status-warning'],
    ['Do Not Trust', basis?.do_not_trust, 'status-critical'],
    ['Trusted Substitute', basis?.trusted_substitutes, 'status-safe'],
    ['First Safe Action', basis?.first_safe_action, 'status-safe'],
    ['Decision Freeze', basis?.decision_freeze, 'status-warning'],
    ['Exit Condition', basis?.exit_condition, 'text-[var(--data-mono)]'],
  ];
  return (
    <div className={`space-y-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)] ${compact ? '' : 'mt-4'}`}>
      {rows.map(([label, value, cls]) => {
        const values = asList(value);
        return (
          <div key={label} className="grid grid-cols-1 md:grid-cols-[190px_1fr] gap-[1px] bg-[var(--border-strong)]">
            <div className="bg-[var(--surface-lowest)] p-3">
              <p className={`label-caps ${cls}`}>{label}</p>
            </div>
            <div className="bg-[var(--surface-panel)] p-3">
              {values.length ? values.slice(0, 5).map((item) => (
                <p key={item} className="caption-mono text-[var(--text)]">{formatText(item)}</p>
              )) : <p className="caption-mono text-[var(--data-mono)]">Not active</p>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Faceplate({ faceplate, selected, onSelect }) {
  return (
    <button
      onClick={() => onSelect(faceplate.equipment_id)}
      className={`text-left bg-[var(--surface-panel)] border ${selected ? 'border-[var(--safe)]' : 'border-[var(--border-strong)]'} p-4 min-h-[270px] hover:bg-[var(--surface-elevated)]`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="label-caps text-[var(--text-muted)]">{faceplate.template_label}</p>
          <h3 className="text-xl font-bold text-[var(--text)] mt-1">{faceplate.title}</h3>
        </div>
        <span className="industrial-badge text-[var(--data-mono)]">{faceplate.equipment_id}</span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
        {(faceplate.signals || []).slice(0, 6).map((signal) => {
          const confidence = signal.confidence || {};
          const reading = signal.reading || {};
          return (
            <div key={signal.tag} className="bg-[var(--surface-base)] p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="font-data text-[var(--text)]">{signal.tag}</p>
                <span className={statusClass(confidence.tier)}>{Math.round(confidence.confidence_pct ?? 0)}%</span>
              </div>
              <p className="caption-mono text-[var(--data-mono)] mt-1">
                {reading.value ?? '--'} {reading.unit || signal.unit}
              </p>
              <p className="caption-mono text-[var(--text-muted)] mt-1">{signal.role || signal.sensor_type}</p>
            </div>
          );
        })}
      </div>
      <p className="caption-mono text-[var(--data-mono)] mt-4">
        Generated from {faceplate.provenance?.template_id} / approved {String(faceplate.provenance?.approved)}
      </p>
    </button>
  );
}

function RolePanel({ manifest }) {
  const rows = manifest?.role_sections || [];
  return (
    <section className="industrial-panel border-t-0">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">{manifest?.role}</p>
          <h2 className="industrial-panel-title text-base">Role-Specific Operating View</h2>
        </div>
      </div>
      <div className="industrial-body space-y-[1px] bg-[var(--border-strong)]">
        {rows.map((row) => (
          <div key={row.section} className="bg-[var(--surface-panel)] p-3">
            <p className="label-caps text-[var(--text)]">{formatText(row.section)}</p>
            <p className="caption-mono text-[var(--data-mono)] mt-1">{(row.items || []).length} item(s) generated from role policy.</p>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function RuntimePlatform() {
  const {
    connect,
    connected,
    plantId,
    role,
    plantContext,
    incidentTimeline,
  } = useStore();
  const [manifest, setManifest] = useState(null);
  const [selected, setSelected] = useState('V-5100');

  useEffect(() => {
    connect();
  }, [connect]);

  useEffect(() => {
    let active = true;
    const load = () => {
      fetch(`/api/screens/generated?role=${role}&context=auto&plant_id=${plantId}`)
        .then((res) => (res.ok ? res.json() : null))
        .then((payload) => {
          if (active) setManifest(payload);
        })
        .catch(() => {
          if (active) setManifest(null);
        });
    };
    load();
    const timer = setInterval(load, 2500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [plantId, role]);

  const selectedFaceplate = useMemo(
    () => (manifest?.faceplates || []).find((item) => item.equipment_id === selected),
    [manifest, selected],
  );

  const stress = manifest?.stress_mode;

  if (!manifest) {
    return (
      <div className="industrial-page p-8">
        <p className="caption-mono text-[var(--data-mono)]">Generating Runtime from asset model and templates...</p>
      </div>
    );
  }

  if (stress) {
    return (
      <div className="industrial-page grid grid-cols-[320px_1fr] gap-[1px] bg-[var(--border-strong)] overflow-hidden">
        <NavigationTree navigation={manifest.navigation} selected={selected} onSelect={setSelected} />
        <main className="bg-[var(--surface-base)] p-[1px] overflow-y-auto scrollbar-thin">
          <section className="industrial-panel min-h-full">
            <div className="industrial-panel-header">
              <div>
                <p className="label-caps status-warning">Stress Mode / Generated Runtime</p>
                <h1 className="industrial-panel-title">{manifest.operating_basis?.abnormal_situation}</h1>
              </div>
              <span className={`industrial-badge ${connected ? 'status-safe' : 'status-critical'}`}>{connected ? 'LIVE' : 'OFFLINE'}</span>
            </div>
            <div className="industrial-body">
              <OperatingBasis basis={manifest.operating_basis} compact />
              <div className="mt-4">
                <IncidentTimeline events={incidentTimeline} compact />
              </div>
            </div>
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className="industrial-page grid grid-cols-[320px_1fr_360px] gap-[1px] bg-[var(--border-strong)] overflow-hidden">
      <NavigationTree navigation={manifest.navigation} selected={selected} onSelect={setSelected} />
      <main className="bg-[var(--surface-base)] p-[1px] overflow-y-auto scrollbar-thin">
        <section className="industrial-panel mb-[1px]">
          <div className="industrial-panel-header">
            <div>
              <p className="label-caps text-[var(--text-muted)]">Generated Runtime / {role}</p>
              <h1 className="industrial-panel-title">Trust-Aware HMI From Metadata</h1>
            </div>
            <div className="flex items-center gap-2">
              <span className={`industrial-badge ${statusClass(plantContext?.severity)}`}>{manifest.context}</span>
              <span className={`industrial-badge ${connected ? 'status-safe' : 'status-critical'}`}>{connected ? 'LIVE' : 'OFFLINE'}</span>
            </div>
          </div>
        </section>
        <section className="industrial-panel mb-[1px]">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">Situation Workspace</h2>
            <span className="industrial-badge text-[var(--data-mono)]">{manifest.situations?.length || 0}</span>
          </div>
          <div className="industrial-body">
            <OperatingBasis basis={manifest.operating_basis} />
          </div>
        </section>
        <section className="industrial-panel">
          <div className="industrial-panel-header">
            <div>
              <p className="label-caps text-[var(--text-muted)]">Generated Equipment Faceplates</p>
              <h2 className="industrial-panel-title text-base">Template-Bound Equipment</h2>
            </div>
          </div>
          <div className="industrial-body grid grid-cols-1 xl:grid-cols-2 gap-[1px] bg-[var(--border-strong)]">
            {(manifest.faceplates || []).map((faceplate) => (
              <Faceplate key={faceplate.equipment_id} faceplate={faceplate} selected={selected === faceplate.equipment_id} onSelect={setSelected} />
            ))}
          </div>
        </section>
      </main>
      <aside className="bg-[var(--surface-panel)] overflow-y-auto scrollbar-thin">
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <div>
              <p className="label-caps text-[var(--text-muted)]">Template Provenance</p>
              <h2 className="industrial-panel-title text-base">{selectedFaceplate?.title || selected}</h2>
            </div>
          </div>
          <div className="industrial-body">
            <pre className="industrial-panel-subtle p-3 caption-mono text-[var(--data-mono)] whitespace-pre-wrap">
              {JSON.stringify(selectedFaceplate?.provenance || manifest.provenance, null, 2)}
            </pre>
          </div>
        </section>
        <RolePanel manifest={manifest} />
        <section className="industrial-panel border-t-0">
          <div className="industrial-panel-header">
            <h2 className="industrial-panel-title text-base">Generated Validation</h2>
          </div>
          <div className="industrial-body">
            <p className={`caption-mono ${manifest.validation?.status === 'valid' ? 'status-safe' : 'status-warning'}`}>
              {manifest.validation?.status} / {manifest.validation?.count || 0} warning(s)
            </p>
          </div>
        </section>
      </aside>
    </div>
  );
}
