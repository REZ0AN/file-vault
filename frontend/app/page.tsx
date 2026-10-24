"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { ToastViewport, useToast } from "./Toast";

export default function Home() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const { toast, showToast, dismissToast } = useToast();

  useEffect(() => {
    const error = new URLSearchParams(window.location.search).get("error");
    api.me().then(() => { router.replace("/dashboard"); })
      .catch(() => { if (error) showToast(error, "error"); });
  }, [router, showToast]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      if (mode === "login") await api.login(email, password);
      else await api.register(email, password);
      router.replace("/dashboard");
    } catch (error) {
      showToast((error as Error).message, "error");
      setBusy(false);
    }
  }

  return <main className="shell auth-shell">
    <header className="auth-intro">
      <p className="eyebrow">FILE VAULT <span aria-hidden="true">/</span> PRIVATE WORKSPACE</p>
      <h1>YOUR FILES.<br /><span className="accent-text">YOUR RULES.</span></h1>
      <p>Keep your files together. Preview, download, or send a copy to your Google account when you need it.</p>
      <div className="hero-stamp" aria-hidden="true">PRIVATE BY DEFAULT <span>↗</span></div>
    </header>

    <section className="card auth-card">
      <div className="step">01 / ACCESS</div>
      <h2>{mode === "login" ? "Sign in" : "Create an account"}</h2>
      <form className="stack" onSubmit={submit}>
        <label htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <label htmlFor="password">Password</label>
        <input id="password" type="password" minLength={8} maxLength={128}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          value={password} onChange={(e) => setPassword(e.target.value)} required />
        <button disabled={busy}>{busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}</button>
      </form>
      <button className="text-button" type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "Need an account? Register" : "Already have an account? Sign in"}
      </button>
      <div className="divider">or</div>
      <a className="button" href={api.googleConnectUrl}>Continue with Google</a>
      <p className="hint">If you already have a password account, sign in first and link Google from your dashboard.</p>
    </section>
    <ToastViewport toast={toast} onDismiss={dismissToast} />
  </main>;
}
