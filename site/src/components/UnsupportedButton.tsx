import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useToast } from "./ToastContext";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  feature: string;
  children: ReactNode;
}

export function UnsupportedButton({ feature, children, ...props }: Props) {
  const { notify } = useToast();
  return (
    <button
      {...props}
      onClick={() => notify(`${feature} is not supported yet.`)}
      type="button"
    >
      {children}
    </button>
  );
}
