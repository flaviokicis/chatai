"use client";

import { useMemo } from "react";
import type { CompiledFlow } from "./types";
import { NodeCard } from "./NodeCard";
import { pickLabel, sortedOutgoing } from "./helpers";

function collectLinearPath(flow: CompiledFlow, startId: string, max = 200): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  let current: string | undefined = startId;
  let steps = 0;
  while (current && steps < max && !seen.has(current)) {
    result.push(current);
    seen.add(current);
    const outs = sortedOutgoing(flow, current);
    if (outs.length === 0) break;
    current = outs[0].target;
    steps += 1;
  }
  return result;
}

type GlobalSegment = { kind: "global"; nodes: string[] };
type BranchColumn = { id: string; label: string; nodes: string[] };
type BranchSegment = { kind: "branch"; decisionId: string; branches: BranchColumn[] };
type Segment = GlobalSegment | BranchSegment;

function computeSegments(flow: CompiledFlow): Segment[] {
  const segments: Segment[] = [];

  let current: string | undefined = flow.entry;
  const hardStop = new Set<string>();

  // helper: advance through globals until decision or end
  function consumeGlobal(startId: string | undefined): { list: string[]; decisionId?: string; next?: string } {
    const list: string[] = [];
    let cur = startId;
    const visited = new Set<string>();
    while (cur && !visited.has(cur)) {
      list.push(cur);
      visited.add(cur);
      const node = flow.nodes[cur];
      const outs = sortedOutgoing(flow, cur);
      if (node?.kind === "Decision" && outs.length > 1) {
        return { list, decisionId: cur, next: cur };
      }
      if (outs.length === 0) return { list };
      cur = outs[0].target;
    }
    return { list };
  }

  while (current && !hardStop.has(current)) {
    hardStop.add(current);

    const { list: globals, decisionId } = consumeGlobal(current);
    if (globals.length) segments.push({ kind: "global", nodes: globals });
    if (!decisionId) break;

    // Build branches from this decision
    const outs = sortedOutgoing(flow, decisionId);
    const branchLists = outs.map((e) => collectLinearPath(flow, e.target));
    // Remove terminal nodes
    const filteredLists = branchLists.map((lst) => lst.filter((id) => flow.nodes[id]?.kind !== "Terminal"));

    // Compute common suffix
    const minLen = Math.min(...filteredLists.map((l) => l.length));
    let commonTail: string[] = [];
    for (let i = 1; i <= minLen; i++) {
      const candidate = filteredLists[0][filteredLists[0].length - i];
      if (filteredLists.every((l) => l[l.length - i] === candidate)) {
        commonTail.push(candidate);
      } else {
        break;
      }
    }
    commonTail = commonTail.reverse();

    const branches: BranchColumn[] = outs.map((e, idx) => {
      const full = filteredLists[idx];
      const visible = commonTail.length ? full.slice(0, Math.max(0, full.length - commonTail.length)) : full;
      return { id: e.target, label: pickLabel(e, flow.nodes), nodes: visible };
    });

    segments.push({ kind: "branch", decisionId, branches });

    current = commonTail[0];
    if (!current) break;
  }

  return segments;
}

export function FlowSegments({
  flow,
  selection,
  onSelect,
}: {
  flow: CompiledFlow;
  selection?: Record<string, string>;
  onSelect?: (decisionId: string, targetId: string) => void;
}) {
  const segments = useMemo(() => computeSegments(flow), [flow]);

  // Get UI labels from flow metadata, with intelligent fallbacks based on flow ID
  const getUILabels = () => {
    const metadata = flow.metadata;
    const uiLabels = metadata?.ui_labels;
    
    // Intelligent defaults based on flow type/ID
    const isPortuguese = flow.id?.includes('consultorio') || flow.id?.includes('agendamento') || flow.id?.includes('vendas');
    const defaultGlobalLabel = isPortuguese ? "Perguntas gerais" : "Global Questions";
    const defaultBranchPrefix = isPortuguese ? "Caminho" : "Path";
    const defaultLocale = isPortuguese ? "pt-BR" : "en";
    
    return {
      globalSectionLabel: uiLabels?.global_section_label || defaultGlobalLabel,
      branchSectionPrefix: uiLabels?.branch_section_prefix || defaultBranchPrefix,
      locale: uiLabels?.locale || defaultLocale
    };
  };

  const uiLabels = getUILabels();

  return (
    <div className="space-y-4">
      {segments.map((seg, idx) => {
        if (seg.kind === "global") {
          const label = uiLabels.globalSectionLabel;
          return (
            <div key={`g-${idx}`} className="rounded-xl border bg-card p-3">
              <div className="text-xs font-medium text-muted-foreground mb-2">{label}</div>
              <div className="relative">
                <div className="absolute left-[18px] top-0 bottom-0 w-px bg-border" />
                <div className="space-y-3">
                  {seg.nodes
                    .filter((nodeId) => flow.nodes[nodeId]?.kind !== "Terminal")
                    .map((nodeId) => (
                    <div key={nodeId} className="relative pl-6">
                      <div className="absolute left-[14px] top-5 h-2 w-2 rounded-full bg-border" />
                      <NodeCard 
                        node={{ ...flow.nodes[nodeId], isEntry: flow.entry === nodeId, outgoing: flow.edges_from[nodeId] ?? [] }} 
                        variant="compact" 
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          );
        }
        // Branch segment
        const colCount = Math.max(1, seg.branches.length);
        const gridCols = colCount === 1
          ? "grid-cols-1"
          : colCount === 2
          ? "grid-cols-2"
          : colCount === 3
          ? "grid-cols-3"
          : colCount === 4
          ? "grid-cols-4"
          : "grid-cols-5";
        return (
          <div key={`b-${seg.decisionId}-${idx}`} className={`grid ${gridCols} gap-4 min-w-[720px] xl:min-w-0`}>
            {seg.branches.map((b) => (
              <div key={b.id} className="rounded-xl border bg-card p-3">
                <button
                  type="button"
                  onClick={() => onSelect?.(seg.decisionId, b.id)}
                  className={`mb-3 w-full text-left text-sm font-medium px-3 py-2 rounded-lg border cursor-pointer transition-all duration-200 ${
                    selection && selection[seg.decisionId] === b.id
                      ? "bg-primary text-primary-foreground border-primary shadow-sm"
                      : "bg-muted/40 hover:bg-muted/60 hover:border-primary/30 border-border hover:shadow-sm"
                  }`}
                  title={`Clique para ver o caminho: ${b.label}`}
                >
                  {b.label}
                </button>
                <div className="relative">
                  <div className="absolute left-[18px] top-0 bottom-0 w-px bg-border" />
                  <div className="space-y-2.5">
                    {b.nodes.map((nodeId) => (
                      <div key={nodeId} className="relative pl-6 group">
                        <div className={`absolute left-[14px] top-5 h-2 w-2 rounded-full ${selection && selection[seg.decisionId] === b.id ? "bg-primary" : "bg-border"}`} />
                        <NodeCard
                          node={{ ...flow.nodes[nodeId], isEntry: flow.entry === nodeId, outgoing: flow.edges_from[nodeId] ?? [] }}
                          highlighted={selection && selection[seg.decisionId] === b.id}
                          variant="compact"
                          flat={!selection || selection[seg.decisionId] !== b.id}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}


