import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { StatePanel } from "./components/StatePanel";
import { ToastProvider } from "./components/ToastContext";
import { CreateTicketPage } from "./pages/CreateTicketPage";
import { LoginPage } from "./pages/LoginPage";
import { TicketDetailPage } from "./pages/TicketDetailPage";
import { TicketListPage } from "./pages/TicketListPage";
import { UsersPage } from "./pages/UsersPage";
import { RoutingPage } from "./pages/RoutingPage";
import { SettingsPage } from "./pages/SettingsPage";

function ProtectedLayout() {
  const { identity, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return (
      <div className="center-page">
        <StatePanel kind="loading" title="Restoring your session" message="Checking your profile…" />
      </div>
    );
  }
  if (!identity) return <Navigate to="/login" replace state={{ from: location }} />;
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

export function App() {
  return (
    <ToastProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedLayout />}>
          <Route path="/tickets" element={<TicketListPage />} />
          <Route path="/tickets/new" element={<CreateTicketPage />} />
          <Route path="/tickets/:ticketId" element={<TicketDetailPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/routing" element={<RoutingPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/tickets" replace />} />
      </Routes>
    </ToastProvider>
  );
}
