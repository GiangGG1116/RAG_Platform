export interface AppSettings {
  apiUrl: string;
  apiKey: string;
  tenantId: string;
  topK: number;
  rerank: boolean;
  stream: boolean;
}

export interface RetrievedChunk {
  chunk_id: string;
  document_id: string;
  document_title: string;
  content: string;
  score: number;
  metadata: Record<string, any>;
}

export interface Citation {
  document_id: string;
  document_title: string;
  chunk_id: string;
  relevance_score: number;
  excerpt: string;
}

export interface QueryResponse {
  query_id: string;
  question: string;
  answer: string;
  citations: Citation[];
  retrieved_chunks: RetrievedChunk[];
  model: string;
  latency_ms: number;
  conversation_id: string | null;
  created_at: string;
}

export interface DocumentInfo {
  id: string;
  title: string;
  doc_type: string;
  status: string;
  metadata: Record<string, any>;
  tenant_id: string;
  chunk_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentInfo[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// ── Conversation / Chat History ───────────────────────────────

export interface ChatMessageData {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  meta: Record<string, any>;
  position: number;
  created_at: string;
}

export interface ConversationData {
  id: string;
  tenant_id: string;
  title: string;
  memory_id: string | null;
  messages: ChatMessageData[];
  created_at: string;
  updated_at: string;
}

export interface ConversationSummary {
  id: string;
  tenant_id: string;
  title: string;
  memory_id: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  items: ConversationSummary[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}


/**
 * Fetch list of documents with pagination
 */
export async function listDocuments(
  settings: AppSettings,
  page = 1,
  pageSize = 20
): Promise<DocumentListResponse> {
  const url = new URL(`${settings.apiUrl}/api/v1/documents`);
  url.searchParams.append("page", page.toString());
  url.searchParams.append("page_size", pageSize.toString());
  url.searchParams.append("tenant_id", settings.tenantId);

  const response = await fetch(url.toString(), {
    headers: {
      "X-API-Key": settings.apiKey,
    },
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Failed to fetch documents (${response.status})`);
  }

  return response.json();
}

/**
 * Ingest a new document
 */
export async function createDocument(
  settings: AppSettings,
  title: string,
  content: string,
  docType = "text",
  metadata: Record<string, any> = {}
): Promise<DocumentInfo> {
  const response = await fetch(`${settings.apiUrl}/api/v1/documents`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": settings.apiKey,
    },
    body: JSON.stringify({
      title,
      content,
      doc_type: docType,
      metadata,
      tenant_id: settings.tenantId,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Failed to ingest document (${response.status})`);
  }

  return response.json();
}

/**
 * Delete an existing document
 */
export async function deleteDocument(settings: AppSettings, documentId: string): Promise<void> {
  const response = await fetch(`${settings.apiUrl}/api/v1/documents/${documentId}`, {
    method: "DELETE",
    headers: {
      "X-API-Key": settings.apiKey,
    },
  });

  if (!response.ok && response.status !== 404) {
    const errorText = await response.text();
    throw new Error(errorText || `Failed to delete document (${response.status})`);
  }
}

/**
 * Check the processing status of a document
 */
export async function getDocumentStatus(
  settings: AppSettings,
  documentId: string
): Promise<{ id: string; status: string; chunk_count: number; error_message: string | null }> {
  const response = await fetch(`${settings.apiUrl}/api/v1/documents/${documentId}/status`, {
    headers: {
      "X-API-Key": settings.apiKey,
    },
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Failed to check status (${response.status})`);
  }

  return response.json();
}

/**
 * Submit a blocking RAG query
 */
export async function queryRAG(
  settings: AppSettings,
  question: string,
  conversationId: string | null = null
): Promise<QueryResponse> {
  const response = await fetch(`${settings.apiUrl}/api/v1/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": settings.apiKey,
    },
    body: JSON.stringify({
      question,
      tenant_id: settings.tenantId,
      top_k: settings.topK,
      rerank: settings.rerank,
      stream: false,
      conversation_id: conversationId,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to execute query (${response.status})`);
  }

  return response.json();
}

/**
 * Submit a streaming RAG query via Server-Sent Events (SSE)
 */
export async function queryRAGStream(
  settings: AppSettings,
  question: string,
  conversationId: string | null = null,
  callbacks: {
    onStatus?: (statusText: string) => void;
    onToken?: (token: string) => void;
    onCitations?: (citations: Citation[]) => void;
    onDone?: (doneData: { query_id: string; model: string; latency_ms: number; conversation_id: string | null }) => void;
    onError?: (errorText: string) => void;
  }
): Promise<void> {
  const response = await fetch(`${settings.apiUrl}/api/v1/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": settings.apiKey,
    },
    body: JSON.stringify({
      question,
      tenant_id: settings.tenantId,
      top_k: settings.topK,
      rerank: settings.rerank,
      stream: true,
      conversation_id: conversationId,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Failed to execute query (${response.status})`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Response body is not readable.");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      // Keep the last incomplete line in buffer
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        if (trimmed.startsWith("event:")) {
          currentEvent = trimmed.substring(6).trim();
        } else if (trimmed.startsWith("data:")) {
          const dataStr = trimmed.substring(5).trim();
          try {
            const data = JSON.parse(dataStr);
            if (currentEvent === "status") {
              callbacks.onStatus?.(data.status || JSON.stringify(data));
            } else if (currentEvent === "chunk") {
              callbacks.onToken?.(data.token || "");
            } else if (currentEvent === "citations") {
              callbacks.onCitations?.(data);
            } else if (currentEvent === "done") {
              callbacks.onDone?.(data);
            } else if (currentEvent === "error") {
              callbacks.onError?.(data.detail || JSON.stringify(data));
            }
          } catch (e) {
            console.error("Failed to parse SSE data block:", dataStr, e);
          }
        }
      }
    }
  } catch (err: any) {
    callbacks.onError?.(err.message || "Stream read connection error.");
    throw err;
  }
}

// ── Conversation / Chat History API ──────────────────────────

function _headers(settings: AppSettings): Record<string, string> {
  return { "X-API-Key": settings.apiKey, "Content-Type": "application/json" };
}

/**
 * List conversations for a tenant (newest first)
 */
export async function listConversations(
  settings: AppSettings,
  page = 1,
  pageSize = 50
): Promise<ConversationListResponse> {
  const url = new URL(`${settings.apiUrl}/api/v1/conversations`);
  url.searchParams.set("tenant_id", settings.tenantId);
  url.searchParams.set("page", page.toString());
  url.searchParams.set("page_size", pageSize.toString());

  const res = await fetch(url.toString(), { headers: _headers(settings) });
  if (!res.ok) throw new Error(`listConversations: ${res.status}`);
  return res.json();
}

/**
 * Create a new conversation record in PostgreSQL
 */
export async function createConversation(
  settings: AppSettings,
  title: string,
  memoryId?: string | null
): Promise<ConversationData> {
  const res = await fetch(`${settings.apiUrl}/api/v1/conversations`, {
    method: "POST",
    headers: _headers(settings),
    body: JSON.stringify({ tenant_id: settings.tenantId, title, memory_id: memoryId ?? null }),
  });
  if (!res.ok) throw new Error(`createConversation: ${res.status}`);
  return res.json();
}

/**
 * Fetch a conversation with all its messages
 */
export async function getConversation(
  settings: AppSettings,
  conversationId: string
): Promise<ConversationData> {
  const res = await fetch(`${settings.apiUrl}/api/v1/conversations/${conversationId}`, {
    headers: _headers(settings),
  });
  if (res.status === 404) throw new Error("Conversation not found");
  if (!res.ok) throw new Error(`getConversation: ${res.status}`);
  return res.json();
}

/**
 * Rename a conversation or update its memory_id
 */
export async function updateConversation(
  settings: AppSettings,
  conversationId: string,
  patch: { title?: string; memory_id?: string | null }
): Promise<ConversationData> {
  const res = await fetch(`${settings.apiUrl}/api/v1/conversations/${conversationId}`, {
    method: "PATCH",
    headers: _headers(settings),
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`updateConversation: ${res.status}`);
  return res.json();
}

/**
 * Delete a conversation and all its messages
 */
export async function deleteConversationApi(
  settings: AppSettings,
  conversationId: string
): Promise<void> {
  const res = await fetch(`${settings.apiUrl}/api/v1/conversations/${conversationId}`, {
    method: "DELETE",
    headers: _headers(settings),
  });
  if (!res.ok && res.status !== 404) throw new Error(`deleteConversation: ${res.status}`);
}

/**
 * Append one or more messages to a conversation
 */
export async function addMessages(
  settings: AppSettings,
  conversationId: string,
  messages: Array<{ role: "user" | "assistant"; content: string; meta?: Record<string, any> }>
): Promise<ConversationData> {
  const res = await fetch(`${settings.apiUrl}/api/v1/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: _headers(settings),
    body: JSON.stringify({
      messages: messages.map((m) => ({ role: m.role, content: m.content, meta: m.meta ?? {} })),
    }),
  });
  if (!res.ok) throw new Error(`addMessages: ${res.status}`);
  return res.json();
}
