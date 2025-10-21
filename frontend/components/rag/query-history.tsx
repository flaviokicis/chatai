"use client";

import React from "react";
import { Clock, CheckCircle2, XCircle, RotateCcw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { QueryHistoryItem } from "@/lib/rag-admin";

interface QueryHistoryProps {
  history: QueryHistoryItem[];
  onRerunQuery: (query: string) => void;
  onClearHistory: () => void;
}

function formatRelativeTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "Agora";
  if (diffMins < 60) return `${diffMins}m atrás`;
  if (diffHours < 24) return `${diffHours}h atrás`;
  if (diffDays < 7) return `${diffDays}d atrás`;
  return date.toLocaleDateString();
}

export function QueryHistory({
  history,
  onRerunQuery,
  onClearHistory,
}: QueryHistoryProps): React.JSX.Element {
  if (history.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Clock className="h-5 w-5 text-primary" />
            Histórico de Consultas
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex h-32 flex-col items-center justify-center gap-2 rounded-md border border-dashed bg-muted/20 text-center text-sm text-muted-foreground">
            <Clock className="h-6 w-6 text-muted-foreground/70" />
            <span>Nenhuma consulta ainda. Seu histórico aparecerá aqui.</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          <Clock className="h-5 w-5 text-primary" />
          Histórico de Consultas
          <Badge variant="secondary" className="ml-2">
            {history.length}
          </Badge>
        </CardTitle>
        <Button
          variant="ghost"
          size="sm"
          onClick={onClearHistory}
          className="text-muted-foreground hover:text-destructive"
        >
          Limpar tudo
        </Button>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[400px] pr-4">
          <div className="space-y-3">
            {history.map((item) => (
              <div
                key={item.id}
                className="group rounded-lg border bg-background p-3 shadow-sm transition hover:border-primary/40 hover:shadow-md"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2">
                      {item.sufficient ? (
                        <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600" />
                      ) : (
                        <XCircle className="h-4 w-4 shrink-0 text-amber-600" />
                      )}
                      <span className="text-xs text-muted-foreground">
                        {formatRelativeTime(item.timestamp)}
                      </span>
                      <Badge variant="outline" className="text-xs">
                        {item.resultCount} chunks
                      </Badge>
                    </div>
                    <p className="text-sm leading-relaxed text-foreground">
                      {item.query}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onRerunQuery(item.query)}
                    className="shrink-0 opacity-0 transition group-hover:opacity-100"
                  >
                    <RotateCcw className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

export default QueryHistory;

