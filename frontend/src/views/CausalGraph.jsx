/**
 * views/CausalGraph.jsx - Causal Propagation Graph Explorer
 *
 * Endpoints:
 *   GET /api/graph/:plant_id - node/edge topology + narrative
 *
 * Interactive features: wheel-to-zoom (0.4–3×), drag-to-pan, click node to
 * highlight its propagation chain (click again or "Reset view" to clear).
 */

import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import useStore from '../store';
import TrustDependencyGraph from '../components/TrustDependencyGraph';
import { trustColor, chartColors } from '../lib/chartTheme';
import PageIdentity from '../components/hmi/PageIdentity';

const confidenceColor = (tier) => trustColor(tier);

const NODE_HW = 52;
const NODE_HH = 38;
const SVG_W = 760;
const SVG_H = 460;

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

  // Pan/zoom transform state — also mirrored in a ref for use inside event handlers.
  const [transform, _setTransformState] = useState({ tx: 0, ty: 0, k: 1 });
  const transformRef = useRef({ tx: 0, ty: 0, k: 1 });
  function setTransform(v) {
    const val = typeof v === 'function' ? v(transformRef.current) : v;
    transformRef.current = val;
    _setTransformState(val);
  }

  const [focusedNodeId, setFocusedNodeId] = useState(null);

  const svgRef = useRef(null);
  const dragRef = useRef({ active: false, moved: false, startClientX: 0, startClientY: 0, startTx: 0, startTy: 0, startK: 1 });

  useEffect(() => {
    setLoading(true);
    fetch(`/api/graph/${plantId}`)
      .then((r) => r.json())
      .then((d) => { setGraph(d); setLoading(false); })
      .catch(() => { setGraph(null); setLoading(false); });
  }, [plantId]);

  // Imperative wheel listener — React 19 synthetic events are passive, so we
  // must attach non-passively to be able to call preventDefault.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    function handleWheel(e) {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const svgX = (e.clientX - rect.left) / rect.width * SVG_W;
      const svgY = (e.clientY - rect.top) / rect.height * SVG_H;
      setTransform((prev) => {
        const factor = e.deltaY < 0 ? 1.1 : 0.9;
        const newK = Math.max(0.4, Math.min(3, prev.k * factor));
        if (newK === prev.k) return prev;
        return {
          k: newK,
          tx: svgX - (svgX - prev.tx) * (newK / prev.k),
          ty: svgY - (svgY - prev.ty) * (newK / prev.k),
        };
      });
    }
    svg.addEventListener('wheel', handleWheel, { passive: false });
    return () => svg.removeEventListener('wheel', handleWheel);
    // Re-run once the SVG actually mounts. On first render `loading` is true and
    // the <svg> is not in the DOM (svgRef.current is null), so a []-deps effect
    // would attach the wheel listener never. Re-running when loading flips false
    // (and on plant change) guarantees the listener binds to the live SVG.
  }, [loading]); // setTransform uses the updater form, so the handler stays stable

  function handlePointerDown(e) {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = {
      active: true,
      moved: false,
      startClientX: e.clientX,
      startClientY: e.clientY,
      startTx: transformRef.current.tx,
      startTy: transformRef.current.ty,
      startK: transformRef.current.k,
    };
  }

  function handlePointerMove(e) {
    if (!dragRef.current.active) return;
    const dx = e.clientX - dragRef.current.startClientX;
    const dy = e.clientY - dragRef.current.startClientY;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) dragRef.current.moved = true;
    if (!dragRef.current.moved) return;
    const rect = svgRef.current.getBoundingClientRect();
    setTransform({
      k: dragRef.current.startK,
      tx: dragRef.current.startTx + dx * SVG_W / rect.width,
      ty: dragRef.current.startTy + dy * SVG_H / rect.height,
    });
  }

  function handlePointerUp() {
    dragRef.current.active = false;
  }

  function handleSvgClick() {
    if (!dragRef.current.moved) setFocusedNodeId(null);
  }

  function handleNodeClick(e, nodeId) {
    e.stopPropagation();
    if (dragRef.current.moved) return;
    setFocusedNodeId((prev) => (prev === nodeId ? null : nodeId));
  }

  function resetView() {
    setTransform({ tx: 0, ty: 0, k: 1 });
    setFocusedNodeId(null);
  }

  const nodes = graph?.nodes || [];
  const positions = computeHierarchicalLayout(nodes, graph?.edges || [], SVG_W, SVG_H);

  // Pre-compute neighbors of the focused node for opacity rules.
  const neighborIds = focusedNodeId ? new Set() : null;
  if (focusedNodeId && graph?.edges) {
    graph.edges.forEach((edge) => {
      if (edge.source === focusedNodeId) neighborIds.add(edge.target);
      if (edge.target === focusedNodeId) neighborIds.add(edge.source);
    });
  }

  function nodeOpacity(nodeId) {
    if (!focusedNodeId) return 1;
    if (nodeId === focusedNodeId) return 1;
    if (neighborIds.has(nodeId)) return 0.8;
    return 0.2;
  }

  function edgeOpacity(edge) {
    if (!focusedNodeId) return edge.is_active ? 1 : 0.7;
    if (edge.source === focusedNodeId || edge.target === focusedNodeId) return 1;
    return 0.1;
  }

  const isDirty = focusedNodeId || transform.k !== 1 || transform.tx !== 0 || transform.ty !== 0;

  return (
    <div className="industrial-page flex overflow-hidden">

      {/* -- Graph canvas -- */}
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
        <PageIdentity displayName="Causal Graph Explorer" level={3} area="Trust Propagation Topology" plant={plantId} />
        {graph?.nodes && (
          <div className="px-5 py-1.5 border-b border-[var(--border)] flex-shrink-0 flex items-center gap-4 bg-[var(--bg-surface)]">
            <span className="caption-mono text-[var(--text-dim)]">
              {graph.nodes.length} nodes · {graph.edges?.length || 0} edges
            </span>
            {focusedNodeId && (
              <span className="caption-mono text-[var(--primary)]">Focus: {focusedNodeId}</span>
            )}
            <span className="caption-mono text-[var(--text-muted)] hidden md:inline">
              Scroll to zoom · drag to pan · click node to highlight chain
            </span>
            {isDirty && (
              <button onClick={resetView} className="industrial-control ml-auto shrink-0">
                Reset view
              </button>
            )}
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
            <svg
              ref={svgRef}
              viewBox={`0 0 ${SVG_W} ${SVG_H}`}
              className="w-full h-full cursor-grab active:cursor-grabbing select-none"
              style={{ background: chartColors.surface }}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerLeave={handlePointerUp}
              onClick={handleSvgClick}
            >
              <g transform={`translate(${transform.tx},${transform.ty}) scale(${transform.k})`}>
                {/* Edges */}
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
                    <g key={`${edge.source}-${edge.target}`} style={{ opacity: edgeOpacity(edge) }}>
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
                        markerEnd={`url(#arrow-${edge.source}-${edge.target})`}
                      />
                    </g>
                  );
                })}

                {/* Nodes */}
                {nodes.map((node) => {
                  const pos   = positions[node.id];
                  if (!pos) return null;
                  const color = confidenceColor(node.tier);
                  const isFocused = node.id === focusedNodeId;
                  return (
                    <g
                      key={node.id}
                      style={{ opacity: nodeOpacity(node.id), cursor: 'pointer' }}
                      onClick={(e) => handleNodeClick(e, node.id)}
                    >
                      <rect
                        x={pos.x - NODE_HW} y={pos.y - NODE_HH}
                        width={NODE_HW * 2} height={NODE_HH * 2}
                        fill={chartColors.card}
                        stroke={color}
                        strokeWidth={isFocused ? 2.5 : 1.5}
                        rx="2"
                        style={{
                          filter: (node.tier === 'CRITICAL' || isFocused)
                            ? `drop-shadow(0 0 6px ${color}88)`
                            : undefined,
                        }}
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
              </g>
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
          <div className="industrial-card p-3">
            <p className="label-caps text-[var(--text-muted)]">Operational Use</p>
            <p className="caption-mono text-[var(--data-mono)] mt-1">
              Use this graph to see which sensor relationship affects the current operating decision. Runtime remains the primary place to act on decision freezes.
            </p>
            <Link to="/runtime" className="industrial-control inline-flex mt-3">Open Runtime Operating Basis</Link>
          </div>
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
