import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  api,
  streamMessage,
  type Conversation,
  type Message,
  type ModelList,
  type Routing,
} from "../api";
import { Alert, ArrowUp, Check, Chevron, Copy, Logo, Menu, Sparkles, Square, X } from "./Icons";
import Markdown, { useCopy } from "./Markdown";

type ViewMessage = Message & { pending?: boolean; routing?: Routing | null };

type Props = {
  initialConversationId: number | null;
  models: ModelList;
  model: string | null;
  onModelChange: (id: string) => void;
  onConversationCreated: (conv: Conversation) => void;
  onConversationTouched: (conv: Conversation) => void;
  onReplyFinished: () => void;
  onError: (err: unknown) => string;
  onOpenSidebar: () => void;
};

const TEMP_USER_ID = -2;
const TEMP_REPLY_ID = -1;

const SUGGESTIONS = [
  { title: "Explain a concept", prompt: "Explain how HTTPS keeps my data safe, in simple terms." },
  { title: "Debug some code", prompt: "Debug this step by step:\n```python\nnums = [1, 2, 3]\nprint(nums[3])\n```" },
  { title: "Plan something", prompt: "Make a 5-day study plan to learn the basics of SQL." },
  { title: "Write for me", prompt: "Write a short, friendly message asking my team for feedback on a project." },
];

function formatMs(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function MessageMeta({ m }: { m: ViewMessage }) {
  const [copied, copy] = useCopy();
  const u = m.usage;
  const routed = u?.requested_model === "auto" || Boolean(m.routing);
  const tier = u?.routing_tier ?? m.routing?.tier;
  const reason = u?.routing_reason ?? m.routing?.reason;

  return (
    <div className="meta">
      <span className="meta-model">{m.model}</span>
      {m.status === "cancelled" && <span className="warn">Stopped</span>}
      {m.status === "error" && <span className="error">Failed</span>}
      {/* details stay hidden until the reply is hovered, to keep the thread calm */}
      <span className="meta-extra">
        {routed && (
          <span className={`tag ${tier === "complex" ? "tag-strong" : ""}`} title={reason ?? undefined}>
            <Sparkles width={12} height={12} /> auto · {tier}
          </span>
        )}
        {u && (
          <>
            <span title={`${u.prompt_tokens} in · ${u.completion_tokens} out`}>
              {u.tokens_estimated ? "~" : ""}
              {u.total_tokens.toLocaleString()} tokens
            </span>
            <span
              title={
                u.first_token_ms != null ? `First token after ${formatMs(u.first_token_ms)}` : ""
              }
            >
              {formatMs(u.latency_ms)}
            </span>
          </>
        )}
        {m.content && (
          <button className="meta-btn" onClick={() => copy(m.content)} aria-label="Copy reply">
            {copied ? <Check width={14} height={14} /> : <Copy width={14} height={14} />}
          </button>
        )}
      </span>
    </div>
  );
}

function ModelPicker(p: {
  models: ModelList;
  value: string | null;
  disabled: boolean;
  onChange: (id: string) => void;
}) {
  const empty = p.models.models.length === 0;
  return (
    <label className="model-picker">
      {p.value === "auto" ? <Sparkles width={14} height={14} /> : <span className="dot" />}
      <select
        value={p.value ?? ""}
        disabled={empty || p.disabled}
        onChange={(e) => p.onChange(e.target.value)}
        aria-label="Model"
      >
        {empty && <option value="">No models</option>}
        {p.models.models.map((m) => (
          <option key={m.id} value={m.id}>
            {m.id === "auto"
              ? "Auto (smart routing)"
              : m.id === "sage-echo"
                ? "sage-echo (test)"
                : m.id}
          </option>
        ))}
      </select>
      <Chevron width={14} height={14} />
    </label>
  );
}

export default function ChatView(p: Props) {
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<ViewMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(p.initialConversationId !== null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { onError } = p;

  useEffect(() => {
    const id = p.initialConversationId;
    if (id === null) {
      inputRef.current?.focus();
      return;
    }
    let cancelled = false;
    api
      .getConversation(id)
      .then((detail) => {
        if (cancelled) return;
        const { messages: msgs, ...conv } = detail;
        setConversation(conv);
        setMessages(msgs);
      })
      .catch((err) => !cancelled && setError(onError(err)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // only load once, this component is remounted when the user switches chats
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // stop any running stream when leaving this chat
  useEffect(() => () => abortRef.current?.abort(), []);

  // follow new text, unless the user scrolled up to read something
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  // grow the textarea with its content
  useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [draft]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };

  const updateReply = (fn: (m: ViewMessage) => ViewMessage) =>
    setMessages((prev) => prev.map((m) => (m.id === TEMP_REPLY_ID ? fn(m) : m)));

  const send = async (text?: string) => {
    const content = (text ?? draft).trim();
    if (!content || streaming) return;
    setError(null);
    setStreaming(true);
    setDraft("");
    stickToBottom.current = true;

    const now = new Date().toISOString();
    const base = { conversation_id: conversation?.id ?? 0, created_at: now };
    setMessages((prev) => [
      ...prev,
      { ...base, id: TEMP_USER_ID, role: "user", content, model: null, status: "complete" },
      {
        ...base,
        id: TEMP_REPLY_ID,
        role: "assistant",
        content: "",
        model: p.model,
        status: "complete",
        pending: true,
      },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      let conv = conversation;
      if (!conv) {
        conv = await api.createConversation();
        setConversation(conv);
        p.onConversationCreated(conv);
      }
      const current = conv;

      await streamMessage(current.id, content, p.model, controller.signal, {
        onStart: ({ user_message, title, model, routing }) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === TEMP_USER_ID
                ? user_message
                : m.id === TEMP_REPLY_ID
                  ? { ...m, model, routing }
                  : m,
            ),
          );
          const touched = { ...current, title, updated_at: user_message.created_at };
          setConversation(touched);
          p.onConversationTouched(touched);
        },
        onDelta: (t) => updateReply((m) => ({ ...m, content: m.content + t })),
        onDone: (message) =>
          setMessages((prev) => prev.map((m) => (m.id === TEMP_REPLY_ID ? message : m))),
        onError: (detail, message) => {
          setError(detail);
          if (message)
            setMessages((prev) => prev.map((m) => (m.id === TEMP_REPLY_ID ? message : m)));
          else updateReply((m) => ({ ...m, pending: false, status: "error" }));
        },
      });
    } catch (err) {
      if (controller.signal.aborted) {
        updateReply((m) => ({ ...m, pending: false, status: "cancelled" }));
      } else {
        setError(onError(err));
        // nothing reached the server, drop the placeholders and give the text back
        setMessages((prev) => prev.filter((m) => m.id !== TEMP_REPLY_ID && m.id !== TEMP_USER_ID));
        setDraft(content);
      }
    } finally {
      // the server may have closed without a done event, never leave a spinner behind
      updateReply((m) => ({ ...m, pending: false }));
      abortRef.current = null;
      setStreaming(false);
      p.onReplyFinished();
      inputRef.current?.focus();
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void send();
    }
  };

  const noModels = p.models.models.length === 0;
  const isEmpty = !loading && messages.length === 0;

  return (
    <main className="chat">
      <header className="topbar">
        <button className="icon-btn mobile-only" aria-label="Open chats" onClick={p.onOpenSidebar}>
          <Menu />
        </button>
        <h1 className="topbar-title" title={conversation?.title}>
          {conversation?.title ?? "New chat"}
        </h1>
      </header>

      <div className="scroll" ref={scrollRef} onScroll={onScroll}>
        {loading && (
          <div className="thread">
            {[0, 1, 2].map((i) => (
              <div key={i} className={`skeleton ${i % 2 ? "right" : ""}`} />
            ))}
          </div>
        )}

        {isEmpty && (
          <div className="welcome">
            <h2>How can I help you today?</h2>
            <p className="muted">Pick a model below or let Auto choose for you.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((sg) => (
                <button
                  key={sg.title}
                  className="suggestion"
                  title={sg.prompt.split("\n")[0]}
                  disabled={noModels}
                  onClick={() => void send(sg.prompt)}
                >
                  {sg.title}
                </button>
              ))}
            </div>
          </div>
        )}

        {!loading && messages.length > 0 && (
          <div className="thread">
            {messages.map((m) =>
              m.role === "user" ? (
                <div key={m.id} className="msg user">
                  <div className="bubble">{m.content}</div>
                </div>
              ) : (
                <div key={m.id} className="msg assistant">
                  <div className="msg-avatar">
                    <Logo size={16} />
                  </div>
                  <div className="msg-body">
                    {m.content ? (
                      <Markdown text={m.content} />
                    ) : m.pending ? (
                      <span className="typing" aria-label="Thinking">
                        <i />
                        <i />
                        <i />
                      </span>
                    ) : (
                      <p className="muted">
                        <em>No reply.</em>
                      </p>
                    )}
                    {m.pending && m.content && <span className="caret" />}
                    {!m.pending && <MessageMeta m={m} />}
                  </div>
                </div>
              ),
            )}
          </div>
        )}
      </div>

      <div className="composer-wrap">
        {p.model === "sage-echo" && (
          <div className="notice" role="status">
            <Alert width={15} height={15} />
            <span>
              <strong>Test model.</strong> sage-echo doesn't use AI, it just repeats what you type.
              Pick another model for real answers.
            </span>
          </div>
        )}
        {error && (
          <div className="banner" role="alert">
            <Alert width={16} height={16} />
            <span>{error}</span>
            <button className="icon-btn sm" aria-label="Dismiss" onClick={() => setError(null)}>
              <X width={14} height={14} />
            </button>
          </div>
        )}
        <div className={`composer ${noModels ? "disabled" : ""}`}>
          <textarea
            ref={inputRef}
            rows={1}
            placeholder={noModels ? "No models configured on the server" : "Message Sage…"}
            value={draft}
            disabled={noModels}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <div className="composer-bar">
            <ModelPicker
              models={p.models}
              value={p.model}
              disabled={streaming}
              onChange={p.onModelChange}
            />
            <span className="hint">
              <kbd>Enter</kbd> to send
            </span>
            {streaming ? (
              <button
                className="send-btn stop"
                aria-label="Stop generating"
                onClick={() => abortRef.current?.abort()}
              >
                <Square width={16} height={16} />
              </button>
            ) : (
              <button
                className="send-btn"
                aria-label="Send message"
                onClick={() => void send()}
                disabled={!draft.trim() || noModels}
              >
                <ArrowUp />
              </button>
            )}
          </div>
        </div>
        <p className="disclaimer">Sage can make mistakes. Check important info.</p>
      </div>
    </main>
  );
}
