"use client";

import { useEffect, useMemo, useState } from "react";
import type { CompiledFlow, FlowEdgeSummary } from "./types";
import { JourneyPreview, type JourneyStep } from "./JourneyPreview";
import { NodeLegend } from "./NodeLegend";
import { FlowSegments } from "./FlowSegments";
import { pickLabel, sortedOutgoing } from "./helpers";

type BranchOption = { targetId: string; label: string };

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

function computePath(flow: CompiledFlow, branchSelection: Record<string, string>, maxSteps = 200): string[] {
  const nodes: string[] = [];
  let current = flow.entry;
  let steps = 0;
  const visited = new Set<string>();
  while (current && steps < maxSteps) {
    nodes.push(current);
    visited.add(current);
    const outs = sortedOutgoing(flow, current);
    if (outs.length === 0) break;
    let chosen: FlowEdgeSummary | undefined;
    if (flow.nodes[current]?.kind === "Decision" && outs.length > 1) {
      const preferredTarget = branchSelection[current];
      chosen = outs.find((e) => e.target === preferredTarget) ?? outs[0];
    } else {
      chosen = outs[0];
    }
    if (!chosen) break;
    current = chosen.target;
    steps += 1;
    if (visited.has(current) && steps > 2) break; // guard against cycles in preview
  }
  return nodes;
}

function stepsFromNodes(flow: CompiledFlow, nodeIds: string[]): JourneyStep[] {
  return nodeIds
    .map((id) => flow.nodes[id])
    .filter(Boolean)
    .filter((n) => n!.kind !== "Decision" && n!.kind !== "Terminal")
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
    const outs = sortedOutgoing(flow, firstDecision);
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

  const pathNodes = useMemo(() => computePath(flow, selection), [flow, selection]);

  const steps = useMemo(() => stepsFromNodes(flow, pathNodes), [flow, pathNodes]);

  return (
    <div className="space-y-6">
      <div className="rounded-xl border bg-card text-card-foreground shadow-sm p-4 md:p-6 space-y-4">
        <div className="flex items-center flex-wrap gap-3">
          <NodeLegend />
        </div>
        {/* Flexible segmented renderer: globals, branch groups, more globals, etc. */}
        <FlowSegments
          flow={flow}
          selection={selection}
          onSelect={(decisionId, targetId) => setSelection({ [decisionId]: targetId })}
        />
      </div>
      <div className="rounded-xl border bg-card text-card-foreground shadow-sm p-4 md:p-6">
        <JourneyPreview steps={steps} title="Visualização do fluxo no WhatsApp" />
      </div>
    </div>
  );
}


