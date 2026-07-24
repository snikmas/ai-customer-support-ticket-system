import { AlertTriangle, Inbox, LoaderCircle, ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";

type Kind = "loading" | "empty" | "error" | "forbidden";

const icons = {
  loading: <LoaderCircle className="spin" size={25} />,
  empty: <Inbox size={25} />,
  error: <AlertTriangle size={25} />,
  forbidden: <ShieldAlert size={25} />,
};

export function StatePanel({
  kind,
  title,
  message,
  action,
}: {
  kind: Kind;
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <section className={`state-panel state-${kind}`} role={kind === "error" ? "alert" : "status"}>
      {icons[kind]}
      <h2>{title}</h2>
      <p>{message}</p>
      {action}
    </section>
  );
}
