"use client";

import React, { useState } from "react";
import { Brain, ListChecks, Loader2 } from "lucide-react";

import type { QueryResult } from "@/lib/rag-admin";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface QueryTesterProps {
  disabled: boolean;
  isLoading: boolean;
  onSubmit: (query: string) => Promise<void>;
  result: QueryResult | null;
}

export function QueryTester({
  disabled,
  isLoading,
  onSubmit,
  result,
}: QueryTesterProps): React.JSX.Element {
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      setError("Por favor, insira uma consulta para testar.");
      return;
    }

    setError(null);
    await onSubmit(trimmed);
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Brain className="h-5 w-5 text-primary" />
            Testar Recuperação de Contexto
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={handleSubmit} className="space-y-3">
            <Textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ex: Quais são os argumentos de vendas para luminárias LED?"
              disabled={disabled || isLoading}
              minLength={3}
              rows={3}
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="flex justify-end">
              <Button
                type="submit"
                disabled={disabled || isLoading}
                className="min-w-[180px]"
              >
                {isLoading ? "Consultando…" : "Testar Consulta"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {result && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-semibold">
                Resposta Provável da IA
              </CardTitle>
            </CardHeader>
            <CardContent>
              {result.generatedAnswer ? (
                <div className="rounded-lg bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 p-4">
                  <p className="text-sm leading-relaxed text-foreground whitespace-pre-wrap">
                    {result.generatedAnswer}
                  </p>
                </div>
              ) : (
                <div className="flex items-center justify-center py-4">
                  <Loader2 className="h-5 w-5 animate-spin text-primary mr-2" />
                  <span className="text-sm text-muted-foreground">Gerando resposta com GPT-5-mini...</span>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base font-semibold">
                Contexto Retornado para IA
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge variant={result.success ? "default" : "secondary"}>
                  {result.success ? "Contexto relevante" : "Contexto insuficiente"}
                </Badge>
                {result.sufficient ? (
                  <Badge variant="outline">Análise: suficiente</Badge>
                ) : (
                  <Badge variant="destructive" className="bg-destructive/10 text-destructive">
                    Análise: insuficiente
                  </Badge>
                )}
                <Badge variant="secondary">Tentativas: {result.attempts}</Badge>
              </div>

              {result.judgeReasoning && (
                <p className="text-sm text-muted-foreground">
                  <span className="font-medium text-foreground">Notas da análise:</span>{" "}
                  {result.judgeReasoning}
                </p>
              )}

              {result.noDocuments && (
                <p className="rounded-md border border-dashed bg-muted/40 p-3 text-sm text-muted-foreground">
                  Nenhum documento encontrado para este tenant. Faça upload antes de testar consultas.
                </p>
              )}

              {result.context ? (
                <pre className="max-h-[420px] whitespace-pre-wrap rounded-lg bg-muted/30 p-4 text-sm leading-relaxed text-foreground overflow-y-auto">
                  {result.context}
                </pre>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Nenhum contexto retornado nesta consulta.
                </p>
              )}

              {result.error && (
                <p className="text-sm text-destructive">
                  Erro na consulta: {result.error}
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <ListChecks className="h-4 w-4 text-primary" />
                Chunks Recuperados ({result.chunks.length})
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {result.chunks.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Nenhum chunk foi retornado para esta consulta.
                </p>
              ) : (
                <div className="max-h-[480px] space-y-3 overflow-y-auto pr-2">
                  {result.chunks.map((chunk) => (
                    <article
                      key={chunk.id}
                      className="rounded-lg border bg-background p-3 shadow-sm transition hover:border-primary/40"
                    >
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <Badge variant="secondary">
                          Relevância: {chunk.score.toFixed(3)}
                        </Badge>
                        {chunk.documentName && (
                          <Badge variant="outline">{chunk.documentName}</Badge>
                        )}
                        {chunk.category && (
                          <Badge variant="outline">{chunk.category}</Badge>
                        )}
                      </div>
                      <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                        {chunk.content}
                      </p>
                      {chunk.metadata && Object.keys(chunk.metadata).length > 0 && (
                        <pre className="mt-3 rounded-md bg-muted/40 p-2 text-xs text-muted-foreground">
                          {JSON.stringify(chunk.metadata, null, 2)}
                        </pre>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

export default QueryTester;
