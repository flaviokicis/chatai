"use client";

import { useEffect, useMemo, useState } from "react";
import { FlowViewer } from "./FlowViewer";
import type { CompiledFlow, EdgeKey, FlowEdgeSummary } from "./types";
import { JourneyPreview, type JourneyStep } from "./JourneyPreview";
import { NodeLegend } from "./NodeLegend";
import { VerticalBranches } from "./VerticalBranches";

type BranchOption = { targetId: string; label: string };

function pickLabel(edge: FlowEdgeSummary, nodes: CompiledFlow["nodes"]): string {
  if (edge.label) return edge.label;
  if (edge.condition_description) return edge.condition_description;
  const tgt = nodes[edge.target];
  return tgt?.label ?? edge.target;
}

function findFirstBranchDecision(flow: CompiledFlow): string | null {
  const queue: string[] = [flow.entry];
  const visited = new Set<string>();
  while (queue.length) {
    const id = queue.shift()!;
    if (visited.has(id)) continue;
    visited.add(id);
    const node = flow.nodes[id];
    if (!node) continue;
    const outs = flow.edges_from[id] ?? [];
    if (node.kind === "Decision" && outs.length > 1) return id;
    outs.forEach((e) => queue.push(e.target));
  }
  return null;
}

function computePath(
  flow: CompiledFlow,
  branchSelection: Record<string, string>,
  maxSteps = 200
): { nodes: string[]; edges: EdgeKey[] } {
  const pathNodes: string[] = [];
  const pathEdges: EdgeKey[] = [];
  let current = flow.entry;
  let steps = 0;
  const visited = new Set<string>();
  while (current && steps < maxSteps) {
    pathNodes.push(current);
    visited.add(current);
    const outs = (flow.edges_from[current] ?? []).slice().sort((a, b) => (a.priority ?? 0) - (b.priority ?? 0));
    if (outs.length === 0) break;
    let chosen: FlowEdgeSummary | undefined;
    if (flow.nodes[current]?.kind === "Decision" && outs.length > 1) {
      const preferredTarget = branchSelection[current];
      chosen = outs.find((e) => e.target === preferredTarget) ?? outs[0];
    } else {
      chosen = outs[0];
    }
    if (!chosen) break;
    pathEdges.push(`${chosen.source}->${chosen.target}` as EdgeKey);
    current = chosen.target;
    steps += 1;
    if (visited.has(current) && steps > 2) break; // guard against cycles in preview
  }
  return { nodes: pathNodes, edges: pathEdges };
}

function stepsFromNodes(flow: CompiledFlow, nodeIds: string[]): JourneyStep[] {
  return nodeIds
    .map((id) => flow.nodes[id])
    .filter(Boolean)
    .map((n) => ({
      id: n!.id,
      kind: n!.kind,
      title: n!.label ?? n!.id,
      // Question nodes may include a prompt for WhatsApp preview
      prompt: (n as unknown as { prompt?: string }).prompt,
    }));
}

export function FlowExperience({ flow }: { flow: CompiledFlow }) {
  const firstDecision = useMemo(() => findFirstBranchDecision(flow), [flow]);
  const branchOptions: BranchOption[] = useMemo(() => {
    if (!firstDecision) return [];
    const outs = (flow.edges_from[firstDecision] ?? []).slice().sort((a, b) => (a.priority ?? 0) - (b.priority ?? 0));
    return outs.map((e) => ({ targetId: e.target, label: pickLabel(e, flow.nodes) }));
  }, [firstDecision, flow]);

  const [selection, setSelection] = useState<Record<string, string>>(() => {
    if (!firstDecision || branchOptions.length === 0) return {};
    return { [firstDecision]: branchOptions[0].targetId };
  });

  useEffect(() => {
    if (!firstDecision) return;
    if (!selection[firstDecision] && branchOptions[0]) {
      setSelection({ [firstDecision]: branchOptions[0].targetId });
    }
  }, [firstDecision, branchOptions, selection]);

  const { nodes: pathNodes, edges: pathEdges } = useMemo(
    () => computePath(flow, selection),
    [flow, selection]
  );

  const highlightedNodes = useMemo(() => new Set(pathNodes), [pathNodes]);
  const highlightedEdges = useMemo(() => new Set<EdgeKey>(pathEdges), [pathEdges]);
  const steps = useMemo(() => stepsFromNodes(flow, pathNodes.filter((id) => flow.nodes[id]?.kind !== "Decision")), [flow, pathNodes]);

  return (
    <div className="space-y-6">
      <div className="rounded-xl border bg-card text-card-foreground shadow-sm p-4 md:p-6 space-y-4">
        <NodeLegend />
        <VerticalBranches
          flow={flow}
          selectedBranchId={selection[firstDecision ?? ""] ?? null}
          onSelect={(id) => {
            if (!firstDecision) return;
            setSelection({ [firstDecision]: id });
          }}
        />
      </div>
      <div className="rounded-xl border bg-card text-card-foreground shadow-sm p-4 md:p-6">
        <JourneyPreview steps={steps} title="Journey preview" />
      </div>
    </div>
  );
}


