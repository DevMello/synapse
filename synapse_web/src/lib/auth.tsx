// Synapse Web UI — auth gate. RLS keys off auth.uid(); the data API and Realtime
// return zero rows without a session. This gate ensures a Supabase session before
// the app shell mounts. In mock mode (no Supabase configured) it renders straight
// through so the app still boots on mock data for design/CI work.
import { useEffect, useState, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase, isSupabaseConfigured } from "./supabase";
import { SignInPage } from "../components/auth/SignInPage";
import { MfaPage } from "../components/auth/MfaPage";
import { AuthShell } from "../components/auth/AuthShell";

// Stub placeholder — Unit 2 will replace this with the real sign-up page.
function SignUpPage({ onSignIn }: { onSignIn: () => void }) {
  return (
    <AuthShell>
      <div style={{ textAlign: "center", padding: "8px 0 16px" }}>
        <h1
          style={{
            margin: "0 0 10px",
            fontSize: 22,
            fontWeight: 500,
            letterSpacing: "-0.02em",
            color: "var(--ink)",
          }}
        >
          Create account
        </h1>
        <p style={{ margin: "0 0 20px", fontSize: 13.5, color: "var(--mute)" }}>
          Sign-up coming soon.
        </p>
        <button
          type="button"
          onClick={onSignIn}
          style={{
            background: "none",
            border: "none",
            padding: 0,
            color: "var(--accent)",
            fontWeight: 600,
            fontSize: 13.5,
            cursor: "pointer",
            fontFamily: "var(--font-sans)",
          }}
        >
          ← Back to sign in
        </button>
      </div>
    </AuthShell>
  );
}

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
