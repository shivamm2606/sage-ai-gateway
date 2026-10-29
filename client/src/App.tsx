import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  getToken,
  setToken,
  type Conversation,
  type ModelList,
  type UsageSummary,
  type User,
} from "./api";
import AuthPage from "./components/AuthPage";
import { Logo } from "./components/Icons";
import ChatView from "./components/ChatView";
import Sidebar from "./components/Sidebar";

const MODEL_KEY = "sage_model";

export default function App() {
  const [token, setTokenState] = useState<string | null>(getToken());
  const [user, setUser] = useState<User | null>(null);
  const [models, setModels] = useState<ModelList>({ default: null, models: [] });
  const [model, setModel] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // bumped only when the user switches chats, so a new chat getting its id does not remount mid-stream
  const [chatKey, setChatKey] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);

  const refreshUsage = useCallback(() => {
    api.usage().then(setUsage, () => undefined);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setTokenState(null);
    setUser(null);
    setConversations([]);
    setActiveId(null);
  }, []);

  // any 401 means the token is gone or expired, send the user back to login
  const handleError = useCallback(
    (err: unknown): string => {
      if (err instanceof ApiError && err.status === 401) logout();
      return err instanceof Error ? err.message : "something went wrong";
    },
    [logout],
  );

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const [me, modelList, convs] = await Promise.all([
          api.me(),
          api.models(),
          api.listConversations(),
        ]);
        if (cancelled) return;
        setUser(me);
        setModels(modelList);
        setConversations(convs);
        refreshUsage();
        let saved: string | null = null;
        try {
          saved = localStorage.getItem(MODEL_KEY);
        } catch {
          saved = null;
        }
        const ids = modelList.models.map((m) => m.id);
        setModel(saved && ids.includes(saved) ? saved : modelList.default);
        setLoadError(null);
      } catch (err) {
        if (!cancelled) setLoadError(handleError(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, handleError, refreshUsage]);

  const chooseModel = (id: string) => {
    setModel(id);
    try {
      localStorage.setItem(MODEL_KEY, id);
    } catch {
      // ignore
    }
  };

  // keep the sidebar sorted with the most recently used chat on top
  const upsertConversation = useCallback((conv: Conversation) => {
    setConversations((prev) => [conv, ...prev.filter((c) => c.id !== conv.id)]);
  }, []);

  const renameConversation = async (id: number, title: string) => {
    try {
      const updated = await api.renameConversation(id, title);
      setConversations((prev) => prev.map((c) => (c.id === id ? updated : c)));
    } catch (err) {
      alert(handleError(err));
    }
  };

  const deleteConversation = async (id: number) => {
    try {
      await api.deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeId === id) {
        setActiveId(null);
        setChatKey((k) => k + 1);
      }
    } catch (err) {
      alert(handleError(err));
    }
  };

  if (!token) {
    return (
      <AuthPage
        onAuthed={(t) => {
          setToken(t);
          setTokenState(t);
        }}
      />
    );
  }

  if (!user) {
    return (
      <div className="center-screen">
        {loadError ? (
          <div className="card">
            <Logo size={36} />
            <h2>Can't reach the server</h2>
            <p className="muted">{loadError}</p>
            <div className="card-actions">
              <button className="btn-primary" onClick={() => window.location.reload()}>
                Try again
              </button>
              <button className="btn-ghost" onClick={logout}>
                Log out
              </button>
            </div>
          </div>
        ) : (
          <div className="boot">
            <Logo size={40} />
            <span className="spinner" />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="layout">
      <Sidebar
        open={sidebarOpen}
        user={user}
        usage={usage}
        conversations={conversations}
        activeId={activeId}
        onSelect={(id) => {
          if (id !== activeId) {
            setActiveId(id);
            setChatKey((k) => k + 1);
          }
          setSidebarOpen(false);
        }}
        onNew={() => {
          setActiveId(null);
          setChatKey((k) => k + 1);
          setSidebarOpen(false);
        }}
        onRename={renameConversation}
        onDelete={deleteConversation}
        onLogout={logout}
        onClose={() => setSidebarOpen(false)}
      />
      <ChatView
        key={chatKey}
        initialConversationId={activeId}
        models={models}
        model={model}
        onModelChange={chooseModel}
        onConversationCreated={(conv) => {
          upsertConversation(conv);
          setActiveId(conv.id);
        }}
        onConversationTouched={upsertConversation}
        onReplyFinished={refreshUsage}
        onError={handleError}
        onOpenSidebar={() => setSidebarOpen(true)}
      />
    </div>
  );
}
