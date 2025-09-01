"use client";

import { useState, useMemo, useEffect } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { SubflowSection } from "@/components/flow-viewer/SubflowSection";
import type { CompiledFlow } from "@/components/flow-viewer/types";
import { FlowExperience, type BranchOption } from "@/components/flow-viewer/FlowExperience";
import { CollapsibleFlowChat } from "@/components/flow-viewer/CollapsibleFlowChat";
import { api } from "@/lib/api-client";
import { Loader2 } from "lucide-react";

// Helper functions (copied from flows/[id]/page.tsx)
function findFirstBranchDecision(flow: CompiledFlow): string | null {
  const queue = [flow.entry];
  while (queue.length) {
    const current = queue.shift();
    if (!current) continue;
    const node = flow.nodes[current];
    const outs = flow.edges_from[current] || [];
    if (node?.kind === "Decision" && outs.length > 1) return current;
    outs.forEach((e) => queue.push(e.target));
  }
  return null;
}

function sortedOutgoing(flow: CompiledFlow, nodeId: string) {
  return (flow.edges_from[nodeId] || []).sort((a, b) => (a.priority || 0) - (b.priority || 0));
}

function pickLabel(edge: any, nodes: any) {
  return edge.condition_description || edge.label || `Opção ${edge.priority + 1}`;
}

export default function AgentDetailPage() {
  const params = useParams();
  const id = Array.isArray(params.id) ? params.id[0] : params.id as string;
  
  // State for FlowExperience
  const [showOnlyCurrentPath, setShowOnlyCurrentPath] = useState(true);
  const [selection, setSelection] = useState<Record<string, string>>({});

  const { data: flow, isLoading, isError } = useQuery({
    queryKey: ["compiledFlow", "example"],
    queryFn: async () => {
      const result = await api.flows.getExampleCompiled();
      return result as unknown as CompiledFlow;
    },
  });

  // Compute branch options
  const firstDecision = useMemo(() => flow ? findFirstBranchDecision(flow) : null, [flow]);
  const branchOptions: BranchOption[] = useMemo(() => {
    if (!firstDecision || !flow) return [];
    const outs = sortedOutgoing(flow, firstDecision);
    return outs.map((e) => ({ targetId: e.target, label: pickLabel(e, flow.nodes) }));
  }, [firstDecision, flow]);

  // Initialize selection when flow loads
  useEffect(() => {
    if (!firstDecision || !flow) return;
    if (!selection[firstDecision] && branchOptions[0]) {
      setSelection({ [firstDecision]: branchOptions[0].targetId });
    }
  }, [firstDecision, branchOptions, selection, flow]);

  if (isLoading) {
    return (
      <div className="min-h-screen w-full bg-background relative">
        <div className="mx-auto max-w-none px-4 py-6 md:py-8 space-y-6">
          <div className="flex justify-center items-center min-h-48">
            <Loader2 className="h-8 w-8 animate-spin" />
          </div>
        </div>
      </div>
    );
  }

  if (isError || !flow) {
    return (
      <div className="min-h-screen w-full bg-background relative">
        <div className="mx-auto max-w-none px-4 py-6 md:py-8 space-y-6">
          <div className="text-center text-red-600">
            Erro ao carregar o fluxo. Tente novamente.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen w-full bg-background relative">
      <div className="mx-auto max-w-none px-4 py-6 md:py-8 space-y-6">
        <div className="flex items-baseline justify-between max-w-7xl mx-auto">
          <h1 className="text-2xl font-semibold tracking-tight">Agente (migrar): {id}</h1>
          <div className="text-xs text-muted-foreground">Use a página Fluxos para visualizar e editar</div>
        </div>
        <div className="flex justify-center">
          <div className="w-full max-w-6xl">
            <FlowExperience 
              flow={flow}
              showOnlyCurrentPath={showOnlyCurrentPath}
              setShowOnlyCurrentPath={setShowOnlyCurrentPath}
              selection={selection}
              setSelection={setSelection}
              branchOptions={branchOptions}
            />
          </div>
        </div>
        <div className="max-w-7xl mx-auto">
          <SubflowSection subflows={flow.subflows} />
        </div>
      </div>
      
      {/* Collapsible chat overlay */}
      <CollapsibleFlowChat flowId={id} />
    </div>
  );
}