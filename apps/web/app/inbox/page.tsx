"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { FlaskConical, Globe, Inbox as InboxIcon, LoaderCircle, MessageCircle, Search, UserRound } from "lucide-react";
import { PageHead } from "@/components/ui";
import { useToast } from "@/components/toast";
import { api, messageFrom } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Agent, Conversation, ConversationInbox } from "@/types";

const LIMIT = 30;

function formatWhen(iso: string): string {
  const date = new Date(iso);
  const sameDay = date.toDateString() === new Date().toDateString();
  return sameDay
    ? date.toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString("es", { day: "numeric", month: "short" });
}

export default function InboxPage() {
  const t = useT();
  const toast = useToast();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [items, setItems] = useState<ConversationInbox[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [agentId, setAgentId] = useState("");
  const [channel, setChannel] = useState("");
  const [tab, setTab] = useState<"all" | "unread" | "human" | "ai">("all");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api<Agent[]>("/agents").then(setAgents).catch(() => {}); }, []);
  useEffect(() => { const id = setTimeout(() => setSearch(searchInput), 300); return () => clearTimeout(id); }, [searchInput]);

  const channelLabel = (value: string) => {
    if (value === "playground") return t("inbox.channelPlayground");
    if (value === "whatsapp") return t("inbox.channelWhatsapp");
    if (value === "widget") return t("inbox.channelWidget");
    return value;
  };

  const channelIcon = (value: string) => {
    if (value === "whatsapp") return <MessageCircle size={10} />;
    if (value === "widget") return <Globe size={10} />;
    if (value === "playground") return <FlaskConical size={10} />;
    return <MessageCircle size={10} />;
  };

  const buildParams = useCallback((offsetValue: number) => {
    const params = new URLSearchParams();
    if (agentId) params.set("agent_id", agentId);
    if (channel) params.set("channel", channel);
    if (tab === "human" || tab === "ai") params.set("mode", tab);
    if (tab === "unread") params.set("unread", "1");
    if (search) params.set("search", search);
    params.set("limit", String(LIMIT));
    params.set("offset", String(offsetValue));
    return params.toString();
  }, [agentId, channel, tab, search]);

  const loadFirst = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await api<ConversationInbox[]>(`/conversations/inbox?${buildParams(0)}`);
      setItems(rows); setOffset(rows.length); setHasMore(rows.length === LIMIT);
    } catch (err) { toast.error(messageFrom(err)); } finally { setLoading(false); }
  }, [buildParams, toast]);

  useEffect(() => { loadFirst(); }, [loadFirst]);

  // Live refresh of the first page (skipped once the user scrolls into older pages).
  useEffect(() => {
    const id = setInterval(() => { if (offset <= LIMIT) loadFirst(); }, 12000);
    return () => clearInterval(id);
  }, [loadFirst, offset]);

  async function loadMore() {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const rows = await api<ConversationInbox[]>(`/conversations/inbox?${buildParams(offset)}`);
      setItems((prev) => [...prev, ...rows]); setOffset((o) => o + rows.length); setHasMore(rows.length === LIMIT);
    } catch (err) { toast.error(messageFrom(err)); } finally { setLoadingMore(false); }
  }

  function onScroll(event: React.UIEvent<HTMLElement>) {
    const el = event.currentTarget;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 80) loadMore();
  }

  async function choose(id: string) {
    setSelected(await api<Conversation>(`/conversations/${id}`));
    setItems((rows) => rows.map((row) => (row.id === id ? { ...row, unread: false } : row)));
    api(`/conversations/${id}/read`, { method: "POST" }).catch(() => {});
  }

  async function toggleMode(next: "ai" | "human") {
    if (!selected) return;
    setSelected(await api<Conversation>(`/conversations/${selected.id}/mode`, { method: "PATCH", body: JSON.stringify({ mode: next }) }));
    loadFirst();
  }

  const composerRef = useRef<HTMLInputElement>(null);
  async function reply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    try {
      setSelected(await api<Conversation>(`/conversations/${selected.id}/reply`, { method: "POST", body: JSON.stringify({ content: data.get("content") }) }));
      form.reset();
      loadFirst();
    } catch (err) { toast.error(messageFrom(err)); } finally { setBusy(false); composerRef.current?.focus(); }
  }

  return <div className="page">
    <PageHead eyebrow={t("inbox.eyebrow")} title={t("inbox.title")} description={t("inbox.description")} />

    <div className="toolbar filters">
      <div className="filter-select"><span>{t("inbox.filterAgent")}</span><select value={agentId} onChange={(e) => setAgentId(e.target.value)}><option value="">{t("inbox.allAgents")}</option>{agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></div>
      <div className="filter-select"><span>{t("inbox.filterChannel")}</span><select value={channel} onChange={(e) => setChannel(e.target.value)}><option value="">{t("inbox.allChannels")}</option><option value="playground">{t("inbox.channelPlayground")}</option><option value="whatsapp">{t("inbox.channelWhatsapp")}</option><option value="widget">{t("inbox.channelWidget")}</option></select></div>
    </div>

    <div className="inbox-layout">
      <aside className="inbox-list" onScroll={onScroll}>
        <div className="inbox-search"><Search size={16} /><input value={searchInput} onChange={(e) => setSearchInput(e.target.value)} placeholder={t("inbox.searchPlaceholder")} /></div>
        <div className="inbox-tabs">
          <button className={tab === "all" ? "active" : ""} onClick={() => setTab("all")}>{t("inbox.tabAll")}</button>
          <button className={tab === "unread" ? "active" : ""} onClick={() => setTab("unread")}>{t("inbox.tabUnread")}</button>
          <button className={tab === "human" ? "active" : ""} onClick={() => setTab("human")}>{t("inbox.statusHuman")}</button>
          <button className={tab === "ai" ? "active" : ""} onClick={() => setTab("ai")}>{t("inbox.statusAi")}</button>
        </div>
        {loading ? <div className="no-conversations"><LoaderCircle className="spin" size={16} /> {t("inbox.loading")}</div>
          : items.length ? <>
            {items.map((item) => (
              <button key={item.id} className={`inbox-row ${selected?.id === item.id ? "active" : ""} ${item.unread ? "unread" : ""}`} onClick={() => choose(item.id)}>
                <span className="inbox-avatar">
                  <span className="entity-avatar tiny"><UserRound size={15} /></span>
                  <span className={`channel-badge ${item.channel}`} title={channelLabel(item.channel)}>{channelIcon(item.channel)}</span>
                </span>
                <span className="inbox-row-body">
                  <span className="inbox-row-top"><strong>{item.contact_name || item.title}</strong><time>{formatWhen(item.updated_at)}</time></span>
                  <small className="inbox-row-preview">{item.preview || t("inbox.noMessages")}</small>
                  <small className="inbox-row-meta">{item.agent_name} · {channelLabel(item.channel)} <span className={`mini-badge ${item.mode}`}>{item.mode === "human" ? t("inbox.modeHuman") : t("inbox.modeAi")}</span></small>
                </span>
                {item.unread && <span className="inbox-unread-dot" />}
              </button>
            ))}
            {loadingMore && <div className="no-conversations"><LoaderCircle className="spin" size={15} /></div>}
          </> : <div className="no-conversations">{t("inbox.empty")}</div>}
      </aside>

      <section className="inbox-thread">
        {!selected ? <div className="empty-state"><div className="empty-icon"><InboxIcon /></div><h3>{t("inbox.empty")}</h3><p>{t("inbox.selectPrompt")}</p></div>
          : <>
            <header>
              <div><strong>{selected.contact_name || selected.title}</strong><small>{channelLabel(selected.channel)}</small></div>
              <button className={`mode-toggle ${selected.mode}`} onClick={() => toggleMode(selected.mode === "ai" ? "human" : "ai")}>{selected.mode === "ai" ? t("inbox.takeControl") : t("inbox.returnToAi")}</button>
            </header>
            <div className="inbox-messages">
              {selected.messages?.map((message) => (
                <div key={message.id} className={`inbox-message ${message.role}`}>
                  <small>{message.sender_name || (message.role === "assistant" ? t("inbox.senderAgent") : t("inbox.senderVisitor"))} · {formatWhen(message.created_at)}</small>
                  <p>{message.content}</p>
                </div>
              ))}
            </div>
            <form className="inbox-composer" onSubmit={reply}>
              <input ref={composerRef} name="content" placeholder={selected.mode === "human" ? t("inbox.composerHuman") : t("inbox.composerLocked")} disabled={selected.mode !== "human"} required />
              <button disabled={selected.mode !== "human" || busy}>{t("inbox.send")}</button>
            </form>
          </>}
      </section>
    </div>
  </div>;
}
