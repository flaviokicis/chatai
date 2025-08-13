import type { CompiledFlow, FlowLayoutColumn, PositionedNode } from "./types";

/**
 * Compute a simple left-to-right columnar layout using inbound edge count as a heuristic.
 * This is deterministic, non-DOM-measuring, and fast. Replace later with a proper graph layout.
 */
export function computeColumns(flow: CompiledFlow): FlowLayoutColumn[] {
  const nodes = Object.values(flow.nodes);
  const incoming: Record<string, number> = {};
  for (const n of nodes) incoming[n.id] = 0;
  for (const arr of Object.values(flow.edges_from)) {
    for (const e of arr) incoming[e.target] = (incoming[e.target] ?? 0) + 1;
  }

  const positioned: PositionedNode[] = nodes
    .map((n) => ({
      ...n,
      isEntry: flow.entry === n.id,
      outgoing: flow.edges_from[n.id] ?? [],
    }))
    .sort((a, b) => (incoming[a.id] ?? 0) - (incoming[b.id] ?? 0));

  // Partition into columns of at most N nodes for readability
  const maxPerColumn = Math.max(4, Math.ceil(positioned.length / 3));
  const columns: FlowLayoutColumn[] = [];
  let i = 0;
  let colIdx = 0;
  while (i < positioned.length) {
    const slice = positioned.slice(i, i + maxPerColumn);
    columns.push({ columnIndex: colIdx, nodes: slice });
    i += maxPerColumn;
    colIdx += 1;
  }
  return columns;
}


