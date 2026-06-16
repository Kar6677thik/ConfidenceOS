/**
 * views/CausalGraph.jsx - Causal Propagation Graph Explorer
 *
 * Endpoints:
 *   GET /api/graph/:plant_id - node/edge topology + narrative
 *
 * Stitch mockup: (no dedicated HTML file - uses App.jsx logic)
 */

import { useEffect, useState } from 'react';
import useStore from '../store';
import TrustDependencyGraph from '../components/TrustDependencyGraph';
import { trustColor, chartColors } from '../lib/chartTheme';
import PageIdentity from '../components/hmi/PageIdentity';

// Sourced from the NAMUR design tokens (chartTheme), shared with every other view.
const confidenceColor = (tier) => trustColor(tier);

// Node half-dimensions - used for both the rect and for edge-to-edge connection points.
const NODE_HW = 52; // half-width
const NODE_HH = 38; // half-height (76px tall nodes fit 3 text lines at 11-13px)

// Deterministic topological layout: nodes with no incoming edges appear left;
// leaf nodes appear right. Within each column nodes are sorted by id for stability.
function computeHierarchicalLayout(nodes, edges, svgW, svgH) {
  if (!nodes.length) return {};
  const nodeSet = new Set(nodes.map((n) => n.id));
  const inDeg = Object.fromEntries(nodes.map((n) => [n.id, 0]));
  const adj   = Object.fromEntries(nodes.map((n) => [n.id, []]));
  (edges || []).forEach(({ source, target }) => {
    if (nodeSet.has(source) && nodeSet.has(target)) {
      adj[source].push(target);
      inDeg[target] = (inDeg[target] || 0) + 1;
    }
  });
  // BFS from roots - assigns longest-path depth so causal chains read left->right.
  const level = {};
  const queue = nodes.filter((n) => !inDeg[n.id]).map((n) => n.id);
  queue.forEach((id) => { level[id] = 0; });
  let head = 0;
  while (head < queue.length) {
    const cur = queue[head++];
    (adj[cur] || []).forEach((tgt) => {
      const next = (level[cur] ?? 0) + 1;
      if (level[tgt] == null || level[tgt] < next) { level[tgt] = next; queue.push(tgt); }
    });
  }
  nodes.forEach((n) => { if (level[n.id] == null) level[n.id] = 0; });
  const byLevel = {};
  nodes.forEach((n) => { (byLevel[level[n.id]] ??= []).push(n.id); });
  Object.values(byLevel).forEach((ids) => ids.sort());
  const levels = Object.keys(byLevel).map(Number).sort((a, b) => a - b);
  const maxL = levels[levels.length - 1] ?? 0;
  const PAD_X = 80, PAD_Y = 56;
  const usableW = svgW - PAD_X * 2;
  const usableH = svgH - PAD_Y * 2;
  const positions = {};
  levels.forEach((l) => {
    const cx = maxL === 0 ? PAD_X + usableW / 2 : PAD_X + (l / maxL) * usableW;
    const rows = byLevel[l];
    rows.forEach((id, i) => {
      const cy = rows.length === 1
        ? PAD_Y + usableH / 2
        : PAD_Y + (i / (rows.length - 1)) * usableH;
      positions[id] = { x: Math.round(cx), y: Math.round(cy) };
    });
  });
  return positions;
}

export default function CausalGraph() {
  const { plantId } = useStore();
  const [graph, setGraph] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    fetch(`/api/graph/${plantId}`)
      .then((r) => r.json())
      .then((d) => { setGraph(d); setLoading(false); })
      .catch(() => { setGraph(null); setLoading(false); });
  }, [plantId]);

  const nodes = graph?.nodes || [];
  const positions = computeHierarchicalLayout(nodes, graph?.edges || [], 760, 460);

  return (
    <div className="industrial-page flex overflow-hidden">

      {/* -- Graph canvas -- */}
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
        <PageIdentity displayName="Causal Graph Explorer" level={3} area="Trust Propagation Topology" plant={plantId} />
        {graph?.nodes && (
          <div className="px-5 py-1.5 border-b border-[var(--border)] flex-shrink-0 flex items-center gap-2 bg-[var(--bg-surface)]">
            <span className="caption-mono text-[var(--text-dim)]">{graph.nodes.length} nodes · {graph.edges?.length || 0} edges</span>
          </div>
        )}

        {/* SVG viewport */}
        <div className="flex-1 overflow-hidden bg-[var(--bg-low)]">
          {loading ? (
            <div className="h-full flex items-center justify-center">
              <p className="label-caps text-[var(--text-muted)]">Loading graph...</p>
            </div>
          ) : !graph?.nodes?.length ? (
            <div className="h-full flex items-center justify-center">
              <p className="label-caps text-[var(--text-muted)]">No graph data available for {plantId}.</p>
            </div>
          ) : (
            <svg viewBox="0 0 760 460" className="w-full h-full"
              style={{ background: chartColors.surface }}>
              {/* Edges - cubic bezier from right-edge of source to left-edge of target */}
              {(graph.edges || []).map((edge) => {
                const a = positions[edge.source];
                const b = positions[edge.target];
                if (!a || !b) return null;
                const stroke = edge.is_propagating ? confidenceColor('LOW') : chartColors.axisLine;
                const x1 = a.x + NODE_HW;
                const x2 = b.x - NODE_HW;
                const midX = (x1 + x2) / 2;
                const d = `M${x1} ${a.y} C${midX} ${a.y} ${midX} ${b.y} ${x2} ${b.y}`;
                return (
                  <g key={`${edge.source}-${edge.target}`}>
                    <defs>
                      <marker id={`arrow-${edge.source}-${edge.target}`}
                        markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                        <path d="M0,0 L0,6 L6,3 z" fill={stroke} />
                      </marker>
                    </defs>
                    <path
                      d={d}
                      fill="none"
                      stroke={stroke}
                      strokeWidth={edge.is_active ? 2.5 : 1.5}
                      strokeDasharray={edge.is_propagating ? undefined : '4 3'}
                      opacity={edge.is_active ? 1 : 0.7}
                      markerEnd={`url(#arrow-${edge.source}-${edge.target})`}
                    />
                  </g>
                );
              })}

              {/* Nodes - taller rect (NODE_HH*2 = 76px) to fit 11px tier label */}
              {nodes.map((node) => {
                const pos   = positions[node.id];
                if (!pos) return null;
                const color = confidenceColor(node.tier);
                return (
                  <g key={node.id}>
                    <rect
                      x={pos.x - NODE_HW} y={pos.y - NODE_HH}
                      width={NODE_HW * 2} height={NODE_HH * 2}
                      fill={chartColors.card} stroke={color} strokeWidth="1.5" rx="2"
                      style={{ filter: node.tier === 'CRITICAL' ? `drop-shadow(0 0 6px ${color}66)` : undefined }}
                    />
                    <text x={pos.x} y={pos.y - 10} textAnchor="middle"
                      fill={chartColors.text} fontSize="13" fontWeight="700" fontFamily="Inter, sans-serif">
                      {node.id}
                    </text>
                    <text x={pos.x} y={pos.y + 8} textAnchor="middle"
                      fill={color} fontSize="12" fontFamily="Geist, monospace">
                      {node.confidence_pct != null ? `${node.confidence_pct}%` : '-'}
                    </text>
                    <text x={pos.x} y={pos.y + 25} textAnchor="middle"
                      fill={color} fontSize="11" fontFamily="Geist, monospace"
                      style={{ letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                      {node.tier || '-'}
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
            { color: confidenceColor('CRITICAL'), label: 'Critical' },
            { color: confidenceColor('LOW'), label: 'Low' },
            { color: confidenceColor('MEDIUM'), label: 'Medium' },
            { color: confidenceColor('HIGH'), label: 'High / Normal' },
          ].map(({ color, label }) => (
            <div key={label} className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-sm" style={{ background: color }} />
              <span className="label-caps text-[var(--text-muted)]">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* -- Right sidebar - narrative + causal chains -- */}
      <aside className="w-96 bg-[var(--bg-surface)] border-l border-[var(--border)] flex flex-col overflow-hidden">
        <div className="industrial-card-header px-5 py-3 border-b border-[var(--border)]">
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
                  <div key={i} className="industrial-card px-3 py-2 caption-mono text-[var(--text-muted)]">
                    {chain.join(' -> ')}
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
                  <span className="caption-mono text-[var(--text-muted)]">{'->'}</span>
                  <span className="font-data text-[var(--critical)] text-[13px]">{e.target}</span>
                </div>
              ))}
            </div>
          )}
          <div className="mt-4 pt-4 border-t border-[var(--border)]">
            <TrustDependencyGraph />
          </div>
        </div>
      </aside>
    </div>
  );
}
