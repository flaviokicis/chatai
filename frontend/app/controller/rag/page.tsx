"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Files,
  Loader2,
  LogOut,
  RefreshCw,
  ShieldCheck,
  Trash2,
  UploadCloud,
} from "lucide-react";

import {
  clearTenantDocuments,
  deleteTenantDocument,
  DocumentDetail,
  DocumentSummary,
  executeTenantQuery,
  fetchControllerTenants,
  fetchDocumentDetail,
  fetchTenantDocuments,
  QueryResult,
  uploadTenantDocument,
} from "@/lib/rag-admin";
import { getControllerUrl } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DocumentTable } from "@/components/rag/document-table";
import { DocumentDetailDialog } from "@/components/rag/document-detail-dialog";
import { QueryTester } from "@/components/rag/query-tester";

interface ControllerTenant {
  id: string;
  owner_first_name: string;
  owner_last_name: string;
  owner_email: string;
  created_at: string;
  updated_at: string;
  project_description?: string;
  target_audience?: string;
  communication_style?: string;
  channel_count: number;
  flow_count: number;
}

export default function RagAdminPage(): React.JSX.Element {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [tenants, setTenants] = useState<ControllerTenant[]>([]);
  const [tenantsLoading, setTenantsLoading] = useState(true);
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null);

  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentDetails, setDocumentDetails] = useState<Record<string, DocumentDetail>>({});

  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null);

  const [uploading, setUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);

  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);

  const [clearDialogOpen, setClearDialogOpen] = useState(false);

  const selectedTenant = useMemo(
    () => tenants.find((tenant) => tenant.id === selectedTenantId) ?? null,
    [selectedTenantId, tenants]
  );

  const loadTenants = useCallback(async () => {
    setTenantsLoading(true);
    setError(null);
    try {
      const data = await fetchControllerTenants();
      setTenants(data);
      setSelectedTenantId((prev) => {
        if (prev) {
          return prev;
        }
        return data.length > 0 ? data[0].id : null;
      });
    } catch (err) {
      if (err instanceof Error && err.message === "unauthorized") {
        router.push("/controller");
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to load tenants.");
    } finally {
      setTenantsLoading(false);
    }
  }, [router]);

  const loadDocuments = useCallback(
    async (tenantId: string) => {
      setDocumentsLoading(true);
      setError(null);
      try {
        const docs = await fetchTenantDocuments(tenantId);
        setDocuments(docs);
      } catch (err) {
        if (err instanceof Error && err.message === "unauthorized") {
          router.push("/controller");
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to load documents.");
      } finally {
        setDocumentsLoading(false);
      }
    },
    [router]
  );

  const refreshDocuments = useCallback(async () => {
    if (!selectedTenantId) {
      return;
    }
    await loadDocuments(selectedTenantId);
  }, [loadDocuments, selectedTenantId]);

  useEffect(() => {
    void loadTenants();
  }, [loadTenants]);

  useEffect(() => {
    if (!selectedTenantId) {
      setDocuments([]);
      setDocumentDetails({});
      setQueryResult(null);
      return;
    }
    setDocumentDetails({});
    setQueryResult(null);
    void loadDocuments(selectedTenantId);
  }, [selectedTenantId, loadDocuments]);

  const handleLogout = useCallback(async () => {
    try {
      await fetch(getControllerUrl("/logout"), {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // swallow errors to guarantee redirect
    } finally {
      router.push("/controller");
    }
  }, [router]);

  const handleTenantChange = useCallback((tenantId: string) => {
    setSelectedTenantId(tenantId);
  }, []);

  const handleFileChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    setSelectedFile(file ?? null);
    setUploadMessage(null);
  }, []);

  const handleUpload = useCallback(async () => {
    if (!selectedTenantId || !selectedFile) {
      setError("Selecione um tenant e um arquivo para continuar.");
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const response = await uploadTenantDocument(selectedTenantId, selectedFile);
      if (!response.success) {
        throw new Error(response.error ?? response.message);
      }

      setUploadMessage(
        `${response.message} (${response.chunksCreated} chunks, ${response.totalWords} palavras).`
      );
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      await refreshDocuments();
    } catch (err) {
      if (err instanceof Error && err.message === "unauthorized") {
        router.push("/controller");
        return;
      }
      setError(err instanceof Error ? err.message : "Erro ao enviar o documento.");
    } finally {
      setUploading(false);
    }
  }, [refreshDocuments, router, selectedFile, selectedTenantId]);

  const openDocumentDetail = useCallback(
    async (documentId: string) => {
      if (!selectedTenantId) {
        return;
      }

      setActiveDocumentId(documentId);
      setDetailDialogOpen(true);
      if (documentDetails[documentId]) {
        return;
      }

      setDetailLoading(true);
      setError(null);
      try {
        const detail = await fetchDocumentDetail(selectedTenantId, documentId);
        setDocumentDetails((prev) => ({
          ...prev,
          [documentId]: detail,
        }));
      } catch (err) {
        if (err instanceof Error && err.message === "unauthorized") {
          router.push("/controller");
          return;
        }
        setError(err instanceof Error ? err.message : "Falha ao carregar o documento.");
        setDetailDialogOpen(false);
      } finally {
        setDetailLoading(false);
      }
    },
    [documentDetails, router, selectedTenantId]
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
    if (!selectedTenantId || !deleteTargetId) {
      return;
    }

    setError(null);
    try {
      await deleteTenantDocument(selectedTenantId, deleteTargetId);
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
      if (err instanceof Error && err.message === "unauthorized") {
        router.push("/controller");
        return;
      }
      setError(err instanceof Error ? err.message : "Não foi possível excluir o documento.");
    } finally {
      setDeleteDialogOpen(false);
      setDeleteTargetId(null);
    }
  }, [activeDocumentId, deleteTargetId, refreshDocuments, router, selectedTenantId]);

  const confirmClearDocuments = useCallback(async () => {
    if (!selectedTenantId) {
      return;
    }

    setError(null);
    try {
      await clearTenantDocuments(selectedTenantId);
      setDocumentDetails({});
      setDetailDialogOpen(false);
      setActiveDocumentId(null);
      await refreshDocuments();
    } catch (err) {
      if (err instanceof Error && err.message === "unauthorized") {
        router.push("/controller");
        return;
      }
      setError(err instanceof Error ? err.message : "Falha ao limpar documentos.");
    } finally {
      setClearDialogOpen(false);
    }
  }, [refreshDocuments, router, selectedTenantId]);

  const handleQuery = useCallback(
    async (query: string) => {
      if (!selectedTenantId) {
        setError("Selecione um tenant para testar consultas.");
        return;
      }

      setQueryLoading(true);
      setError(null);

      try {
        const result = await executeTenantQuery(selectedTenantId, query);
        setQueryResult(result);
      } catch (err) {
        if (err instanceof Error && err.message === "unauthorized") {
          router.push("/controller");
          return;
        }
        setError(err instanceof Error ? err.message : "Erro ao consultar o RAG.");
      } finally {
        setQueryLoading(false);
      }
    },
    [router, selectedTenantId]
  );

  const activeDocument = activeDocumentId ? documentDetails[activeDocumentId] : undefined;

  const disableActions = tenantsLoading || !selectedTenantId;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">
              RAG Knowledge Base
            </h1>
            <p className="text-sm text-muted-foreground">
              Upload, inspecione e teste os documentos de cada tenant para garantir respostas impecáveis.
            </p>
          </div>
          <Button variant="outline" onClick={handleLogout}>
            <LogOut className="mr-2 h-4 w-4" />
            Sair
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        {error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {uploadMessage && (
          <Alert>
            <ShieldCheck className="h-4 w-4 text-primary" />
            <AlertDescription>{uploadMessage}</AlertDescription>
          </Alert>
        )}

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Files className="h-5 w-5 text-primary" />
              Seleção de Tenant
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div className="flex-1 space-y-2">
              <Label htmlFor="tenant-select">Tenant</Label>
              <Select
                value={selectedTenantId ?? undefined}
                onValueChange={handleTenantChange}
                disabled={tenantsLoading || tenants.length === 0}
              >
                <SelectTrigger id="tenant-select" className="w-full md:w-96">
                  <SelectValue placeholder={tenantsLoading ? "Carregando…" : "Selecione um tenant"} />
                </SelectTrigger>
                <SelectContent>
                  {tenants.map((tenant) => (
                    <SelectItem key={tenant.id} value={tenant.id}>
                      {tenant.owner_first_name} {tenant.owner_last_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedTenant && (
                <p className="text-xs text-muted-foreground">
                  {selectedTenant.project_description || "Sem descrição cadastrada."}
                </p>
              )}
            </div>

            <Button
              type="button"
              variant="outline"
              onClick={() => void refreshDocuments()}
              disabled={disableActions}
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              Atualizar documentos
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UploadCloud className="h-5 w-5 text-primary" />
              Upload de documento
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div className="flex-1 space-y-2">
              <Label htmlFor="document-upload">Arquivo</Label>
              <Input
                ref={fileInputRef}
                id="document-upload"
                type="file"
                accept=".pdf,.txt,.md,.json"
                disabled={disableActions || uploading}
                onChange={handleFileChange}
              />
              <p className="text-xs text-muted-foreground">
                Tipos suportados: PDF, TXT, Markdown e JSON (até 10MB).
              </p>
            </div>
            <Button
              type="button"
              onClick={() => void handleUpload()}
              disabled={disableActions || uploading || !selectedFile}
              className="md:w-64"
            >
              {uploading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Enviando…
                </>
              ) : (
                <>
              <UploadCloud className="mr-2 h-4 w-4" />
              Enviar documento
            </>
          )}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Files className="h-5 w-5 text-primary" />
              Documentos do tenant
            </CardTitle>
            <div className="flex flex-wrap items-center gap-2">
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
            </div>
          </CardHeader>
          <CardContent>
            <DocumentTable
              documents={documents}
              isLoading={documentsLoading || tenantsLoading}
              onViewDocument={(docId) => void openDocumentDetail(docId)}
              onDeleteDocument={scheduleDeleteDocument}
            />
          </CardContent>
        </Card>

        <QueryTester
          disabled={disableActions}
          isLoading={queryLoading}
          onSubmit={handleQuery}
          result={queryResult}
        />
      </main>

      <DocumentDetailDialog
        document={activeDocument}
        open={detailDialogOpen}
        onOpenChange={handleDetailDialogOpenChange}
        isLoading={detailLoading}
      />

      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Excluir documento</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Tem certeza que deseja excluir este documento? Todos os chunks associados serão removidos.
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={() => void confirmDeleteDocument()}>
              Excluir
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
            Esta ação removerá permanentemente todos os documentos e chunks deste tenant. Deseja continuar?
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setClearDialogOpen(false)}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={() => void confirmClearDocuments()}>
              Limpar tudo
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
