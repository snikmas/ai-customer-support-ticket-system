import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { apiRequest } from "../api/client";
import type { SessionIdentity, Tokens, User } from "../api/types";
import { clearTokens, readIdentity, readTokens, writeTokens } from "./session";

interface AuthContextValue {
  identity: SessionIdentity | null;
  user: User | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<SessionIdentity | null>(() => {
    const tokens = readTokens();
    return tokens ? readIdentity(tokens.access_token) : null;
  });
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(identity));

  const reset = useCallback(() => {
    clearTokens();
    setIdentity(null);
    setUser(null);
    setLoading(false);
  }, []);

  useEffect(() => {
    const onExpired = () => reset();
    window.addEventListener("resolveai:session-expired", onExpired);
    return () => window.removeEventListener("resolveai:session-expired", onExpired);
  }, [reset]);

  useEffect(() => {
    if (!identity) {
      setUser(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    apiRequest<User>(`/users/${identity.userId}`)
      .then(setUser)
      .catch(reset)
      .finally(() => setLoading(false));
  }, [identity, reset]);

  const login = useCallback(async (identifier: string, password: string) => {
    const key = identifier.includes("@") ? "email" : "nickname";
    const tokens = await apiRequest<Tokens>("/auth/login", {
      method: "POST",
      authenticated: false,
      body: { [key]: identifier.trim(), password },
    });
    const nextIdentity = readIdentity(tokens.access_token);
    if (!nextIdentity) throw new Error("The API returned an invalid access token");
    writeTokens(tokens);
    setIdentity(nextIdentity);
  }, []);

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
    () => ({ identity, user, loading, login, logout }),
    [identity, user, loading, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
