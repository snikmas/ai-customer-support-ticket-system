import {
  AlertTriangle,
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
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { initials, roleLabel } from "../lib/format";
import { NotificationBell } from "./NotificationBell";

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [search, setSearch] = useState("");
  const isTicketList = location.pathname === "/tickets";
  const isOverdue = new URLSearchParams(location.search).get("overdue") === "true";

  useEffect(() => {
    setSearch(new URLSearchParams(location.search).get("search") || "");
  }, [location.search]);

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const params = new URLSearchParams(location.search);
    if (search.trim()) params.set("search", search.trim());
    else params.delete("search");
    params.delete("page");
    navigate(`/tickets?${params.toString()}`);
  };

  const close = () => setMobileOpen(false);
  return (
    <div className="app-frame">
      <button
        className="mobile-menu"
        aria-label="Open navigation"
        onClick={() => setMobileOpen(true)}
      >
        <Menu />
      </button>
      {mobileOpen && <button className="nav-scrim" aria-label="Close navigation" onClick={close} />}
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
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
            className={isTicketList && !isOverdue ? "active" : undefined}
            onClick={close}
          >
            <Inbox size={17} /> All tickets
          </Link>
          {user?.role === "agent" && (
            <Link
              to="/tickets?assigned_to_me=true"
              className={isTicketList && new URLSearchParams(location.search).get("assigned_to_me") === "true" ? "active" : undefined}
              onClick={close}
            >
              <Layers size={17} /> My queue
            </Link>
          )}
          <Link
            to="/tickets?overdue=true"
            className={isTicketList && isOverdue ? "active" : undefined}
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
      <div className="app-main">
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
