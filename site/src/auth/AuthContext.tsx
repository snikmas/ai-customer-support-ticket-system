import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { apiRequest, resetRefreshState } from "../api/client";
import type { SessionIdentity, Tokens, User } from "../api/types";
import {
  bumpSessionGeneration,
  clearTokens,
  readIdentity,
  readTokens,
  writeTokens,
} from "./session";

interface AuthContextValue {
  identity: SessionIdentity | null;
  user: User | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<SessionIdentity | null>(() => {
    const tokens = readTokens();
    return tokens ? readIdentity(tokens.access_token) : null;
  });
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(identity));
  // Monotonic guard for profile requests. Every identity change and every
  // explicit refresh bumps it, so a response that was started under an older
  // session is ignored instead of replacing the current user's profile or
  // signing them out with a stale failure.
  const profileRequestId = useRef(0);

  const reset = useCallback(() => {
    bumpSessionGeneration();
    resetRefreshState();
    clearTokens();
    setIdentity(null);
    setUser(null);
    setLoading(false);
  }, []);

  const loadProfile = useCallback(
    async (userId: string) => {
      const requestId = ++profileRequestId.current;
      try {
        const profile = await apiRequest<User>(`/users/${userId}`);
        if (requestId === profileRequestId.current) setUser(profile);
      } catch {
        // A stale failure for a superseded session must not sign out the
        // current one.
        if (requestId === profileRequestId.current) reset();
      } finally {
        if (requestId === profileRequestId.current) setLoading(false);
      }
    },
    [reset],
  );

  useEffect(() => {
    const onExpired = () => reset();
    const onRefreshed = () => {
      const tokens = readTokens();
      if (tokens) setIdentity(readIdentity(tokens.access_token));
    };
    window.addEventListener("resolveai:session-expired", onExpired);
    window.addEventListener("resolveai:session-refreshed", onRefreshed);
    return () => {
      window.removeEventListener("resolveai:session-expired", onExpired);
      window.removeEventListener("resolveai:session-refreshed", onRefreshed);
    };
  }, [reset]);

  useEffect(() => {
    // Invalidate any profile request still in flight for a previous identity
    // before starting the current one.
    profileRequestId.current += 1;
    if (!identity) {
      setUser(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    void loadProfile(identity.userId);
  }, [identity, loadProfile]);

  const login = useCallback(async (identifier: string, password: string) => {
    const key = identifier.includes("@") ? "email" : "nickname";
    const tokens = await apiRequest<Tokens>("/auth/login", {
      method: "POST",
      authenticated: false,
      body: { [key]: identifier.trim(), password },
    });
    const nextIdentity = readIdentity(tokens.access_token);
    if (!nextIdentity) throw new Error("The API returned an invalid access token");
    bumpSessionGeneration();
    resetRefreshState();
    writeTokens(tokens);
    setIdentity(nextIdentity);
  }, []);

  const refreshUser = useCallback(async () => {
    const tokens = readTokens();
    const nextIdentity = tokens ? readIdentity(tokens.access_token) : null;
    if (!nextIdentity) return;
    // Only replace identity when it actually changed, so an unchanged session
    // does not trigger a duplicate guarded load from the effect above.
    setIdentity((current) =>
      current &&
      current.userId === nextIdentity.userId &&
      current.role === nextIdentity.role
        ? current
        : nextIdentity,
    );
    await loadProfile(nextIdentity.userId);
  }, [loadProfile]);

  const logout = useCallback(async () => {
    const refreshToken = readTokens()?.refresh_token;
    try {
      if (refreshToken) {
        await apiRequest("/auth/logout", {
          method: "POST",
          authenticated: false,
          body: { refresh_token: refreshToken },
        });
      }
    } finally {
      reset();
    }
  }, [reset]);

  const value = useMemo(
    () => ({ identity, user, loading, login, logout, refreshUser }),
    [identity, user, loading, login, logout, refreshUser],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
