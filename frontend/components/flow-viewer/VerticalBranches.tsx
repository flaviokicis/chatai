"use client";

import { useMemo } from "react";
import type { CompiledFlow, FlowEdgeSummary } from "./types";
import { NodeCard } from "./NodeCard";

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

function collectLinearPath(flow: CompiledFlow, startId: string, max = 200): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  let current: string | undefined = startId;
  let steps = 0;
  while (current && steps < max && !seen.has(current)) {
    result.push(current);
    seen.add(current);
    const outs = (flow.edges_from[current] ?? []).slice().sort((a, b) => (a.priority ?? 0) - (b.priority ?? 0));
    if (outs.length === 0) break;
    // Continue linearly by taking the first edge by priority
    current = outs[0].target;
    steps += 1;
  }
  return result;
}

export interface BranchColumn {
  id: string; // target node id from decision edge
  label: string;
  nodes: string[]; // ordered downstream nodes including target
}

export function VerticalBranches({
  flow,
  onSelect,
  selectedBranchId,
}: {
  flow: CompiledFlow;
  onSelect?: (branchId: string) => void;
  selectedBranchId?: string | null;
}) {
  const decisionId = useMemo(() => findFirstBranchDecision(flow), [flow]);
  const branches: BranchColumn[] = useMemo(() => {
    if (!decisionId) {
      return [
        {
          id: flow.entry,
          label: flow.nodes[flow.entry]?.label ?? flow.entry,
          nodes: collectLinearPath(flow, flow.entry),
        },
      ];
    }
    const outs = (flow.edges_from[decisionId] ?? []).slice().sort((a, b) => (a.priority ?? 0) - (b.priority ?? 0));
    return outs.map((e) => ({
      id: e.target,
      label: pickLabel(e, flow.nodes),
      nodes: collectLinearPath(flow, e.target),
    }));
  }, [flow, decisionId]);

  // Pre-branch (global) linear path from entry to the decision node
  const preBranchNodes: string[] = useMemo(() => {
    if (!decisionId) return [];
    // Walk from entry until decisionId inclusively
    const result: string[] = [];
    const visited = new Set<string>();
    let current = flow.entry;
    while (current && !visited.has(current)) {
      result.push(current);
      visited.add(current);
      if (current === decisionId) break;
      const outs = (flow.edges_from[current] ?? []).slice().sort((a, b) => (a.priority ?? 0) - (b.priority ?? 0));
      if (outs.length === 0) break;
      current = outs[0].target;
    }
    return result;
  }, [flow, decisionId]);

  const gridCols = `grid-cols-${Math.max(1, branches.length)}`;

  // Remove terminal nodes (e.g., t.done) from branch columns and compute common suffix
  const filteredBranches: BranchColumn[] = useMemo(() => {
    return branches.map((b) => ({
      ...b,
      nodes: b.nodes.filter((nid) => flow.nodes[nid]?.kind !== "Terminal"),
    }));
  }, [branches, flow.nodes]);

  const commonTail: string[] = useMemo(() => {
    if (filteredBranches.length === 0) return [];
    const lists = filteredBranches.map((b) => b.nodes);
    if (lists.some((l) => l.length === 0)) return [];
    const minLen = Math.min(...lists.map((l) => l.length));
    const tail: string[] = [];
    for (let i = 1; i <= minLen; i++) {
      const candidate = lists[0][lists[0].length - i];
      if (lists.every((l) => l[l.length - i] === candidate)) {
        tail.push(candidate);
      } else {
        break;
      }
    }
    return tail.reverse();
  }, [filteredBranches]);

  const branchesWithoutTail: BranchColumn[] = useMemo(() => {
    if (commonTail.length === 0) return filteredBranches;
    const tailLen = commonTail.length;
    return filteredBranches.map((b) => ({
      ...b,
      nodes: b.nodes.slice(0, Math.max(0, b.nodes.length - tailLen)),
    }));
  }, [filteredBranches, commonTail]);

  return (
    <div className="w-full overflow-x-auto">
      {/* Global pre-branch sequence */}
      {preBranchNodes.length > 0 ? (
        <div className="mb-4">
          <div className="rounded-xl border bg-card p-3">
            <div className="text-xs font-medium text-muted-foreground mb-2">Perguntas globais</div>
            <div className="relative">
              <div className="absolute left-[18px] top-0 bottom-0 w-px bg-border" />
              <div className="space-y-3">
                {preBranchNodes.map((nodeId) => (
                  <div key={nodeId} className="relative pl-6">
                    <div className="absolute left-[14px] top-5 h-2 w-2 rounded-full bg-border" />
                    <NodeCard node={{ ...flow.nodes[nodeId], isEntry: flow.entry === nodeId, outgoing: flow.edges_from[nodeId] ?? [] }} variant="compact" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* Branch columns */}
      <div className={`grid ${gridCols} gap-4 min-w-[720px] xl:min-w-0`}> 
        {branchesWithoutTail.map((b) => (
          <div key={b.id} className="rounded-xl border bg-card p-3">
             <button
              type="button"
              onClick={() => onSelect?.(b.id)}
               className={`mb-3 w-full text-left text-sm font-medium px-3 py-2 rounded-lg border cursor-pointer ${
                selectedBranchId === b.id
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-muted/40 hover:bg-muted border-border"
              }`}
            >
              {b.label}
            </button>
              <div className="relative">
                <div className="absolute left-[18px] top-0 bottom-0 w-px bg-border" />
                <div className="space-y-2.5">
                {b.nodes.map((nodeId) => (
                    <div key={nodeId} className="relative pl-6 group">
                      <div className={`absolute left-[14px] top-5 h-2 w-2 rounded-full ${selectedBranchId === b.id ? "bg-primary" : "bg-border"}`} />
                    <NodeCard node={{ ...flow.nodes[nodeId], isEntry: flow.entry === nodeId, outgoing: flow.edges_from[nodeId] ?? [] }} highlighted={selectedBranchId === b.id} variant="compact" flat={selectedBranchId !== b.id} />
                    </div>
                  ))}
                </div>
              </div>
          </div>
        ))}
      </div>

      {/* Global tail (shown once after branches) */}
      {commonTail.length > 0 ? (
        <div className="mt-4 rounded-xl border bg-card p-3">
          <div className="text-xs font-medium text-muted-foreground mb-2">Perguntas globais (finais)</div>
          <div className="relative">
            <div className="absolute left-[18px] top-0 bottom-0 w-px bg-border" />
            <div className="space-y-2.5">
              {commonTail.map((nodeId) => (
                <div key={nodeId} className="relative pl-6 group">
                  <div className="absolute left-[14px] top-5 h-2 w-2 rounded-full bg-border" />
                  <NodeCard node={{ ...flow.nodes[nodeId], isEntry: flow.entry === nodeId, outgoing: flow.edges_from[nodeId] ?? [] }} variant="compact" flat />
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}


