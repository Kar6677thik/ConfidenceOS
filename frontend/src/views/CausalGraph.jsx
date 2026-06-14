/**
 * views/CausalGraph.jsx — Causal Propagation Graph Explorer
 *
 * Endpoints:
 *   GET /api/graph/:plant_id — node/edge topology + narrative
 *
 * Stitch mockup: (no dedicated HTML file — uses App.jsx logic)
 */

import { useEffect, useState } from 'react';
import useStore from '../store';

function confidenceColor(tier) {
  if (!tier) return '#8fd6ff';
  const t = tier.toUpperCase();
  if (t === 'CRITICAL') return '#ffb4ab';
  if (t === 'LOW')      return '#ffda66';
  if (t === 'MEDIUM')   return '#c3c6cd';
  return '#8fd6ff';
}

export default function CausalGraph() {
  const { plantId } = useStore();
  const [graph, setGraph] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/graph/${plantId}`)
      .then((r) => r.json())
      .then((d) => { setGraph(d); setLoading(false); })
      .catch(() => { setGraph(null); setLoading(false); });
  }, [plantId]);

  const nodes = graph?.nodes || [];
  const positions = {};
  nodes.forEach((node, i) => {
    positions[node.id] = {
      x: 140 + (i % 3) * 220,
      y: 90 + Math.floor(i / 3) * 180,
    };
  });

  return (
    <div className="industrial-page flex overflow-hidden">

      {/* ── Graph canvas ── */}
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="stitch-card-header px-5 py-3 border-b border-[var(--border)] bg-[var(--bg-surface)]">
          <h1 className="text-[18px] font-semibold text-[var(--text)]">Causal Graph Explorer</h1>
          <div className="flex items-center gap-3">
            <span className="label-caps text-[var(--text-muted)]">{plantId?.toUpperCase()}</span>
            {graph?.nodes && (
              <span className="industrial-badge text-[var(--primary)] border-[var(--primary)]/40">
                {graph.nodes.length} nodes · {graph.edges?.length || 0} edges
              </span>
            )}
          </div>
        </div>

        {/* SVG viewport */}
        <div className="flex-1 overflow-hidden bg-[var(--bg-low)]">
          {loading ? (
            <div className="h-full flex items-center justify-center">
              <p className="label-caps text-[var(--text-muted)]">Loading graph…</p>
            </div>
          ) : !graph?.nodes?.length ? (
            <div className="h-full flex items-center justify-center">
              <p className="label-caps text-[var(--text-muted)]">No graph data available for {plantId}.</p>
            </div>
          ) : (
            <svg viewBox="0 0 760 460" className="w-full h-full"
              style={{ background: '#0b0e11' }}>
              {/* Edges */}
              {(graph.edges || []).map((edge) => {
                const a = positions[edge.source];
                const b = positions[edge.target];
                if (!a || !b) return null;
                return (
                  <g key={`${edge.source}-${edge.target}`}>
                    <defs>
                      <marker id={`arrow-${edge.source}-${edge.target}`}
                        markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                        <path d="M0,0 L0,6 L6,3 z"
                          fill={edge.is_propagating ? '#ffda66' : '#3d4850'} />
                      </marker>
                    </defs>
                    <line
                      x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                      stroke={edge.is_propagating ? '#ffda66' : '#3d4850'}
                      strokeWidth={edge.is_active ? 3 : 1.5}
                      strokeDasharray={edge.is_propagating ? undefined : '4 3'}
                      markerEnd={`url(#arrow-${edge.source}-${edge.target})`}
                    />
                  </g>
                );
              })}

              {/* Nodes */}
              {nodes.map((node) => {
                const pos   = positions[node.id];
                const color = confidenceColor(node.tier);
                return (
                  <g key={node.id}>
                    <rect
                      x={pos.x - 52} y={pos.y - 34} width="104" height="68"
                      fill="var(--bg-card)" stroke={color} strokeWidth="1.5" rx="2"
                      style={{ filter: node.tier === 'CRITICAL' ? `drop-shadow(0 0 6px ${color}66)` : undefined }}
                    />
                    <text x={pos.x} y={pos.y - 8} textAnchor="middle"
                      fill="#e1e2e7" fontSize="13" fontWeight="700" fontFamily="Inter, sans-serif">
                      {node.id}
                    </text>
                    <text x={pos.x} y={pos.y + 12} textAnchor="middle"
                      fill={color} fontSize="12" fontFamily="Geist, monospace">
                      {node.confidence_pct != null ? `${node.confidence_pct}%` : '—'}
                    </text>
                    <text x={pos.x} y={pos.y + 26} textAnchor="middle"
                      fill={color} fontSize="9" fontFamily="Geist, monospace"
                      style={{ letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                      {node.tier || '—'}
                    </text>
                  </g>
                );
              })}
            </svg>
          )}
        </div>

        {/* Legend */}
        <div className="flex gap-5 px-5 py-3 border-t border-[var(--border)] bg-[var(--bg-surface)]">
          {[
            { color: '#ffb4ab', label: 'Critical' },
            { color: '#ffda66', label: 'Low' },
            { color: '#c3c6cd', label: 'Medium' },
            { color: '#8fd6ff', label: 'High / Normal' },
          ].map(({ color, label }) => (
            <div key={label} className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-sm" style={{ background: color }} />
              <span className="label-caps text-[var(--text-muted)]">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Right sidebar — narrative + causal chains ── */}
      <aside className="w-96 bg-[var(--bg-surface)] border-l border-[var(--border)] flex flex-col overflow-hidden">
        <div className="stitch-card-header px-5 py-3 border-b border-[var(--border)]">
          <span className="text-[14px] font-semibold text-[var(--text)]">Root Cause Narrative</span>
        </div>
        <div className="flex-1 overflow-y-auto scrollbar-thin p-5 space-y-5">
          <p className="leading-relaxed text-[14px] text-[var(--text)]">
            {graph?.narrative || 'No narrative available. Graph data may still be loading.'}
          </p>
          {(graph?.causal_chains || []).length > 0 && (
            <div>
              <p className="label-caps text-[var(--text-muted)] mb-3">Propagation Chains</p>
              <div className="space-y-1">
                {graph.causal_chains.map((chain, i) => (
                  <div key={i} className="stitch-card px-3 py-2 caption-mono text-[var(--text-muted)]">
                    {chain.join(' → ')}
                  </div>
                ))}
              </div>
            </div>
          )}
          {graph?.edges?.filter((e) => e.is_propagating).length > 0 && (
            <div>
              <p className="label-caps text-[var(--text-muted)] mb-3">Active Propagations</p>
              {graph.edges.filter((e) => e.is_propagating).map((e) => (
                <div key={`${e.source}-${e.target}`}
                  className="flex items-center gap-2 py-2 border-b border-[var(--border-subtle)]">
                  <span className="font-data text-[var(--warning)] text-[13px]">{e.source}</span>
                  <span className="caption-mono text-[var(--text-muted)]">→</span>
                  <span className="font-data text-[var(--critical)] text-[13px]">{e.target}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
