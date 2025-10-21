"use client";

import React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";

import type { DocumentDetail } from "@/lib/rag-admin";

interface DocumentDetailDialogProps {
  document?: DocumentDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isLoading: boolean;
}

function renderMetadata(metadata?: Record<string, unknown> | null): React.ReactNode {
  if (!metadata || Object.keys(metadata).length === 0) {
    return <span className="text-sm text-muted-foreground">No metadata provided.</span>;
  }

  return (
    <pre className="rounded-md bg-muted/50 p-3 text-xs leading-relaxed text-muted-foreground">
      {JSON.stringify(metadata, null, 2)}
    </pre>
  );
}

export function DocumentDetailDialog({
  document,
  open,
  onOpenChange,
  isLoading,
}: DocumentDetailDialogProps): React.JSX.Element {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">
            {document ? document.fileName : "Detalhes do Documento"}
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            Inspecione o conteúdo e metadados do documento.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {isLoading && (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              Carregando detalhes…
            </div>
          )}

          {!isLoading && document && (
            <>
              <section className="grid gap-4 rounded-lg border bg-muted/40 p-4 text-sm leading-relaxed">
                <div className="grid gap-2">
                  <p>
                    <span className="font-medium text-foreground">ID do Documento:</span>{" "}
                    <span className="text-muted-foreground">{document.id}</span>
                  </p>
                  <p>
                    <span className="font-medium text-foreground">Tipo:</span>{" "}
                    <span className="uppercase tracking-wide text-muted-foreground">
                      {document.fileType}
                    </span>
                  </p>
                  <p>
                    <span className="font-medium text-foreground">Enviado:</span>{" "}
                    <span className="text-muted-foreground">
                      {new Date(document.createdAt).toLocaleString()}
                    </span>
                  </p>
                  {document.updatedAt && (
                    <p>
                      <span className="font-medium text-foreground">Atualizado:</span>{" "}
                      <span className="text-muted-foreground">
                        {new Date(document.updatedAt).toLocaleString()}
                      </span>
                    </p>
                  )}
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-foreground">Total de chunks:</span>
                    <Badge variant="secondary">{document.chunkCount}</Badge>
                  </div>
                </div>
              </section>

              {showTechnicalDetails && (
                <section className="space-y-2">
                  <h3 className="text-sm font-semibold uppercase text-muted-foreground">
                    Metadados do Documento
                  </h3>
                  {renderMetadata(document.metadata)}
                </section>
              )}

              <section className="space-y-3">
                <h3 className="text-sm font-semibold uppercase text-muted-foreground">
                  {showTechnicalDetails ? "Detalhamento de Chunks" : "Conteúdo do Documento"}
                </h3>

                <div className="max-h-[480px] space-y-3 overflow-y-auto pr-2">
                  {document.chunks.map((chunk) => (
                    <article
                      key={chunk.id}
                      className="rounded-lg border bg-background p-3 shadow-sm transition hover:border-primary/40"
                    >
                      <div className="flex items-center justify-between mb-3 pb-3 border-b border-border">
                        <h4 className="text-sm font-semibold text-primary">
                          Chunk {chunk.chunkIndex + 1}
                        </h4>
                        {showTechnicalDetails && (
                          <div className="flex gap-2">
                            {chunk.category && (
                              <Badge variant="secondary" className="text-xs">
                                {chunk.category}
                              </Badge>
                            )}
                            <Badge variant="outline" className="text-xs">
                              ID: {chunk.id.toString().slice(0, 8)}
                            </Badge>
                          </div>
                        )}
                      </div>

                      <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                        {chunk.content}
                      </p>

                      {showTechnicalDetails && (chunk.keywords || chunk.possibleQuestions) && (
                        <div className="mt-4 pt-3 border-t border-border grid gap-3 text-xs">
                          {chunk.keywords && (
                            <div className="rounded-md bg-muted/50 p-2">
                              <span className="font-semibold text-foreground">
                                Palavras-chave:
                              </span>{" "}
                              <span className="text-muted-foreground">{chunk.keywords}</span>
                            </div>
                          )}
                          {chunk.possibleQuestions && chunk.possibleQuestions.length > 0 && (
                            <div className="rounded-md bg-muted/50 p-2">
                              <p className="font-semibold text-foreground mb-2">
                                Perguntas possíveis:
                              </p>
                              <ul className="mt-1 list-disc space-y-1 pl-5">
                                {chunk.possibleQuestions.map((question) => (
                                  <li key={question}>{question}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}
                    </article>
                  ))}
                </div>
              </section>
            </>
          )}

          {!isLoading && !document && (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              Selecione um documento para inspecionar seu conteúdo.
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default DocumentDetailDialog;
