import { Suspense } from "react";
import { SubflowSection } from "@/components/flow-viewer/SubflowSection";
import type { CompiledFlow } from "@/components/flow-viewer/types";
import { FlowExperience } from "@/components/flow-viewer/FlowExperience";
import { CollapsibleFlowChat } from "@/components/flow-viewer/CollapsibleFlowChat";

type Params = Promise<{ id: string }>;

async function fetchCompiledFlow(): Promise<CompiledFlow> {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080";
  const res = await fetch(`${base}/flows/example/compiled`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to load flow: ${res.status}`);
  }
  return (await res.json()) as CompiledFlow;
}

function GraphSkeleton() {
  return (
    <div className="animate-pulse text-sm text-muted-foreground">Carregando fluxo…</div>
  );
}

export default async function AgentDetailPage({ params }: { params: Params }) {
  const { id } = await params;
  const flow = await fetchCompiledFlow();

  return (
    <div className="min-h-screen w-full bg-background relative">
      <div className="mx-auto max-w-none px-4 py-6 md:py-8 space-y-6">
        <div className="flex items-baseline justify-between max-w-7xl mx-auto">
          <h1 className="text-2xl font-semibold tracking-tight">Agente (migrar): {id}</h1>
          <div className="text-xs text-muted-foreground">Use a página Fluxos para visualizar e editar</div>
        </div>
        <div className="flex justify-center">
          <div className="w-full max-w-6xl">
            <Suspense fallback={<GraphSkeleton />}>
              <FlowExperience flow={flow} />
            </Suspense>
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


