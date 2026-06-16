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
    return `${node.id} ${node.confidence_pct ?? '--'}% ${node.tier || ''}`;
  }
  if (node.type === 'affected_decision') {
    return `${node.label}: ${node.status}`;
  }
  return `${node.label || node.id}${node.value != null ? ` ${node.value}` : ''}`;
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
  const path = [
    ...nodes.filter((node) => node.type === 'sensor'),
    ...nodes.filter((node) => node.type === 'inferred_variable'),
    ...nodes.filter((node) => node.type === 'affected_decision'),
  ];
  const decision = nodes.find((node) => node.type === 'affected_decision');

  return (
    <section className="industrial-panel border-t-0">
      <div className="industrial-panel-header">
        <div>
          <p className="label-caps text-[var(--text-muted)]">Trust Dependency</p>
          <h2 className="industrial-panel-title text-base">Signal To Affected Decision</h2>
        </div>
      </div>
      <div className="industrial-body space-y-4">
        {decision && (
          <div className="bg-[var(--surface-panel)] border border-[var(--border-strong)] p-3">
            <p className="label-caps text-[var(--text-muted)]">Affected Decision</p>
            <p className={`caption-mono mt-1 ${trustClass(decision)}`}>{nodeText(decision)}</p>
          </div>
        )}
        <div className="space-y-[1px] bg-[var(--border-strong)] border border-[var(--border-strong)]">
          {path.map((node) => (
            <div key={node.id} className="bg-[var(--surface-panel)] p-3">
              <p className={`label-caps ${trustClass(node)}`}>{node.type}</p>
              <p className="caption-mono text-[var(--text)] mt-1">{nodeText(node)}</p>
            </div>
          ))}
        </div>
        <div className="caption-mono text-[var(--data-mono)]">
          {edges.map((edge) => `${edge.source} -> ${edge.target}`).join(' / ') || 'No dependency edges yet.'}
        </div>
        <p className="caption-mono text-[var(--text)]">{graph?.summary || 'Trust dependency data unavailable.'}</p>
      </div>
    </section>
  );
}
