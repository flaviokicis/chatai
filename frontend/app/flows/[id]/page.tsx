"use client";

import { SubflowSection } from "@/components/flow-viewer/SubflowSection";
import type { CompiledFlow } from "@/components/flow-viewer/types";
import { FlowExperience } from "@/components/flow-viewer/FlowExperience";
import { FlowEditorChat } from "@/components/flow-viewer/FlowEditorChat";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { Loader2 } from "lucide-react";

export default function FlowDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Array.isArray(params.id) ? params.id[0] : params.id;

  const { data: flow, isLoading, isError, refetch } = useQuery<CompiledFlow>({
    queryKey: ["compiledFlow", id],
    queryFn: () => api.flows.getCompiled(id),
    staleTime: 1000 * 60 * 30,
  });

  return (
    <div className="min-h-screen w-full bg-background">
      <div className="mx-auto max-w-7xl px-4 py-6 md:py-8 space-y-6">
        <div className="flex items-baseline justify-between">
          <h1 className="text-2xl font-semibold tracking-tight">Fluxo: {id}</h1>
          {flow ? (
            <div className="text-xs text-muted-foreground">Identificador do fluxo: {flow.id}</div>
          ) : null}
        </div>

        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Carregando fluxo…
          </div>
        ) : isError || !flow ? (
          <div className="rounded-md border p-4 text-sm">
            Falha ao carregar o fluxo. <button className="underline ml-1" onClick={() => refetch()}>Tentar novamente</button>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 2xl:grid-cols-4 gap-6">
              <div className="2xl:col-span-3">
                <FlowExperience flow={flow} />
              </div>
              <div>
                <FlowEditorChat flowId={id} />
              </div>
            </div>
            <SubflowSection subflows={flow.subflows} />
          </>
        )}
      </div>
    </div>
  );
}

