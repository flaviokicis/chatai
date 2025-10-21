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
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">
            {document ? document.fileName : "Document details"}
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            Inspect document metadata, generated chunks, and semantic hints.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {isLoading && (
            <div className="flex h-32 items-center justify-center text-muted-foreground">
              Loading document details…
            </div>
          )}

          {!isLoading && document && (
            <>
              <section className="grid gap-4 rounded-lg border bg-muted/40 p-4 text-sm leading-relaxed">
                <div className="grid gap-2">
                  <p>
                    <span className="font-medium text-foreground">Document ID:</span>{" "}
                    <span className="text-muted-foreground">{document.id}</span>
                  </p>
                  <p>
                    <span className="font-medium text-foreground">File type:</span>{" "}
                    <span className="uppercase tracking-wide text-muted-foreground">
                      {document.fileType}
                    </span>
                  </p>
                  <p>
                    <span className="font-medium text-foreground">Uploaded:</span>{" "}
                    <span className="text-muted-foreground">
                      {new Date(document.createdAt).toLocaleString()}
                    </span>
                  </p>
                  {document.updatedAt && (
                    <p>
                      <span className="font-medium text-foreground">Updated:</span>{" "}
                      <span className="text-muted-foreground">
                        {new Date(document.updatedAt).toLocaleString()}
                      </span>
                    </p>
                  )}
                  <p>
                    <span className="font-medium text-foreground">Total chunks:</span>{" "}
                    <Badge variant="secondary">{document.chunkCount}</Badge>
                  </p>
                </div>
              </section>

              <section className="space-y-2">
                <h3 className="text-sm font-semibold uppercase text-muted-foreground">
                  Document metadata
                </h3>
                {renderMetadata(document.metadata)}
              </section>

              <section className="space-y-3">
                <h3 className="text-sm font-semibold uppercase text-muted-foreground">
                  Chunk breakdown
                </h3>

                <div className="max-h-[480px] space-y-3 overflow-y-auto pr-2">
                  {document.chunks.map((chunk) => (
                    <article
                      key={chunk.id}
                      className="rounded-lg border bg-background p-3 shadow-sm transition hover:border-primary/40"
                    >
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <Badge variant="outline">#{chunk.chunkIndex}</Badge>
                        {chunk.category && (
                          <Badge variant="secondary">{chunk.category}</Badge>
                        )}
                        <span>
                          Created{" "}
                          {chunk.createdAt
                            ? new Date(chunk.createdAt).toLocaleString()
                            : "—"}
                        </span>
                      </div>

                      <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                        {chunk.content}
                      </p>

                      {(chunk.keywords || chunk.possibleQuestions) && (
                        <div className="mt-3 grid gap-2 text-xs text-muted-foreground">
                          {chunk.keywords && (
                            <p>
                              <span className="font-medium text-foreground">
                                Keywords:
                              </span>{" "}
                              {chunk.keywords}
                            </p>
                          )}
                          {chunk.possibleQuestions && chunk.possibleQuestions.length > 0 && (
                            <div>
                              <p className="font-medium text-foreground">
                                Possible questions:
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
              Select a document to inspect its chunks.
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default DocumentDetailDialog;
