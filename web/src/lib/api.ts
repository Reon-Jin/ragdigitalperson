import type {
  AgentMemory,
  AnalysisMode,
  AuthResponse,
  ConversationSession,
  ConversationSummary,
  DashboardOverview,
  DocumentDetail,
  HealthPayload,
  LibraryFileItem,
  LocalAvatarProfile,
  ModelItem,
  SecurityPayload,
  SessionResponse,
  StreamEvent,
  UploadResponse,
  UserProfile,
} from "../types";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseJson<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : "请求失败";
    throw new ApiError(detail, response.status);
  }
  return data as T;
}

async function fetchAndParse<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  return parseJson<T>(response);
}

export function createApi(getToken: () => string, onUnauthorized: () => void) {
  const request = async <T>(input: RequestInfo | URL, init: RequestInit = {}): Promise<T> => {
    const headers = new Headers(init.headers || {});
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(input, { ...init, headers });
    if (response.status === 401) {
      onUnauthorized();
      throw new ApiError("请先登录", 401);
    }
    return parseJson<T>(response);
  };

  return {
    request,
    session: (): Promise<SessionResponse> => request<SessionResponse>("/api/v2/auth/session"),
    login: (username: string, password: string): Promise<AuthResponse> =>
      fetchAndParse<AuthResponse>("/api/v2/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      }),
    register: (username: string, password: string, displayName?: string): Promise<AuthResponse> =>
      fetchAndParse<AuthResponse>("/api/v2/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, display_name: displayName || null }),
      }),
    logout: (): Promise<{ ok: boolean }> => request<{ ok: boolean }>("/api/v2/auth/logout", { method: "POST" }),
    models: (): Promise<ModelItem[]> => fetchAndParse<ModelItem[]>("/api/models"),
    profile: (): Promise<UserProfile> => request<UserProfile>("/api/v2/profile"),
    saveProfile: (payload: UserProfile): Promise<UserProfile> =>
      request<UserProfile>("/api/v2/profile", { method: "PUT", body: JSON.stringify(payload) }),
    avatarProfile: (): Promise<LocalAvatarProfile> => request<LocalAvatarProfile>("/api/v2/avatar/profile"),
    saveAvatarProfile: (payload: LocalAvatarProfile): Promise<LocalAvatarProfile> =>
      request<LocalAvatarProfile>("/api/v2/avatar/profile", { method: "PUT", body: JSON.stringify(payload) }),
    dashboard: (): Promise<DashboardOverview> => request<DashboardOverview>("/api/v2/dashboard/overview"),
    health: (): Promise<HealthPayload> => request<HealthPayload>("/api/v2/health/market"),
    files: (): Promise<LibraryFileItem[]> => request<LibraryFileItem[]>("/api/files"),
    getLibraryDocument: (docId: string): Promise<DocumentDetail> =>
      request<DocumentDetail>(`/api/library/${encodeURIComponent(docId)}`),
    deleteLibraryDocument: (docId: string): Promise<{ deleted: boolean; doc_id: string }> =>
      request<{ deleted: boolean; doc_id: string }>(`/api/library/${encodeURIComponent(docId)}`, { method: "DELETE" }),
    upload: (body: FormData): Promise<UploadResponse> => request<UploadResponse>("/api/upload", { method: "POST", body }),
    memory: (): Promise<AgentMemory> => request<AgentMemory>("/api/v2/agent/memory"),
    recordEvent: (eventType: string, summary: string, metadata: Record<string, unknown> = {}): Promise<AgentMemory> =>
      request<AgentMemory>("/api/v2/agent/events", {
        method: "POST",
        body: JSON.stringify({ event_type: eventType, summary, metadata }),
      }),
    conversations: (): Promise<ConversationSummary[]> => request<ConversationSummary[]>("/api/v2/conversations"),
    createConversation: (title?: string): Promise<ConversationSession> =>
      request<ConversationSession>("/api/v2/conversations", {
        method: "POST",
        body: JSON.stringify({ title: title || null }),
      }),
    getConversation: (conversationId: string): Promise<ConversationSession> =>
      request<ConversationSession>(`/api/v2/conversations/${encodeURIComponent(conversationId)}`),
    deleteConversation: (conversationId: string): Promise<{ deleted: boolean }> =>
      request<{ deleted: boolean }>(`/api/v2/conversations/${encodeURIComponent(conversationId)}`, { method: "DELETE" }),
    queryStock: (query: string): Promise<SecurityPayload> =>
      request<SecurityPayload>(`/api/v2/stocks/query?query=${encodeURIComponent(query)}`),
    streamCopilot: async (
      payload: {
        message: string;
        task_type: string;
        analysis_mode: AnalysisMode;
        model_provider: string;
        conversation_id: string;
        history: Array<{ role: string; content: string }>;
        context_hint: Record<string, unknown>;
      },
      signal: AbortSignal,
      onEvent: (event: StreamEvent) => void,
    ): Promise<void> => {
      const headers = new Headers({ "Content-Type": "application/json" });
      const token = getToken();
      if (token) headers.set("Authorization", `Bearer ${token}`);
      const response = await fetch("/api/v2/copilot/stream", {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        signal,
      });
      if (response.status === 401) {
        onUnauthorized();
        throw new ApiError("请先登录", 401);
      }
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new ApiError(typeof data?.detail === "string" ? data.detail : "流式响应不可用", response.status);
      }
      if (!response.body) {
        throw new ApiError("流式响应不可用", response.status);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";
        chunks.forEach((chunk) => {
          const line = chunk
            .split("\n")
            .find((item) => item.startsWith("data: "));
          if (!line) return;
          try {
            onEvent(JSON.parse(line.slice(6)) as StreamEvent);
          } catch {
            // ignore malformed SSE chunks
          }
        });
      }
    },
  };
}
