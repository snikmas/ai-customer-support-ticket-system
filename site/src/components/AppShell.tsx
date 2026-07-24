import {
  AlertTriangle,
  Bell,
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
import { useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { initials, roleLabel } from "../lib/format";
import { UnsupportedButton } from "./UnsupportedButton";

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const isTicketList = location.pathname === "/tickets";
  const isOverdue = new URLSearchParams(location.search).get("overdue") === "true";

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
          <UnsupportedButton feature="My tickets" className="nav-action">
            <Layers size={17} /> My tickets
          </UnsupportedButton>
          <Link
            to="/tickets?overdue=true"
            className={isTicketList && isOverdue ? "active" : undefined}
            onClick={close}
          >
            <AlertTriangle size={17} /> Overdue
          </Link>
          <div className="nav-divider" />
          <UnsupportedButton feature="User management" className="nav-action">
            <Users size={17} /> Users
          </UnsupportedButton>
          <UnsupportedButton feature="Department management" className="nav-action">
            <Building2 size={17} /> Departments
          </UnsupportedButton>
          <UnsupportedButton feature="Settings" className="nav-action">
            <Settings size={17} /> Settings
          </UnsupportedButton>
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
          <UnsupportedButton feature="Ticket search" className="search-placeholder">
            <Search size={16} />
            <span>Search tickets...</span>
          </UnsupportedButton>
          <div className="top-actions">
            <UnsupportedButton feature="Notifications" className="icon-button" aria-label="Notifications">
              <Bell size={19} />
            </UnsupportedButton>
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
