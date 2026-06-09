// Synapse Web UI — auth gate. RLS keys off auth.uid(); the data API and Realtime
// return zero rows without a session. This gate ensures a Supabase session before
// the app shell mounts. In mock mode (no Supabase configured) it renders straight
// through so the app still boots on mock data for design/CI work.
import { useEffect, useState, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase, isSupabaseConfigured } from "./supabase";
import { SignInPage } from "../components/auth/SignInPage";
import { SignUpPage } from "../components/auth/SignUpPage";
import { MfaPage } from "../components/auth/MfaPage";

type AuthView = "signin" | "signup" | "mfa";

export function AuthGate({ children }: { children: ReactNode }) {
  if (!isSupabaseConfigured || !supabase) return <>{children}</>;
  return <RequireSession>{children}</RequireSession>;
}

function RequireSession({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [view, setView] = useState<AuthView>("signin");
  const [mfaEmail, setMfaEmail] = useState("");

  useEffect(() => {
    supabase!.auth.getSession().then(({ data }) => setSession(data.session));
    const { data: sub } = supabase!.auth.onAuthStateChange((_e, s) => {
      setSession(s);
      // If the session drops to null while on a non-signin view (e.g. SIGNED_OUT
      // event from another tab), reset to the sign-in screen so the user isn't
      // left stuck on the MFA or sign-up view.
      if (!s) setView("signin");
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  if (session === undefined) {
    return <div className="db-mono db-muted" style={{ padding: 40 }}>Loading…</div>;
  }

  if (session !== null) return <>{children}</>;

  if (view === "signin") {
    return (
      <SignInPage
        onSignUp={() => setView("signup")}
        onMfaRequired={(email) => {
          setMfaEmail(email);
          setView("mfa");
        }}
      />
    );
  }

  if (view === "mfa") {
    return <MfaPage email={mfaEmail} onBack={() => setView("signin")} />;
  }

  // view === "signup"
  return <SignUpPage onSignIn={() => setView("signin")} />;
}
