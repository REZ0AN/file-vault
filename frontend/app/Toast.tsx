"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Toast = { id: number; message: string; tone: "success" | "error" };

export function useToast(initialMessage = "") {
  const nextId = useRef(0);
  const [toast, setToast] = useState<Toast | null>(initialMessage
    ? { id: 0, message: initialMessage, tone: "error" } : null);

  const showToast = useCallback((message: string, tone: Toast["tone"] = "success") => {
    nextId.current += 1;
    setToast({ id: nextId.current, message, tone });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast((current) => current?.id === toast.id ? null : current), 5000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  return { toast, showToast, dismissToast: () => setToast(null) };
}

export function ToastViewport({ toast, onDismiss }: { toast: Toast | null; onDismiss: () => void }) {
  if (!toast) return null;
  return <div className={`toast toast-${toast.tone}`} role={toast.tone === "error" ? "alert" : "status"}
    aria-live={toast.tone === "error" ? "assertive" : "polite"}>
    <span className="toast-mark" aria-hidden="true">{toast.tone === "error" ? "!" : "✓"}</span>
    <span>{toast.message}</span>
    <button type="button" className="toast-close" onClick={onDismiss} aria-label="Dismiss notification">×</button>
  </div>;
}
