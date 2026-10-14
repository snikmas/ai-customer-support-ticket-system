import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "../auth/AuthContext";
import type { Visibility } from "../api/types";

export interface TicketDraft {
  body: string;
  visibility: Visibility;
  files: File[];
}

interface DraftContextValue {
  getDraft: (ticketId: string) => TicketDraft | undefined;
  saveDraft: (ticketId: string, draft: TicketDraft) => void;
  clearDraft: (ticketId: string) => void;
}

const DraftContext = createContext<DraftContextValue | null>(null);

/**
 * In-memory reply drafts keyed by ticket for the signed-in user.
 *
 * Drafts are intentionally not persisted: browser file selections cannot be
 * restored from serialized storage, and storing support-message text needs a
 * separate retention decision. The whole store resets whenever the signed-in
 * user changes, so one account never sees another account's draft.
 */
export function DraftProvider({ children }: { children: ReactNode }) {
  const { identity } = useAuth();
  const userId = identity?.userId ?? null;
  const [drafts, setDrafts] = useState<Record<string, TicketDraft>>({});

  useEffect(() => {
    setDrafts({});
  }, [userId]);

  const getDraft = useCallback((ticketId: string) => drafts[ticketId], [drafts]);
  const saveDraft = useCallback((ticketId: string, draft: TicketDraft) => {
    setDrafts((current) => ({ ...current, [ticketId]: draft }));
  }, []);
  const clearDraft = useCallback((ticketId: string) => {
    setDrafts((current) => {
      if (!(ticketId in current)) return current;
      const next = { ...current };
      delete next[ticketId];
      return next;
    });
  }, []);

  // A draft lives in this store, not in a mounted composer, so the warning must
  // follow the store: any authenticated page warns while unsent work exists.
  const hasDrafts = Object.keys(drafts).length > 0;
  useEffect(() => {
    if (!hasDrafts) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [hasDrafts]);

  const value = useMemo(
    () => ({ getDraft, saveDraft, clearDraft }),
    [getDraft, saveDraft, clearDraft],
  );
  return <DraftContext.Provider value={value}>{children}</DraftContext.Provider>;
}

export function useDrafts(): DraftContextValue {
  const value = useContext(DraftContext);
  if (!value) throw new Error("useDrafts must be used inside DraftProvider");
  return value;
}
