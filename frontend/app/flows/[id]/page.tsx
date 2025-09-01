"use client";

import { SubflowSection } from "@/components/flow-viewer/SubflowSection";
import type { CompiledFlow } from "@/components/flow-viewer/types";
import { FlowExperience, type BranchOption } from "@/components/flow-viewer/FlowExperience";
import { CollapsibleFlowChat } from "@/components/flow-viewer/CollapsibleFlowChat";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Loader2, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { useState, useMemo, useEffect } from "react";

// Helper functions from FlowExperience
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
  const edges = flow.edges_from[nodeId] || [];
  return [...edges].sort((a, b) => ((a as any).order || 0) - ((b as any).order || 0));
}

function pickLabel(edge: any, nodes: any) {
  return edge.condition_description || edge.label || `Para ${nodes[edge.target]?.label || edge.target}`;
}

export default function FlowDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Array.isArray(params.id) ? params.id[0] : params.id;
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Simplified view state (moved from FlowExperience)
  const [showOnlyCurrentPath, setShowOnlyCurrentPath] = useState(true);
  const [selection, setSelection] = useState<Record<string, string>>({});
  
  const { data: flow, isLoading, isError, refetch } = useQuery({
    queryKey: ["compiledFlow", id],
    queryFn: async () => {
      const result = await api.flows.getCompiled(id);
      return result as unknown as CompiledFlow;
    },
    staleTime: 1000 * 60 * 5, // Shorter stale time for more frequent updates
    refetchOnWindowFocus: false, // Prevent unnecessary refetches
    refetchOnMount: true, // Always refetch when component mounts
  });



  // Compute simplified view values (moved from FlowExperience)
  const firstDecision = useMemo(() => flow ? findFirstBranchDecision(flow as unknown as CompiledFlow) : null, [flow]);
  const branchOptions: BranchOption[] = useMemo(() => {
    if (!firstDecision || !flow) return [];
    const outs = sortedOutgoing(flow as unknown as CompiledFlow, firstDecision);
    return outs.map((e) => ({ targetId: e.target, label: pickLabel(e, (flow as unknown as CompiledFlow).nodes) }));
  }, [firstDecision, flow]);

  // Initialize selection when flow loads
  useEffect(() => {
    if (!firstDecision || !flow) return;
    if (!selection[firstDecision] && branchOptions[0]) {
      setSelection({ [firstDecision]: branchOptions[0].targetId });
    }
  }, [firstDecision, branchOptions, selection, flow]);

  // Get current active path info for chat context
  const currentPathLabel = useMemo(() => {
    if (!firstDecision || !selection[firstDecision] || !branchOptions.length) return null;
    const selectedOption = branchOptions.find(opt => opt.targetId === selection[firstDecision]);
    return selectedOption?.label || null;
  }, [firstDecision, selection, branchOptions]);

const handleFlowModified = async () => {
    console.log("🔄 Flow modification detected, refreshing...");
    setIsRefreshing(true);
    try {
      const result = await refetch();
      console.log("✅ Flow refreshed successfully", result);
      toast.success("Fluxo atualizado automaticamente!", {
        icon: <CheckCircle2 className="h-4 w-4" />,
        description: "As alterações já são visíveis no diagrama"
      });
    } catch (error) {
      console.error("❌ Failed to refresh flow:", error);
      toast.error("Falha ao atualizar visualização do fluxo", {
        description: "Tente recarregar a página manualmente"
      });
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div className="min-h-screen w-full bg-background relative">
      <div className="mx-auto max-w-none px-4 py-6 md:py-8 space-y-6">
        <div className="flex items-baseline justify-between max-w-7xl mx-auto">
          <h1 className="text-2xl font-semibold tracking-tight">Visualização do Fluxo</h1>
          {flow ? (
            <div className="text-xs text-muted-foreground">ID: {(flow as unknown as CompiledFlow).id}</div>
          ) : null}
        </div>

        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground max-w-7xl mx-auto">
            <Loader2 className="h-4 w-4 animate-spin" /> Carregando fluxo…
          </div>
        ) : isError || !flow ? (
          <div className="rounded-md border p-4 text-sm max-w-7xl mx-auto">
            Falha ao carregar o fluxo. <button className="underline ml-1" onClick={() => refetch()}>Tentar novamente</button>
          </div>
        ) : (
          <>
            <div className="relative">
              {isRefreshing && (
                <div className="absolute inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-10 rounded-lg">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <Loader2 className="h-5 w-5 animate-spin" />
                    Atualizando fluxo...
                  </div>
                </div>
              )}
              <div className="flex justify-center">
                <div className="w-full max-w-6xl">
                  <FlowExperience 
                    flow={flow as unknown as CompiledFlow} 
                    showOnlyCurrentPath={showOnlyCurrentPath}
                    setShowOnlyCurrentPath={setShowOnlyCurrentPath}
                    selection={selection}
                    setSelection={setSelection}
                    branchOptions={branchOptions}
                  />
                </div>
              </div>
            </div>
            <div className="max-w-7xl mx-auto">
              <SubflowSection subflows={(flow as unknown as CompiledFlow).subflows} />
            </div>
          </>
        )}
      </div>
      
      {/* Collapsible chat overlay */}
      {flow && (
        <CollapsibleFlowChat 
          flowId={id} 
          onFlowModified={handleFlowModified}
          simplifiedViewEnabled={showOnlyCurrentPath}
          activePath={currentPathLabel}
        />
      )}
    </div>
  );
}

