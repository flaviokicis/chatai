"use client";

import {
  useCallback,
  useEffect,
  useState,
} from "react";
import {
  AlertTriangle,
  Loader2,
  RefreshCw,
  Trash2,
  Settings,
  ChevronDown,
  ChevronUp,
  FileText,
} from "lucide-react";

import {
  clearTenantDocuments,
  deleteTenantDocument,
  DocumentDetail,
  DocumentSummary,
  executeTenantQuery,
  fetchDocumentDetail,
  fetchTenantDocuments,
  QueryResult,
  uploadTenantDocument,
  updateDocumentMetadata,
  QueryHistoryItem,
} from "@/lib/rag-admin";
import { getOrInitDefaultTenantId } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DocumentTable } from "@/components/rag/document-table";
import { DocumentDetailDialog } from "@/components/rag/document-detail-dialog";
import { QueryTester } from "@/components/rag/query-tester";
import { StatsDashboard } from "@/components/rag/stats-dashboard";
import { EditMetadataDialog } from "@/components/rag/edit-metadata-dialog";
import { QueryHistory } from "@/components/rag/query-history";
import { UploadZone } from "@/components/rag/upload-zone";

export default function DocumentsPage(): React.JSX.Element {
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentDetails, setDocumentDetails] = useState<Record<string, DocumentDetail>>({});

  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null);

  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [clearDialogOpen, setClearDialogOpen] = useState(false);
  const [clearing, setClearing] = useState(false);

  const [editMetadataDialogOpen, setEditMetadataDialogOpen] = useState(false);
  const [editMetadataDocumentId, setEditMetadataDocumentId] = useState<string | null>(null);
  const [savingMetadata, setSavingMetadata] = useState(false);

  const [queryHistory, setQueryHistory] = useState<QueryHistoryItem[]>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('rag_query_history');
      if (saved) {
        try {
          return JSON.parse(saved);
        } catch {
          return [];
        }
      }
    }
    return [];
  });
  
  const [showAdvanced, setShowAdvanced] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('rag_advanced_mode');
      return saved === 'true';
    }
    return false;
  });

  const editMetadataDocument = editMetadataDocumentId ? documentDetails[editMetadataDocumentId] : null;

  const toggleAdvanced = useCallback(() => {
    setShowAdvanced(prev => {
      const newValue = !prev;
      if (typeof window !== 'undefined') {
        localStorage.setItem('rag_advanced_mode', String(newValue));
      }
      return newValue;
    });
  }, []);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('rag_query_history', JSON.stringify(queryHistory));
    }
  }, [queryHistory]);

  useEffect(() => {
    const loadTenantId = async () => {
      try {
        const id = await getOrInitDefaultTenantId();
        setTenantId(id);
      } catch (err) {
        console.error("Failed to get tenant ID:", err);
        setError("Não foi possível carregar o tenant. Por favor, faça login novamente.");
      }
    };
    loadTenantId();
  }, []);

  const loadDocuments = useCallback(
    async (tid: string) => {
      setDocumentsLoading(true);
      setError(null);
      try {
        const docs = await fetchTenantDocuments(tid);
        setDocuments(docs);
      } catch (err) {
        if (err instanceof Error && err.message === "unauthorized") {
          return;
        }
        setError(err instanceof Error ? err.message : "Falha ao carregar documentos.");
      } finally {
        setDocumentsLoading(false);
      }
    },
    []
  );

  const refreshDocuments = useCallback(async () => {
    if (!tenantId) return;
    await loadDocuments(tenantId);
  }, [loadDocuments, tenantId]);

  useEffect(() => {
    if (!tenantId) {
      setDocuments([]);
      setDocumentDetails({});
      setQueryResult(null);
      return;
    }
    setDocumentDetails({});
    setQueryResult(null);
    void loadDocuments(tenantId);
  }, [tenantId, loadDocuments]);

  const handleUpload = useCallback(async (file: File) => {
    if (!tenantId) {
      return {
        success: false,
        chunksCreated: 0,
        totalWords: 0,
        error: "Tenant ID não disponível",
      };
    }

    try {
      const response = await uploadTenantDocument(tenantId, file);
      return {
        success: response.success,
        chunksCreated: response.chunksCreated,
        totalWords: response.totalWords,
        error: response.error,
        message: response.message,
      };
    } catch (err) {
      return {
        success: false,
        chunksCreated: 0,
        totalWords: 0,
        error: err instanceof Error ? err.message : "Erro ao enviar o documento.",
      };
    }
  }, [tenantId]);

  const openDocumentDetail = useCallback(
    async (documentId: string) => {
      if (!tenantId) return;

      setActiveDocumentId(documentId);
      setDetailDialogOpen(true);
      if (documentDetails[documentId]) return;

      setDetailLoading(true);
      setError(null);
      try {
        const detail = await fetchDocumentDetail(tenantId, documentId);
        setDocumentDetails((prev) => ({
          ...prev,
          [documentId]: detail,
        }));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Falha ao carregar o documento.");
        setDetailDialogOpen(false);
      } finally {
        setDetailLoading(false);
      }
    },
    [documentDetails, tenantId]
  );

  const handleDetailDialogOpenChange = useCallback((open: boolean) => {
    setDetailDialogOpen(open);
    if (!open) {
      setActiveDocumentId(null);
    }
  }, []);

  const scheduleDeleteDocument = useCallback((documentId: string) => {
    setDeleteTargetId(documentId);
    setDeleteDialogOpen(true);
  }, []);

  const confirmDeleteDocument = useCallback(async () => {
    if (!tenantId || !deleteTargetId) return;

    setDeleting(true);
    setError(null);
    try {
      await deleteTenantDocument(tenantId, deleteTargetId);
      setDocumentDetails((prev) => {
        const next = { ...prev };
        delete next[deleteTargetId];
        return next;
      });
      if (activeDocumentId === deleteTargetId) {
        setDetailDialogOpen(false);
        setActiveDocumentId(null);
      }
      await refreshDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível excluir o documento.");
    } finally {
      setDeleting(false);
      setDeleteDialogOpen(false);
      setDeleteTargetId(null);
    }
  }, [activeDocumentId, deleteTargetId, refreshDocuments, tenantId]);

  const confirmClearDocuments = useCallback(async () => {
    if (!tenantId) return;

    setClearing(true);
    setError(null);
    try {
      await clearTenantDocuments(tenantId);
      setDocumentDetails({});
      setDetailDialogOpen(false);
      setActiveDocumentId(null);
      await refreshDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao limpar documentos.");
    } finally {
      setClearing(false);
      setClearDialogOpen(false);
    }
  }, [refreshDocuments, tenantId]);

  const handleQuery = useCallback(
    async (query: string) => {
      if (!tenantId) {
        setError("Tenant ID não disponível.");
        return;
      }

      setQueryLoading(true);
      setError(null);

      try {
        const result = await executeTenantQuery(tenantId, query);
        setQueryResult(result);

        setQueryHistory((prev) => [
          {
            id: `${Date.now()}-${Math.random()}`,
            query,
            timestamp: new Date().toISOString(),
            resultCount: result.chunks.length,
            sufficient: result.sufficient,
          },
          ...prev.slice(0, 19),
        ]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Erro ao consultar o RAG.");
      } finally {
        setQueryLoading(false);
      }
    },
    [tenantId]
  );

  const handleOpenEditMetadata = useCallback(
    async (documentId: string) => {
      if (!tenantId) return;

      setEditMetadataDocumentId(documentId);
      setEditMetadataDialogOpen(true);

      if (!documentDetails[documentId]) {
        try {
          const detail = await fetchDocumentDetail(tenantId, documentId);
          setDocumentDetails((prev) => ({
            ...prev,
            [documentId]: detail,
          }));
        } catch (err) {
          setError(err instanceof Error ? err.message : "Failed to load document.");
        }
      }
    },
    [tenantId, documentDetails]
  );

  const handleSaveMetadata = useCallback(
    async (documentId: string, metadata: Record<string, unknown>) => {
      if (!tenantId) return;

      setSavingMetadata(true);
      setError(null);

      try {
        await updateDocumentMetadata(tenantId, documentId, metadata);

        setDocumentDetails((prev) => ({
          ...prev,
          [documentId]: {
            ...prev[documentId],
            metadata,
          } as DocumentDetail,
        }));

        setEditMetadataDialogOpen(false);
        setEditMetadataDocumentId(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to update metadata.");
      } finally {
        setSavingMetadata(false);
      }
    },
    [tenantId]
  );

  const handleClearQueryHistory = useCallback(() => {
    setQueryHistory([]);
    if (typeof window !== 'undefined') {
      localStorage.removeItem('rag_query_history');
    }
  }, []);

  const activeDocument = activeDocumentId ? documentDetails[activeDocumentId] : undefined;
  const disableActions = !tenantId;

  if (!tenantId) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" />
          <p className="mt-4 text-muted-foreground">Carregando...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <h1 className="text-3xl font-bold tracking-tight">Base de Conhecimento</h1>
            <p className="text-muted-foreground">
              Adicione documentos para que sua IA responda com informações precisas do seu negócio.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={toggleAdvanced}
            className="gap-2"
          >
            <Settings className="h-4 w-4" />
            {showAdvanced ? "Modo Simples" : "Modo Avançado"}
            {showAdvanced ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {showAdvanced && <StatsDashboard documents={documents} isLoading={documentsLoading} />}

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Upload de Documentos</CardTitle>
                <p className="text-sm text-muted-foreground mt-1">
                  Arraste múltiplos arquivos ou clique para selecionar
                </p>
              </div>
              {showAdvanced && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void refreshDocuments()}
                  disabled={disableActions}
                >
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Atualizar
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <UploadZone
              onUpload={handleUpload}
              onUploadComplete={refreshDocuments}
              disabled={disableActions}
              maxFiles={10}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Seus Documentos</CardTitle>
            {showAdvanced && (
              <Button
                type="button"
                variant="destructive"
                size="sm"
                disabled={disableActions || documents.length === 0}
                onClick={() => setClearDialogOpen(true)}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Limpar tudo
              </Button>
            )}
          </CardHeader>
          <CardContent>
            {documents.length === 0 && !documentsLoading ? (
              <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
                <div className="rounded-full bg-primary/10 p-6 mb-4">
                  <FileText className="h-12 w-12 text-primary" />
                </div>
                <h3 className="text-lg font-semibold mb-2">Nenhum documento ainda</h3>
                <p className="text-sm text-muted-foreground max-w-md mb-6">
                  Comece fazendo upload de PDFs, documentos ou guias sobre seus produtos e serviços. 
                  Sua IA usará essas informações para dar respostas mais precisas aos seus clientes.
                </p>
              </div>
            ) : (
              <DocumentTable
                documents={documents}
                isLoading={documentsLoading}
                onViewDocument={(docId) => void openDocumentDetail(docId)}
                onEditMetadata={showAdvanced ? (docId) => void handleOpenEditMetadata(docId) : undefined}
                onDeleteDocument={scheduleDeleteDocument}
              />
            )}
          </CardContent>
        </Card>

        {showAdvanced && (
          <>
            <QueryTester
              disabled={disableActions}
              isLoading={queryLoading}
              onSubmit={handleQuery}
              result={queryResult}
            />

            <QueryHistory
              history={queryHistory}
              onRerunQuery={handleQuery}
              onClearHistory={handleClearQueryHistory}
            />
          </>
        )}
      </div>

      <DocumentDetailDialog
        document={activeDocument}
        open={detailDialogOpen}
        onOpenChange={handleDetailDialogOpenChange}
        isLoading={detailLoading}
        showTechnicalDetails={showAdvanced}
      />

      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Excluir documento</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Tem certeza que deseja excluir este documento? 
            <span className="block mt-2 font-medium text-foreground">
              Todos os {documents.find(d => d.id === deleteTargetId)?.chunkCount || 0} chunks associados serão permanentemente removidos.
            </span>
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button 
              variant="outline" 
              onClick={() => setDeleteDialogOpen(false)}
              disabled={deleting}
            >
              Cancelar
            </Button>
            <Button 
              variant="destructive" 
              onClick={() => void confirmDeleteDocument()}
              disabled={deleting}
            >
              {deleting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Excluindo...
                </>
              ) : (
                "Excluir"
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={clearDialogOpen} onOpenChange={setClearDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Limpar todos os documentos</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Esta ação removerá permanentemente:
            <span className="block mt-2 font-medium text-foreground">
              • {documents.length} {documents.length === 1 ? "documento" : "documentos"}
              <br />
              • {documents.reduce((acc, d) => acc + d.chunkCount, 0)} chunks
            </span>
            <span className="block mt-2 text-destructive font-medium">
              Esta ação não pode ser desfeita.
            </span>
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button 
              variant="outline" 
              onClick={() => setClearDialogOpen(false)}
              disabled={clearing}
            >
              Cancelar
            </Button>
            <Button 
              variant="destructive" 
              onClick={() => void confirmClearDocuments()}
              disabled={clearing}
            >
              {clearing ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Limpando...
                </>
              ) : (
                "Limpar tudo"
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <EditMetadataDialog
        documentId={editMetadataDocumentId ?? ""}
        documentName={editMetadataDocument?.fileName ?? ""}
        currentMetadata={editMetadataDocument?.metadata}
        open={editMetadataDialogOpen}
        onOpenChange={setEditMetadataDialogOpen}
        onSave={handleSaveMetadata}
        isSaving={savingMetadata}
      />
    </div>
  );
}

