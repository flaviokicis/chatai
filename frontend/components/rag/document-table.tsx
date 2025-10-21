"use client";

import { useMemo } from "react";
import { Eye, FileText, Trash2, Pencil } from "lucide-react";

import type { DocumentSummary } from "@/lib/rag-admin";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

interface DocumentTableProps {
  documents: DocumentSummary[];
  isLoading: boolean;
  onViewDocument: (documentId: string) => void;
  onEditMetadata?: (documentId: string) => void;
  onDeleteDocument: (documentId: string) => void;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function formatFileSize(bytes?: number | null): string {
  if (!bytes || bytes <= 0) {
    return "—";
  }

  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  return `${size.toFixed(size < 10 ? 1 : 0)} ${units[unitIndex]}`;
}

export function DocumentTable({
  documents,
  isLoading,
  onViewDocument,
  onEditMetadata,
  onDeleteDocument,
}: DocumentTableProps): React.JSX.Element {
  const totalChunks = useMemo(
    () => documents.reduce((acc, doc) => acc + doc.chunkCount, 0),
    [documents]
  );

  if (isLoading) {
    return (
      <div className="flex h-32 items-center justify-center text-muted-foreground">
        Carregando documentos…
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="flex h-32 flex-col items-center justify-center gap-2 rounded-md border border-dashed bg-muted/20 text-center text-sm text-muted-foreground">
        <FileText className="h-6 w-6 text-muted-foreground/70" />
        <span>Nenhum documento encontrado.</span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
        <span>
          <strong className="text-foreground">{documents.length}</strong>{" "}
          {documents.length === 1 ? "documento" : "documentos"}
        </span>
        <span aria-hidden="true" className="text-muted-foreground">
          •
        </span>
        <span>
          <strong className="text-foreground">{totalChunks}</strong> chunks no total
        </span>
      </div>

      <div className="overflow-hidden rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[220px]">Documento</TableHead>
              <TableHead>Enviado em</TableHead>
              <TableHead className="hidden md:table-cell">Chunks</TableHead>
              <TableHead className="hidden md:table-cell">Tipo</TableHead>
              <TableHead className="hidden lg:table-cell">Tamanho</TableHead>
              <TableHead className="w-[160px] text-right">Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {documents.map((doc) => (
              <TableRow key={doc.id}>
                <TableCell>
                  <div className="flex flex-col">
                    <span className="font-medium text-foreground">
                      {doc.fileName}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      ID: {doc.id}
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  <span className="text-sm text-foreground">
                    {formatDate(doc.createdAt)}
                  </span>
                </TableCell>
                <TableCell className="hidden md:table-cell">
                  <Badge variant="secondary">{doc.chunkCount}</Badge>
                </TableCell>
                <TableCell className="hidden md:table-cell uppercase tracking-wide text-muted-foreground">
                  {doc.fileType}
                </TableCell>
                <TableCell className="hidden lg:table-cell text-muted-foreground">
                  {formatFileSize(doc.fileSize)}
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => onViewDocument(doc.id)}
                      aria-label={`Ver chunks de ${doc.fileName}`}
                      title="Ver conteúdo e chunks"
                    >
                      <Eye className="h-4 w-4" />
                      <span className="ml-1.5 hidden sm:inline">Ver</span>
                    </Button>
                    {onEditMetadata && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onEditMetadata(doc.id)}
                        aria-label={`Editar metadados de ${doc.fileName}`}
                        title="Editar metadados"
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => onDeleteDocument(doc.id)}
                      aria-label={`Excluir ${doc.fileName}`}
                      title="Excluir documento"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

export default DocumentTable;
