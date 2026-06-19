import { useEffect, useState } from 'react';
import useStore from '../store';

function trustClass(node) {
  if (node.status === 'blocked_until_verified') return 'status-critical';
  if (node.trusted === false) return 'status-warning';
  if (node.trusted === true) return 'status-safe';
  return 'text-[var(--data-mono)]';
}

function nodeText(node) {
  if (node.type === 'sensor') {
    return `${node.id} ${node.confidence_pct ?? '--'}% ${node.tier || node.trust_state || ''}`;
  }
  if (node.type === 'affected_decision') {
    return `${node.label}: ${node.status}`;
  }
  return `${node.label || node.id}${node.value != null ? ` ${node.value}` : ''}`;
}

function relationshipText(edge) {
  return String(edge.relationship || 'depends_on').replace(/_/g, ' ');
}

export default function TrustDependencyGraph() {
  const { plantId } = useStore();
  const [graph, setGraph] = useState(null);

  useEffect(() => {
    fetch(`/api/trust-dependency/${plantId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setGraph)
      .catch(() => setGraph(null));
  }, [plantId]);

  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  const decision = nodes.find((node) => node.type === 'affected_decision');
  const sensors = nodes.filter((node) => node.type === 'sensor');
  const inferred = nodes.find((node) => node.type === 'inferred_variable');
  const blocked = decision?.status === 'blocked_until_verified';

  return (
    <section className="industrial-panel border-t-0">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Trust Dependency</p>
          <h2 className="industrial-panel-title text-base">Signal To Operating Decision</h2>
        </div>
        {decision && (
          <span className={`industrial-badge ${blocked ? 'status-critical' : 'status-safe'}`}>
            {blocked ? 'Decision Freeze' : 'Decision Monitored'}
          </span>
        )}
      </div>
      <div className="industrial-body space-y-4">
        {decision && (
          <div className="bg-[var(--surface-panel)] border border-[var(--border-strong)] p-3">
            <p className="label-caps text-[var(--text-muted)]">Affected Decision</p>
            <p className={`caption-mono mt-1 ${trustClass(decision)}`}>{nodeText(decision)}</p>
            {decision.depends_on?.length > 0 && (
              <p className="caption-mono text-[var(--text-muted)] mt-2">
                Depends on: {decision.depends_on.join(' / ')}
              </p>
            )}
          </div>
        )}
        <div className="grid grid-cols-1 gap-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
          <div className="bg-[var(--surface-panel)] p-3">
            <p className="label-caps text-[var(--text-muted)]">Evidence Signals</p>
            <div className="mt-2 space-y-2">
              {sensors.map((node) => (
                <div key={node.id} className="flex items-center justify-between gap-3">
                  <span className="caption-mono text-[var(--text)]">{nodeText(node)}</span>
                  <span className={`label-caps ${trustClass(node)}`}>{node.trusted === false ? 'not basis' : node.trusted === true ? 'basis candidate' : node.role || node.type}</span>
                </div>
              ))}
              {!sensors.length && <p className="caption-mono text-[var(--text-muted)]">No evidence signals attached.</p>}
            </div>
          </div>
          {inferred && (
            <div className="bg-[var(--surface-panel)] p-3">
              <p className="label-caps text-[var(--text-muted)]">Inferred Variable</p>
              <p className={`caption-mono mt-1 ${trustClass(inferred)}`}>{nodeText(inferred)}</p>
              {inferred.evidence && <p className="caption-mono text-[var(--text-muted)] mt-2">{inferred.evidence}</p>}
            </div>
          )}
        </div>
        <div>
          <p className="label-caps text-[var(--text-muted)] mb-2">Dependency Path</p>
          <div className="space-y-2">
            {edges.map((edge) => (
              <div key={`${edge.source}-${edge.target}-${edge.relationship}`} className="caption-mono text-[var(--data-mono)] flex items-center gap-2">
                <span className="text-[var(--text)]">{edge.source}</span>
                <span>{relationshipText(edge)}</span>
                <span className="text-[var(--text)]">{edge.target}</span>
              </div>
            ))}
            {!edges.length && <p className="caption-mono text-[var(--data-mono)]">No dependency edges yet.</p>}
          </div>
        </div>
        <p className="caption-mono text-[var(--text)]">{graph?.summary || 'Trust dependency data unavailable.'}</p>
        {graph?.asset_model_id && (
          <p className="caption-mono text-[var(--text-muted)]">
            Source: {graph.asset_model_id} / {graph.equipment_id || 'equipment model'} / read-only deterministic graph
          </p>
        )}
      </div>
    </section>
  );
}
