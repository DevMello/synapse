// Synapse Web UI — polished sign-in form.
import { useState, type FormEvent } from "react";
import { supabase } from "../../lib/supabase";
import { AuthShell } from "./AuthShell";
import { OAuthButtons } from "./OAuthButtons";

interface SignInPageProps {
  onSignUp: () => void;
  onMfaRequired: (email: string) => void;
}

export function SignInPage({ onSignUp, onMfaRequired }: SignInPageProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setErr(null);

    const { error } = await supabase.auth.signInWithPassword({ email, password });

    if (error) {
      // Check for MFA required
      if (error.code === "mfa_required") {
        onMfaRequired(email);
        return;
      }
      setErr(error.message);
      setBusy(false);
    }
    // On success, supabase fires onAuthStateChange → session is set → app mounts.
    // No need to setBusy(false) since the component unmounts.
  }

  return (
    <AuthShell>
      {/* Page heading */}
      <div style={{ marginBottom: 24 }}>
        <h1
          style={{
            margin: "0 0 6px",
            fontSize: 22,
            fontWeight: 500,
            letterSpacing: "-0.02em",
            color: "var(--ink)",
            fontFamily: "var(--font-sans)",
          }}
        >
          Welcome back
        </h1>
        <p
          style={{
            margin: 0,
            fontSize: 13.5,
            color: "var(--mute)",
            lineHeight: 1.5,
          }}
        >
          Sign in to your Synapse account
        </p>
      </div>

      {/* Form */}
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 0 }}>
        <input
          className="db-input"
          type="email"
          placeholder="Email address"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
          required
          disabled={busy}
          style={{ marginBottom: 10 }}
        />
        <input
          className="db-input"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
          disabled={busy}
          style={{ marginBottom: err ? 10 : 16 }}
        />

        {/* Error display */}
        {err && (
          <div
            className="db-mono"
            style={{
              color: "#c9521a",
              fontSize: 12,
              marginBottom: 14,
              lineHeight: 1.4,
            }}
          >
            {err}
          </div>
        )}

        {/* Submit button */}
        <button
          className="db-btn db-btn-primary"
          type="submit"
          disabled={busy || !supabase}
          style={{
            width: "100%",
            justifyContent: "center",
            borderRadius: 11,
            padding: "12px 16px",
          }}
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>

      {/* OAuth buttons */}
      <OAuthButtons onError={setErr} />

      {/* Footer link */}
      <div
        style={{
          marginTop: 22,
          textAlign: "center",
          fontSize: 13.5,
          color: "var(--mute)",
        }}
      >
        Don't have an account?{" "}
        <button
          type="button"
          onClick={onSignUp}
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
          Create one
        </button>
      </div>
    </AuthShell>
  );
}
