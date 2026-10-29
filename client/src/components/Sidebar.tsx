import { useState } from "react";
import type { Conversation, UsageSummary, User } from "../api";
import { LogOut, Pencil, Plus, Trash, Wordmark, X } from "./Icons";

type Props = {
  open: boolean;
  user: User;
  usage: UsageSummary | null;
  conversations: Conversation[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onNew: () => void;
  onRename: (id: number, title: string) => void;
  onDelete: (id: number) => void;
  onLogout: () => void;
  onClose: () => void;
};

const compact = new Intl.NumberFormat(undefined, { notation: "compact" });

function groupByDate(conversations: Conversation[]): [string, Conversation[]][] {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const day = 86_400_000;
  const groups: Record<string, Conversation[]> = {};
  const order = ["Today", "Yesterday", "Previous 7 days", "Previous 30 days", "Older"];

  for (const c of conversations) {
    const t = new Date(c.updated_at).getTime();
    const label =
      t >= startOfToday.getTime()
        ? "Today"
        : t >= startOfToday.getTime() - day
          ? "Yesterday"
          : t >= startOfToday.getTime() - 7 * day
            ? "Previous 7 days"
            : t >= startOfToday.getTime() - 30 * day
              ? "Previous 30 days"
              : "Older";
    (groups[label] ??= []).push(c);
  }
  return order.filter((l) => groups[l]).map((l) => [l, groups[l]]);
}

function UsageLine({ usage }: { usage: UsageSummary }) {
  const tokenPct = usage.token_limit ? usage.total_tokens / usage.token_limit : 0;
  const requestPct = usage.request_limit ? usage.requests / usage.request_limit : 0;
  const pct = Math.min(1, Math.max(tokenPct, requestPct));
  const limited = Boolean(usage.token_limit || usage.request_limit);

  return (
    <div
      className="usage-line"
      title={`${usage.requests}${usage.request_limit ? ` / ${usage.request_limit}` : ""} requests today · resets 00:00 UTC`}
    >
      <div className="usage-text">
        <span>Usage today</span>
        <span>
          {compact.format(usage.total_tokens)}
          {usage.token_limit ? ` / ${compact.format(usage.token_limit)}` : ""}
        </span>
      </div>
      {limited && (
        <div className="usage-bar">
          <div className={pct >= 0.9 ? "danger" : ""} style={{ width: `${pct * 100}%` }} />
        </div>
      )}
    </div>
  );
}

export default function Sidebar(p: Props) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState("");

  const finishEdit = () => {
    const title = draft.trim();
    if (editingId !== null && title) p.onRename(editingId, title);
    setEditingId(null);
  };

  return (
    <>
      <div className={`backdrop ${p.open ? "show" : ""}`} onClick={p.onClose} />
      <aside className={`sidebar ${p.open ? "open" : ""}`}>
        <div className="sidebar-top">
          <Wordmark size={24} />
          <button className="icon-btn mobile-only" aria-label="Close menu" onClick={p.onClose}>
            <X />
          </button>
        </div>

        <button className="new-chat" onClick={p.onNew}>
          <Plus width={16} height={16} />
          New chat
        </button>

        <nav className="conv-list" aria-label="Conversations">
          {p.conversations.length === 0 && (
            <p className="conv-empty">Your conversations will show up here.</p>
          )}
          {groupByDate(p.conversations).map(([label, items]) => (
            <div key={label} className="conv-group">
              <div className="conv-label">{label}</div>
              {items.map((c) => (
                <div key={c.id} className={`conv ${c.id === p.activeId ? "active" : ""}`}>
                  {editingId === c.id ? (
                    <input
                      className="conv-edit"
                      autoFocus
                      value={draft}
                      maxLength={255}
                      onChange={(e) => setDraft(e.target.value)}
                      onBlur={finishEdit}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") finishEdit();
                        if (e.key === "Escape") setEditingId(null);
                      }}
                    />
                  ) : (
                    <>
                      <button
                        className="conv-title"
                        title={c.title}
                        onClick={() => p.onSelect(c.id)}
                      >
                        {c.title}
                      </button>
                      <div className="conv-actions">
                        <button
                          className="icon-btn sm"
                          aria-label="Rename chat"
                          onClick={() => {
                            setEditingId(c.id);
                            setDraft(c.title);
                          }}
                        >
                          <Pencil width={14} height={14} />
                        </button>
                        <button
                          className="icon-btn sm danger"
                          aria-label="Delete chat"
                          onClick={() => {
                            if (confirm(`Delete "${c.title}"? This can't be undone.`))
                              p.onDelete(c.id);
                          }}
                        >
                          <Trash width={14} height={14} />
                        </button>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          ))}
        </nav>

        {p.usage && <UsageLine usage={p.usage} />}

        <div className="user-row">
          <span className="avatar">{p.user.email[0]?.toUpperCase()}</span>
          <span className="user-email" title={p.user.email}>
            {p.user.email}
          </span>
          <button className="icon-btn" aria-label="Log out" title="Log out" onClick={p.onLogout}>
            <LogOut width={16} height={16} />
          </button>
        </div>
      </aside>
    </>
  );
}
