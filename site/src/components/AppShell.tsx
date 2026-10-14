import {
  AlertTriangle,
  Cpu,
  Building2,
  Inbox,
  Layers,
  LogOut,
  Menu,
  Plus,
  Search,
  Settings,
  Users,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { initials, roleLabel } from "../lib/format";
import { NotificationBell } from "./NotificationBell";

const MOBILE_QUERY = "(max-width: 760px)";

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(query).matches
      : false,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(query);
    const update = () => setMatches(list.matches);
    update();
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, [query]);
  return matches;
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [search, setSearch] = useState("");
  const isMobile = useMediaQuery(MOBILE_QUERY);
  const isTicketList = location.pathname === "/tickets";
  const sidebarRef = useRef<HTMLElement>(null);
  const mainRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);

  // Collapse the three ticket-list destinations to exactly one active item.
  // Precedence: the Overdue destination, then My queue, then All tickets.
  const listParams = new URLSearchParams(location.search);
  const activeDestination = !isTicketList
    ? null
    : listParams.get("overdue") === "true"
      ? "overdue"
      : listParams.get("assigned_to_me") === "true"
        ? "queue"
        : "all";

  useEffect(() => {
    setSearch(new URLSearchParams(location.search).get("search") || "");
  }, [location.search]);

  // The closed mobile drawer must leave the tab order entirely; a transform and
  // aria-hidden alone keep its links focusable. Desktop keeps the sidebar live.
  useEffect(() => {
    const sidebar = sidebarRef.current;
    const main = mainRef.current;
    if (sidebar) {
      const hidden = isMobile && !mobileOpen;
      if (hidden) sidebar.setAttribute("inert", "");
      else sidebar.removeAttribute("inert");
      sidebar.setAttribute("aria-hidden", hidden ? "true" : "false");
    }
    if (main) {
      if (isMobile && mobileOpen) main.setAttribute("inert", "");
      else main.removeAttribute("inert");
    }
  }, [isMobile, mobileOpen]);

  // Move focus into the modal drawer on open so Escape/Tab act on it.
  useEffect(() => {
    if (!(isMobile && mobileOpen)) return;
    const sidebar = sidebarRef.current;
    const first = sidebar?.querySelector<HTMLElement>(
      'a[href], button:not([disabled])',
    );
    first?.focus();
  }, [isMobile, mobileOpen]);

  const close = useCallback(() => {
    setMobileOpen(false);
    menuRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!(isMobile && mobileOpen)) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== "Tab") return;
      const sidebar = sidebarRef.current;
      if (!sidebar) return;
      const focusable = Array.from(
        sidebar.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [close, isMobile, mobileOpen]);

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const params = new URLSearchParams(location.search);
    if (search.trim()) params.set("search", search.trim());
    else params.delete("search");
    params.delete("page");
    navigate(`/tickets?${params.toString()}`);
  };

  return (
    <div className="app-frame">
      <button
        ref={menuRef}
        className="mobile-menu"
        aria-label="Open navigation"
        onClick={() => setMobileOpen(true)}
      >
        <Menu />
      </button>
      {mobileOpen && <button className="nav-scrim" aria-label="Close navigation" onClick={close} />}
      <aside
        ref={sidebarRef}
        className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}
      >
        <div className="brand-row">
          <div className="brand-mark" />
          <strong>ResolveAI</strong>
          <button className="mobile-close" aria-label="Close navigation" onClick={close}>
            <X size={19} />
          </button>
        </div>
        <nav className="nav-list" aria-label="Main navigation">
          <Link
            to="/tickets"
            className={activeDestination === "all" ? "active" : undefined}
            aria-current={activeDestination === "all" ? "page" : undefined}
            onClick={close}
          >
            <Inbox size={17} /> All tickets
          </Link>
          {user?.role === "agent" && (
            <Link
              to="/tickets?assigned_to_me=true"
              className={activeDestination === "queue" ? "active" : undefined}
              aria-current={activeDestination === "queue" ? "page" : undefined}
              onClick={close}
            >
              <Layers size={17} /> My queue
            </Link>
          )}
          <Link
            to="/tickets?overdue=true"
            className={activeDestination === "overdue" ? "active" : undefined}
            aria-current={activeDestination === "overdue" ? "page" : undefined}
            onClick={close}
          >
            <AlertTriangle size={17} /> Overdue
          </Link>
          <div className="nav-divider" />
          {user && ["manager", "admin", "super_admin"].includes(user.role) && (
            <>
              <Link to="/users" className={location.pathname === "/users" ? "active" : undefined} onClick={close}>
                <Users size={17} /> Users
              </Link>
              <Link to="/routing" className={location.pathname === "/routing" ? "active" : undefined} onClick={close}>
                <Building2 size={17} /> Routing
              </Link>
            </>
          )}
          {user && ["admin", "super_admin"].includes(user.role) && (
            <Link to="/ai-settings" className={location.pathname === "/ai-settings" ? "active" : undefined} onClick={close}>
              <Cpu size={17} /> AI settings
            </Link>
          )}
          <Link to="/settings" className={location.pathname === "/settings" ? "active" : undefined} onClick={close}>
            <Settings size={17} /> My settings
          </Link>
        </nav>
        <div className="profile-block">
          <div className="avatar">{initials(user?.first_name, user?.last_name)}</div>
          <div>
            <strong>{user ? `${user.first_name} ${user.last_name}` : "Signed in"}</strong>
            <span>{user ? roleLabel(user.role) : ""}</span>
          </div>
          <button aria-label="Sign out" title="Sign out" onClick={() => void logout()}>
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <div className="app-main" ref={mainRef}>
        <header className="topbar">
          <form className="search-placeholder" role="search" onSubmit={submitSearch}>
            <Search size={16} />
            <input
              aria-label="Search tickets"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search tickets..."
            />
          </form>
          <div className="top-actions">
            <NotificationBell />
            <button className="button primary compact" onClick={() => navigate("/tickets/new")}>
              <Plus size={17} /> Create ticket
            </button>
          </div>
        </header>
        <main className="page">{children}</main>
      </div>
    </div>
  );
}
