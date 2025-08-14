import type { CompiledFlow, FlowEdgeSummary } from "./types";

export function pickLabel(edge: FlowEdgeSummary, nodes: CompiledFlow["nodes"]): string {
  if (edge.label) return edge.label;
  if (edge.condition_description) return edge.condition_description;
  const targetNode = nodes[edge.target];
  return targetNode?.label ?? edge.target;
}

export function sortedOutgoing(flow: CompiledFlow, id: string): FlowEdgeSummary[] {
  return (flow.edges_from[id] ?? [])
    .slice()
    .sort((a, b) => (a.priority ?? 0) - (b.priority ?? 0));
}


