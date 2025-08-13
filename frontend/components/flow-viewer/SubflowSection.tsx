"use client";

import type { CompiledFlow } from "./types";
import { FlowViewer } from "./FlowViewer";

export function SubflowSection({ subflows }: { subflows: Record<string, CompiledFlow> | undefined }) {
  if (!subflows || Object.keys(subflows).length === 0) return null;
  return (
    <div className="mt-8 space-y-6">
      {Object.entries(subflows).map(([name, sub]) => (
        <div key={name} className="rounded-xl border bg-card p-4">
          <div className="mb-3 text-sm font-medium">Subflow: {name}</div>
          <div className="w-full overflow-x-auto">
            <FlowViewer flow={sub} />
          </div>
        </div>
      ))}
    </div>
  );
}


