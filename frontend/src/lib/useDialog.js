import { useEffect, useRef } from "react";

/**
 * Modal behaviour for a portalled dialog (drawer, alarm): while `open`, everything else in <body> is `inert`,
 * the page does not scroll, focus moves to [data-autofocus] (or the dialog, give it tabIndex={-1}), and Escape
 * calls onEscape. Cleanup undoes exactly what it changed, so dialogs can nest; only the topmost one hears Escape.
 */
export function useDialog(ref, open, onEscape) {
  const escape = useRef(onEscape);
  useEffect(() => { escape.current = onEscape; });

  useEffect(() => {
    const node = ref.current;
    if (!open || !node) return undefined;
    const previous = document.activeElement;
    const inerted = [...document.body.children].filter((el) => !el.contains(node) && !el.inert);
    inerted.forEach((el) => { el.inert = true; });
    const html = document.documentElement;
    const overflow = html.style.overflow;
    html.style.overflow = "hidden";
    (node.querySelector("[data-autofocus]") ?? node).focus();
    const onKey = (event) => {
      if (event.key === "Escape" && !node.closest("[inert]")) escape.current?.(event);
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      inerted.forEach((el) => { el.inert = false; });
      html.style.overflow = overflow;
      (previous?.isConnected ? previous : document.getElementById("main"))?.focus();
    };
  }, [ref, open]);
}
