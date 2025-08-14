import { Suspense } from "react";
import { SubflowSection } from "@/components/flow-viewer/SubflowSection";
import type { CompiledFlow } from "@/components/flow-viewer/types";
import { FlowExperience } from "@/components/flow-viewer/FlowExperience";
import { FlowEditorChat } from "@/components/flow-viewer/FlowEditorChat";

type Params = Promise<{ id: string }>;

async function fetchCompiledFlow(): Promise<CompiledFlow> {
  const base = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
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

export default async function FlowDetailPage({ params }: { params: Params }) {
  const { id } = await params;
  const flow = await fetchCompiledFlow();

  return (
    <div className="min-h-screen w-full bg-background">
      <div className="mx-auto max-w-7xl px-4 py-6 md:py-8 space-y-6">
        <div className="flex items-baseline justify-between">
          <h1 className="text-2xl font-semibold tracking-tight">Fluxo: {id}</h1>
          <div className="text-xs text-muted-foreground">Identificador do fluxo: {flow.id}</div>
        </div>
        <div className="grid grid-cols-1 2xl:grid-cols-4 gap-6">
          <div className="2xl:col-span-3">
            <Suspense fallback={<GraphSkeleton />}>
              <FlowExperience flow={flow} />
            </Suspense>
          </div>
          <div>
            <FlowEditorChat />
          </div>
        </div>
        <SubflowSection subflows={flow.subflows} />
      </div>
    </div>
  );
}


