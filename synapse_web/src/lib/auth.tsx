// Synapse Web UI — auth gate. RLS keys off auth.uid(); the data API and Realtime
// return zero rows without a session. This gate ensures a Supabase session before
// the app shell mounts. In mock mode (no Supabase configured) it renders straight
// through so the app still boots on mock data for design/CI work.
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase, isSupabaseConfigured } from "./supabase";

export function AuthGate({ children }: { children: ReactNode }) {
  if (!isSupabaseConfigured || !supabase) return <>{children}</>;
  return <RequireSession>{children}</RequireSession>;
}

function RequireSession({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null | undefined>(undefined);

  useEffect(() => {
    supabase!.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = supabase!.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  if (session === undefined) {
    return <div className="db-mono db-muted" style={{ padding: 40 }}>Loading…</div>;
  }
  if (session === null) return <SignIn />;
  return <>{children}</>;
}

function SignIn() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const { error } = await supabase!.auth.signInWithPassword({ email, password });
    if (error) setErr(error.message);
    setBusy(false);
  }

  return (
    <div style={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
      <form onSubmit={submit} className="db-card" style={{ width: 320, padding: 24, display: "grid", gap: 12 }}>
        <h1 className="db-mono" style={{ fontSize: 18 }}>Synapse</h1>
        <input className="db-input" type="email" placeholder="email" value={email}
          onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
        <input className="db-input" type="password" placeholder="password" value={password}
          onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        {err && <div className="db-mono" style={{ color: "var(--db-danger, #e5484d)", fontSize: 12 }}>{err}</div>}
        <button className="db-btn db-btn-primary" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
