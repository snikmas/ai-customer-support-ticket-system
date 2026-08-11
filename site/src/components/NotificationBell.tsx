import { Bell, CheckCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest, toErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type { Notification } from "../api/types";

export function NotificationBell() {
  const { identity } = useAuth();
  const [count, setCount] = useState(0);
  const [items, setItems] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");

  const refreshCount = useCallback(async () => {
    if (!identity) return;
    try { setCount((await apiRequest<{ count: number }>("/notifications/unread-count")).count); }
    catch (caught) { setError(toErrorMessage(caught)); }
  }, [identity]);

  useEffect(() => {
    if (!identity) { setCount(0); setItems([]); setOpen(false); return; }
    void refreshCount();
    const timer = window.setInterval(() => void refreshCount(), 30_000);
    return () => window.clearInterval(timer);
  }, [identity, refreshCount]);

  const toggle = async () => {
    setOpen((current) => !current);
    if (!open) {
      try { setItems(await apiRequest<Notification[]>("/notifications/?limit=10")); setError(""); }
      catch (caught) { setError(toErrorMessage(caught)); }
    }
  };

  const markRead = async (id: string) => {
    try { await apiRequest(`/notifications/${id}`, { method: "PATCH", body: { read: true } }); setItems((current) => current.map((item) => item.id === id ? { ...item, read_at: new Date().toISOString() } : item)); setCount((current) => Math.max(0, current - 1)); }
    catch (caught) { setError(toErrorMessage(caught)); }
  };

  const markAll = async () => {
    try { await apiRequest("/notifications/read-all", { method: "POST" }); setItems((current) => current.map((item) => ({ ...item, read_at: new Date().toISOString() }))); setCount(0); }
    catch (caught) { setError(toErrorMessage(caught)); }
  };

  return <div className="notification-wrap">
    <button className="icon-button notification-button" aria-label={`Notifications${count ? `, ${count} unread` : ""}`} onClick={() => void toggle()}><Bell size={19} />{count > 0 && <span className="notification-count">{count > 99 ? "99+" : count}</span>}</button>
    {open && <div className="notification-popover" role="dialog" aria-label="Notifications"><header><strong>Notifications</strong><button onClick={() => void markAll()} disabled={!count}><CheckCheck size={15} /> Mark all read</button></header>{error && <p className="field-error">{error}</p>}{items.length === 0 ? <p className="muted">No notifications yet.</p> : <ul>{items.map((item) => <li className={item.read_at ? "read" : "unread"} key={item.id}><button onClick={() => void markRead(item.id)} disabled={Boolean(item.read_at)}><strong>{item.message}</strong><span>{item.read_at ? "Read" : "Unread"}</span></button></li>)}</ul>}</div>}
  </div>;
}
