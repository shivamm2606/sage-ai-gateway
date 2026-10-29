const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";
const TOKEN_KEY = "sage_token";

export type User = { id: number; email: string; created_at: string };
export type Conversation = { id: number; title: string; created_at: string; updated_at: string };
export type MessageUsage = {
  requested_model: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  tokens_estimated: boolean;
  latency_ms: number;
  first_token_ms: number | null;
  routing_tier: string | null;
  routing_reason: string | null;
};
export type Message = {
  id: number;
  conversation_id: number;
  role: "user" | "assistant" | "system";
  content: string;
  model: string | null;
  status: "complete" | "cancelled" | "error";
  created_at: string;
  usage?: MessageUsage | null;
};
export type UsageSummary = {
  requests: number;
  total_tokens: number;
  request_limit: number | null;
  token_limit: number | null;
  requests_remaining: number | null;
  tokens_remaining: number | null;
};
export type Routing = { tier: string; score: number; reason: string };
export type ConversationDetail = Conversation & { messages: Message[] };
export type ModelList = { default: string | null; models: { id: string; provider: string }[] };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage unavailable, the session just won't survive a reload
  }
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

async function errorFrom(res: Response): Promise<ApiError> {
  let detail = res.statusText || "request failed";
  try {
    const body = await res.json();
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail) && body.detail[0]?.msg) detail = body.detail[0].msg;
  } catch {
    // body was not json
  }
  return new ApiError(res.status, detail);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { ...init, headers: headers() });
  if (!res.ok) throw await errorFrom(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  register: (email: string, password: string) =>
    request<User>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>("/auth/me"),
  models: () => request<ModelList>("/models"),
  usage: () => request<UsageSummary>("/usage"),
  listConversations: () => request<Conversation[]>("/conversations"),
  createConversation: () =>
    request<Conversation>("/conversations", { method: "POST", body: "{}" }),
  getConversation: (id: number) => request<ConversationDetail>(`/conversations/${id}`),
  renameConversation: (id: number, title: string) =>
    request<Conversation>(`/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  deleteConversation: (id: number) =>
    request<void>(`/conversations/${id}`, { method: "DELETE" }),
};

export type StreamHandlers = {
  onStart: (data: {
    user_message: Message;
    model: string;
    requested_model: string;
    routing: Routing | null;
    title: string;
  }) => void;
  onDelta: (text: string) => void;
  onDone: (message: Message) => void;
  onError: (detail: string, message?: Message) => void;
};

// POST a message and read the server-sent events coming back
export async function streamMessage(
  conversationId: number,
  content: string,
  model: string | null,
  signal: AbortSignal,
  h: StreamHandlers,
): Promise<void> {
  const res = await fetch(`${API_URL}/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ content, model }),
    signal,
  });
  if (!res.ok || !res.body) throw await errorFrom(res);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const handle = (block: string) => {
    let event = "message";
    let data = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) event = line.slice(7);
      else if (line.startsWith("data: ")) data += line.slice(6);
    }
    if (!data) return;
    const payload = JSON.parse(data);
    if (event === "start") h.onStart(payload);
    else if (event === "delta") h.onDelta(payload.text);
    else if (event === "done") h.onDone(payload.message);
    else if (event === "error") h.onError(payload.detail, payload.message);
  };

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      handle(buffer.slice(0, idx));
      buffer = buffer.slice(idx + 2);
    }
  }
  if (buffer.trim()) handle(buffer);
}
