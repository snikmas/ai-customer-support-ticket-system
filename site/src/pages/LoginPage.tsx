import { AlertCircle, Eye, EyeOff } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { API_BASE_URL, toErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { identity, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [health, setHealth] = useState<"checking" | "healthy" | "unavailable">("checking");

  useEffect(() => {
    fetch(`${API_BASE_URL}/health`)
      .then((response) => setHealth(response.ok ? "healthy" : "unavailable"))
      .catch(() => setHealth("unavailable"));
  }, []);

  if (identity) return <Navigate to="/tickets" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!identifier.trim() || !password) {
      setError("Email or nickname and password are required.");
      return;
    }
    setSubmitting(true);
    try {
      await login(identifier, password);
      const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;
      navigate(from || "/tickets", { replace: true });
    } catch (caught) {
      setError(toErrorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <div className="login-wrap">
        <div className="login-brand">
          <div className="brand-mark" />
          <strong>ResolveAI</strong>
        </div>
        <section className="login-card">
          <h1>Customer support, resolved.</h1>
          <p>Sign in to work with real ticket data.</p>
          {error && (
            <div className="alert error" role="alert">
              <AlertCircle size={17} />
              <span>{error}</span>
            </div>
          )}
          <form onSubmit={submit}>
            <label>
              Email or nickname
              <input
                autoComplete="username"
                autoFocus
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
              />
            </label>
            <label>
              Password
              <span className="password-field">
                <input
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <button
                  type="button"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  onClick={() => setShowPassword((value) => !value)}
                >
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </span>
            </label>
            <button className="button primary login-submit" disabled={submitting}>
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </section>
        <div className={`health-label health-${health}`}>
          <span />
          {health === "checking"
            ? "Checking API…"
            : health === "healthy"
              ? "API and dependencies operational"
              : "API or dependency unavailable"}
        </div>
      </div>
    </main>
  );
}
