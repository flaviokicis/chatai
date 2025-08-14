"use client";

export function NodeLegend() {
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      <div className="flex items-center gap-1">
        <span className="inline-block h-2 w-2 rounded-full" style={{ background: "#ecfdf5", border: "1px solid #10b981" }} />
        Pergunta
      </div>
      <div className="flex items-center gap-1">
        <span className="inline-block h-2 w-2 rounded-full" style={{ background: "#fffbeb", border: "1px solid #f59e0b" }} />
        Decisão
      </div>
      <div className="flex items-center gap-1">
        <span className="inline-block h-2 w-2 rounded-full" style={{ background: "#eff6ff", border: "1px solid #3b82f6" }} />
        Terminal
      </div>
      <div className="flex items-center gap-1">
        <span className="inline-block h-2 w-2 rounded-sm bg-primary" />
        Caminho destacado
      </div>
    </div>
  );
}


