"use client";

import type { NodeKind } from "./types";

export interface JourneyStep {
  id: string;
  kind: NodeKind;
  title: string;
  prompt?: string;
}

export function JourneyPreview({ steps, title }: { steps: JourneyStep[]; title?: string }) {
  return (
    <div className="w-full max-w-sm mx-auto">
      {title ? (
        <div className="mb-2 text-xs font-medium text-muted-foreground">{title}</div>
      ) : null}
      <div className="rounded-3xl border bg-white shadow-sm p-3">
        <div className="rounded-2xl bg-slate-50 p-3 h-[520px] overflow-y-auto">
          <div className="text-center text-[10px] text-muted-foreground mb-2">Como esta conversa deve ficar no WhatsApp</div>
          <div className="space-y-3">
            {steps.map((s) => (
              <div key={s.id} className="flex w-full">
                <div className="max-w-[80%] rounded-2xl rounded-tl-none bg-emerald-600 text-white px-3 py-2 shadow">
                  <div className="text-[11px] opacity-85 mb-0.5">{s.title}</div>
                  {s.prompt ? <div className="text-sm leading-relaxed">{s.prompt}</div> : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}


