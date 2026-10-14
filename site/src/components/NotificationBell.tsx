import { Bell, CheckCheck } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiRequest, toErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type { Notification } from "../api/types";

export function NotificationBell() {
  const { identity } = useAuth();
  const [count, setCount] = useState(0);
  const [items, setItems] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);

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

  // Listeners exist only while the popup is open, and nonmodal dismissal is
  // Escape or a click outside. No modal focus trap is needed for this popup.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onPointerDown = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [open]);

  const toggle = async () => {
    const nextOpen = !open;
    setOpen(nextOpen);
    if (nextOpen) {
      try { setItems(await apiRequest<Notification[]>("/notifications/?limit=10")); setError(""); }
      catch (caught) { setError(toErrorMessage(caught)); }
    }
  };

  const markRead = useCallback(async (id: string) => {
    try {
      await apiRequest(`/notifications/${id}`, { method: "PATCH", body: { read: true } });
      setItems((current) => current.map((item) => item.id === id ? { ...item, read_at: new Date().toISOString() } : item));
      setCount((current) => Math.max(0, current - 1));
    } catch (caught) {
      setError(toErrorMessage(caught));
    }
  }, []);

  const openNotification = (item: Notification) => {
    setOpen(false);
    // Mark read only once, on first open; a read item stays navigable.
    if (!item.read_at) void markRead(item.id);
  };

  const markAll = async () => {
    try { await apiRequest("/notifications/read-all", { method: "POST" }); setItems((current) => current.map((item) => ({ ...item, read_at: new Date().toISOString() }))); setCount(0); }
    catch (caught) { setError(toErrorMessage(caught)); }
  };

  return <div className="notification-wrap" ref={wrapRef}>
    <button className="icon-button notification-button" aria-label={`Notifications${count ? `, ${count} unread` : ""}`} aria-expanded={open} onClick={() => void toggle()}><Bell size={19} />{count > 0 && <span className="notification-count">{count > 99 ? "99+" : count}</span>}</button>
    {open && <section className="notification-popover" aria-label="Notifications"><header><strong>Notifications</strong><button onClick={() => void markAll()} disabled={!count}><CheckCheck size={15} /> Mark all read</button></header>{error && <p className="field-error">{error}</p>}{items.length === 0 ? <p className="muted">No notifications yet.</p> : <ul>{items.map((item) => <li className={item.read_at ? "read" : "unread"} key={item.id}>
      {item.ticket_id ? (
        <Link to={`/tickets/${item.ticket_id}`} onClick={() => openNotification(item)}>
          <strong>{item.message}</strong>
          <span>{item.read_at ? "Read" : "Unread"}</span>
        </Link>
      ) : (
        <div className="notification-static">
          <strong>{item.message}</strong>
          <span>{item.read_at ? "Read" : "Unread"}</span>
        </div>
      )}
    </li>)}</ul>}</section>}
  </div>;
}
