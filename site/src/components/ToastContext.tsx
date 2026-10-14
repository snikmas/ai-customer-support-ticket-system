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
import { Info, X } from "lucide-react";
import { useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const DEFAULT_DURATION_MS = 5_000;

interface ToastOptions {
  /** Milliseconds before the message expires. Use 0 for a persistent message. */
  duration?: number;
  /**
   * Keep the message after a route change. Use this when the action navigates
   * to the screen that shows its result; otherwise the message is cleared as
   * soon as the visit moves on.
   */
  persistsOnNavigation?: boolean;
}

interface ToastContextValue {
  notify: (message: string, options?: ToastOptions) => void;
  clear: () => void;
  clearTransient: () => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const { identity } = useAuth();
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const persists = useRef(false);
  const userId = identity?.userId ?? null;

  const cancelTimer = useCallback(() => {
    if (timer.current !== undefined) {
      window.clearTimeout(timer.current);
      timer.current = undefined;
    }
  }, []);

  const clear = useCallback(() => {
    cancelTimer();
    setMessage(null);
  }, [cancelTimer]);

  const clearTransient = useCallback(() => {
    if (!persists.current) clear();
  }, [clear]);

  const notify = useCallback(
    (next: string, options?: ToastOptions) => {
      cancelTimer();
      persists.current = Boolean(options?.persistsOnNavigation);
      setMessage(next);
      const duration =
        options?.duration === undefined ? DEFAULT_DURATION_MS : options.duration;
      if (duration > 0) {
        timer.current = window.setTimeout(() => {
          timer.current = undefined;
          setMessage(null);
        }, duration);
      }
    },
    [cancelTimer],
  );

  // A toast describes one signed-in user's action. Never let account A's
  // message survive a sign-out or an account switch.
  useEffect(() => {
    cancelTimer();
    setMessage(null);
  }, [userId, cancelTimer]);

  useEffect(() => cancelTimer, [cancelTimer]);

  const value = useMemo(
    () => ({ notify, clear, clearTransient }),
    [notify, clear, clearTransient],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      {message && (
        <div className="toast" role="status">
          <Info size={18} aria-hidden />
          <span>{message}</span>
          <button aria-label="Dismiss notification" onClick={clear}>
            <X size={16} />
          </button>
        </div>
      )}
    </ToastContext.Provider>
  );
}

/**
 * Clears transient toasts when the route changes. Mount inside both the router
 * and the ToastProvider. Persistent messages (persistsOnNavigation) are kept.
 */
export function ToastNavigationScope() {
  const location = useLocation();
  const { clearTransient } = useToast();
  const previous = useRef(`${location.pathname}${location.search}`);
  useEffect(() => {
    const key = `${location.pathname}${location.search}`;
    if (previous.current !== key) {
      previous.current = key;
      clearTransient();
    }
  }, [location, clearTransient]);
  return null;
}

export function useToast(): ToastContextValue {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used inside ToastProvider");
  return value;
}
