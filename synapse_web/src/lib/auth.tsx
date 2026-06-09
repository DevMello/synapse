// Synapse Web UI — auth gate. RLS keys off auth.uid(); the data API and Realtime
// return zero rows without a session. This gate ensures a Supabase session before
// the app shell mounts. In mock mode (no Supabase configured) it renders straight
// through so the app still boots on mock data for design/CI work.
import { useEffect, useState, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase, isSupabaseConfigured } from "./supabase";
import { ensureSessionSigningKey, getPublicKeyBase64, clearSessionSigningKey } from "./commandSigning";
import { apiPost } from "../api/client";
import { SignInPage } from "../components/auth/SignInPage";
import { SignUpPage } from "../components/auth/SignUpPage";
import { MfaPage } from "../components/auth/MfaPage";
import { MfaEnrollTotp } from "../components/auth/MfaEnrollTotp";
import { MfaEnrollPasskey } from "../components/auth/MfaEnrollPasskey";
import { RecoveryCodesDisplay } from "../components/auth/RecoveryCodesDisplay";
import { RecoveryCodePage } from "../components/auth/RecoveryCodePage";

type AuthView =
  | "signin"
  | "signup"
  | "mfa"
  | "enroll-totp"
  | "enroll-passkey"
  | "show-recovery-codes"
  | "recovery-code";

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
    const { data: sub } = supabase!.auth.onAuthStateChange((event, s) => {
      setSession(s);
      if (s && (event === "SIGNED_IN" || event === "INITIAL_SESSION")) {
        // Register once per new session — not on every TOKEN_REFRESHED event.
        void (async () => {
          try {
            await ensureSessionSigningKey();
            const public_key = await getPublicKeyBase64();
            await apiPost("/auth/command-key", { public_key });
          } catch {
            // non-fatal — command signing degrades gracefully
          }
        })();
      } else if (!s) {
        clearSessionSigningKey();
        setView("signin");
      }
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
    return (
      <MfaPage
        email={mfaEmail}
        onBack={() => setView("signin")}
        onRecoveryCode={() => setView("recovery-code")}
      />
    );
  }

  if (view === "enroll-totp") {
    return (
      <MfaEnrollTotp
        onEnrolled={() => setView("show-recovery-codes")}
        onCancel={() => setView("signin")}
      />
    );
  }

  if (view === "enroll-passkey") {
    return (
      <MfaEnrollPasskey
        onEnrolled={() => setView("show-recovery-codes")}
        onCancel={() => setView("signin")}
      />
    );
  }

  if (view === "show-recovery-codes") {
    return <RecoveryCodesDisplay onConfirmed={() => setView("signin")} />;
  }

  if (view === "recovery-code") {
    return <RecoveryCodePage onBack={() => setView("signin")} />;
  }

  // view === "signup"
  return <SignUpPage onSignIn={() => setView("signin")} />;
}
