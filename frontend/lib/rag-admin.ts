import { getApiUrl, getControllerUrl } from "@/lib/config";

export interface ControllerTenantSummary {
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

export interface DocumentSummary {
  id: string;
  fileName: string;
  fileType: string;
  fileSize?: number | null;
  createdAt: string;
  chunkCount: number;
}

export interface DocumentChunk {
  id: string;
  chunkIndex: number;
  content: string;
  category?: string | null;
  keywords?: string | null;
  possibleQuestions?: string[] | null;
  metadata?: Record<string, unknown> | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface DocumentDetail extends DocumentSummary {
  updatedAt?: string | null;
  metadata?: Record<string, unknown> | null;
  chunks: DocumentChunk[];
}

export interface DocumentUploadResult {
  success: boolean;
  message: string;
  documentId?: string | null;
  chunksCreated: number;
  totalWords: number;
  error?: string | null;
}

export interface DocumentDeleteResult {
  success: boolean;
  message: string;
}

export interface QueryHistoryItem {
  id: string;
  query: string;
  timestamp: string;
  resultCount: number;
  sufficient: boolean;
}

export interface QueryChunk {
  id: string;
  content: string;
  score: number;
  category?: string | null;
  keywords?: string | null;
  possibleQuestions?: string[] | null;
  metadata?: Record<string, unknown> | null;
  documentName?: string | null;
}

export interface QueryResult {
  success: boolean;
  noDocuments: boolean;
  context: string | null;
  judgeReasoning?: string | null;
  attempts: number;
  sufficient: boolean;
  chunks: QueryChunk[];
  error?: string | null;
  generatedAnswer?: string | null;
}

interface DocumentListResponse {
  documents: Array<{
    id: string;
    file_name: string;
    file_type: string;
    file_size?: number | null;
    created_at: string;
    chunk_count: number;
  }>;
  total_count: number;
}

interface DocumentDetailResponse {
  id: string;
  file_name: string;
  file_type: string;
  file_size?: number | null;
  created_at: string;
  updated_at?: string | null;
  metadata?: Record<string, unknown> | null;
  chunk_count: number;
  chunks: Array<{
    id: string;
    chunk_index: number;
    content: string;
    category?: string | null;
    keywords?: string | null;
    possible_questions?: string[] | null;
    metadata?: Record<string, unknown> | null;
    created_at?: string | null;
    updated_at?: string | null;
  }>;
}

interface DocumentUploadResponse {
  success: boolean;
  message: string;
  document_id?: string | null;
  chunks_created: number;
  total_words: number;
  error?: string | null;
}

interface DocumentDeleteResponse {
  success: boolean;
  message: string;
}

interface QueryResponse {
  success: boolean;
  no_documents: boolean;
  context: string | null;
  judge_reasoning?: string | null;
  attempts: number;
  sufficient: boolean;
  chunks: Array<{
    id: string;
    content: string;
    score: number;
    category?: string | null;
    keywords?: string | null;
    possible_questions?: string[] | null;
    metadata?: Record<string, unknown> | null;
    document_name?: string | null;
  }>;
  error?: string | null;
  generated_answer?: string | null;
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return {} as T;
  }

  const data = await response.json().catch(() => {
    throw new Error("Server returned an invalid response");
  });

  if (!response.ok) {
    const detail = (data as { detail?: string }).detail;
    const message = typeof detail === "string" ? detail : "Request failed";
    if (response.status === 401) {
      const error = new Error("unauthorized");
      (error as Error & { cause?: unknown }).cause = message;
      throw error;
    }
    throw new Error(message);
  }

  return data as T;
}

export async function fetchControllerTenants(): Promise<ControllerTenantSummary[]> {
  const response = await fetch(getControllerUrl("/tenants"), {
    credentials: "include",
  });
  return parseJsonOrThrow<ControllerTenantSummary[]>(response);
}

export async function fetchTenantDocuments(tenantId: string): Promise<DocumentSummary[]> {
  const response = await fetch(
    getApiUrl(`/api/tenants/${tenantId}/documents`),
    {
      credentials: "include",
    }
  );

  const data = await parseJsonOrThrow<DocumentListResponse>(response);
  return data.documents.map((doc) => ({
    id: doc.id,
    fileName: doc.file_name,
    fileType: doc.file_type,
    fileSize: doc.file_size ?? undefined,
    createdAt: doc.created_at,
    chunkCount: doc.chunk_count,
  }));
}

export async function fetchDocumentDetail(
  tenantId: string,
  documentId: string
): Promise<DocumentDetail> {
  const response = await fetch(
    getApiUrl(`/api/tenants/${tenantId}/documents/${documentId}`),
    {
      credentials: "include",
    }
  );

  const data = await parseJsonOrThrow<DocumentDetailResponse>(response);
  return {
    id: data.id,
    fileName: data.file_name,
    fileType: data.file_type,
    fileSize: data.file_size ?? undefined,
    createdAt: data.created_at,
    updatedAt: data.updated_at ?? undefined,
    metadata: data.metadata ?? undefined,
    chunkCount: data.chunk_count,
    chunks: data.chunks.map((chunk) => ({
      id: chunk.id,
      chunkIndex: chunk.chunk_index,
      content: chunk.content,
      category: chunk.category,
      keywords: chunk.keywords,
      possibleQuestions: chunk.possible_questions ?? undefined,
      metadata: chunk.metadata ?? undefined,
      createdAt: chunk.created_at ?? undefined,
      updatedAt: chunk.updated_at ?? undefined,
    })),
  };
}

export async function uploadTenantDocument(
  tenantId: string,
  file: File
): Promise<DocumentUploadResult> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(
    getApiUrl(`/api/tenants/${tenantId}/documents/upload`),
    {
      method: "POST",
      body: formData,
      credentials: "include",
    }
  );

  const data = await parseJsonOrThrow<DocumentUploadResponse>(response);
  return {
    success: data.success,
    message: data.message,
    documentId: data.document_id ?? undefined,
    chunksCreated: data.chunks_created,
    totalWords: data.total_words,
    error: data.error ?? undefined,
  };
}

export async function deleteTenantDocument(
  tenantId: string,
  documentId: string
): Promise<DocumentDeleteResult> {
  const response = await fetch(
    getApiUrl(`/api/tenants/${tenantId}/documents/${documentId}`),
    {
      method: "DELETE",
      credentials: "include",
    }
  );

  const data = await parseJsonOrThrow<DocumentDeleteResponse>(response);
  return {
    success: data.success,
    message: data.message,
  };
}

export async function clearTenantDocuments(tenantId: string): Promise<DocumentDeleteResult> {
  const response = await fetch(
    getApiUrl(`/api/tenants/${tenantId}/documents/clear`),
    {
      method: "DELETE",
      credentials: "include",
    }
  );

  const data = await parseJsonOrThrow<DocumentDeleteResponse>(response);
  return {
    success: data.success,
    message: data.message,
  };
}

export async function updateDocumentMetadata(
  tenantId: string,
  documentId: string,
  metadata: Record<string, unknown>
): Promise<DocumentDeleteResult> {
  const response = await fetch(
    getApiUrl(`/api/tenants/${tenantId}/documents/${documentId}/metadata`),
    {
      method: "PATCH",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ metadata }),
    }
  );

  const data = await parseJsonOrThrow<{ success: boolean; message: string }>(response);
  return {
    success: data.success,
    message: data.message,
  };
}

export async function executeTenantQuery(
  tenantId: string,
  query: string
): Promise<QueryResult> {
  const response = await fetch(
    getApiUrl(`/api/tenants/${tenantId}/documents/query`),
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
    }
  );

  const data = await parseJsonOrThrow<QueryResponse>(response);
  return {
    success: data.success,
    noDocuments: data.no_documents,
    context: data.context,
    judgeReasoning: data.judge_reasoning,
    attempts: data.attempts,
    sufficient: data.sufficient,
    error: data.error ?? undefined,
    generatedAnswer: data.generated_answer ?? undefined,
    chunks: data.chunks.map((chunk) => ({
      id: chunk.id,
      content: chunk.content,
      score: chunk.score,
      category: chunk.category,
      keywords: chunk.keywords,
      possibleQuestions: chunk.possible_questions ?? undefined,
      metadata: chunk.metadata ?? undefined,
      documentName: chunk.document_name ?? undefined,
    })),
  };
}
