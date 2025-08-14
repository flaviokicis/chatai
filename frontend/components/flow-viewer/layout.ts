import type { CompiledFlow, FlowLayoutColumn, PositionedNode } from "./types";

/**
 * Compute a clean left-to-right DAG layout.
 *
 * Strategy:
 * 1) Layering: breadth‑first distance from entry defines the column index
 * 2) Ordering within each column: barycenter heuristic using parent positions
 * 3) Deterministic fallbacks to keep the graph stable across renders
 */
export function computeColumns(flow: CompiledFlow): FlowLayoutColumn[] {
  const nodeIds = Object.keys(flow.nodes);

  // Build adjacency and reverse adjacency
  const outgoing: Record<string, string[]> = {};
  const incoming: Record<string, string[]> = {};
  for (const id of nodeIds) {
    outgoing[id] = (flow.edges_from[id] ?? []).map((e) => e.target);
    incoming[id] = [];
  }
  for (const [src, edges] of Object.entries(flow.edges_from)) {
    for (const e of edges) {
      if (!incoming[e.target]) incoming[e.target] = [];
      incoming[e.target].push(src);
    }
  }

  // 1) Layering via BFS from entry
  const layer: Record<string, number> = {};
  for (const id of nodeIds) layer[id] = Number.POSITIVE_INFINITY;
  const q: string[] = [flow.entry];
  layer[flow.entry] = 0;
  const enqueued = new Set<string>([flow.entry]);
  while (q.length) {
    const u = q.shift()!;
    const base = layer[u];
    for (const v of outgoing[u] ?? []) {
      // Use shortest distance layering
      if (layer[v] > base + 1) layer[v] = base + 1;
      if (!enqueued.has(v)) {
        q.push(v);
        enqueued.add(v);
      }
    }
  }

  // Unreached nodes: place them after the deepest layer (keeps layout robust if data contains islands)
  const maxAssigned = Math.max(0, ...Object.values(layer).filter((n) => Number.isFinite(n)));
  for (const id of nodeIds) {
    if (!Number.isFinite(layer[id])) layer[id] = maxAssigned + 1;
  }

  // 2) Initial grouping by column
  const groups = new Map<number, string[]>();
  for (const id of nodeIds) {
    const col = layer[id];
    if (!groups.has(col)) groups.set(col, []);
    groups.get(col)!.push(id);
  }

  // 3) Ordering within columns using barycenter of parents, with deterministic fallbacks
  const orderedColumns: string[][] = [];
  const numCols = Math.max(...Array.from(groups.keys())) + 1;
  const positionInColumn: Record<string, number> = {};

  for (let c = 0; c < numCols; c++) {
    const ids = (groups.get(c) ?? []).slice();
    if (c === 0) {
      // Entry first, then others by (incoming count, id)
      ids.sort((a, b) => {
        if (a === flow.entry) return -1;
        if (b === flow.entry) return 1;
        const ia = incoming[a]?.length ?? 0;
        const ib = incoming[b]?.length ?? 0;
        if (ia !== ib) return ia - ib;
        return a.localeCompare(b);
      });
    } else {
      ids.sort((a, b) => {
        const pa = (incoming[a] ?? []).map((p) => positionInColumn[p]).filter((n) => Number.isFinite(n));
        const pb = (incoming[b] ?? []).map((p) => positionInColumn[p]).filter((n) => Number.isFinite(n));
        const baryA = pa.length ? pa.reduce((x, y) => x + y, 0) / pa.length : Number.POSITIVE_INFINITY;
        const baryB = pb.length ? pb.reduce((x, y) => x + y, 0) / pb.length : Number.POSITIVE_INFINITY;
        if (baryA !== baryB) return baryA - baryB;
        // Fallback: fewer incoming first, then id for stability
        const ia = incoming[a]?.length ?? 0;
        const ib = incoming[b]?.length ?? 0;
        if (ia !== ib) return ia - ib;
        return a.localeCompare(b);
      });
    }
    ids.forEach((id, idx) => (positionInColumn[id] = idx));
    orderedColumns.push(ids);
  }

  // 4) Build final structure with node metadata
  const columns: FlowLayoutColumn[] = orderedColumns.map((ids, columnIndex) => ({
    columnIndex,
    nodes: ids.map((id) => ({
      ...flow.nodes[id],
      isEntry: id === flow.entry,
      outgoing: flow.edges_from[id] ?? [],
    })) as PositionedNode[],
  }));

  return columns;
}


