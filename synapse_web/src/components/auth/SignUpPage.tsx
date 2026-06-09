import { useState, type FormEvent } from "react";
import { supabase } from "../../lib/supabase";

interface SignUpPageProps {
  onSignIn: () => void;
}

export function SignUpPage({ onSignIn }: SignUpPageProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);

    if (password.length < 8) {
      setErr("Password must be at least 8 characters");
      return;
    }
    if (password !== confirmPassword) {
      setErr("Passwords do not match");
      return;
    }

    setBusy(true);
    try {
      const { error } = await supabase!.auth.signUp({ email, password });
      if (error) {
        setErr(error.message);
        return;
      }
      setDone(true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "An unexpected error occurred");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        display: "grid",
        placeItems: "center",
        minHeight: "100vh",
        background: "var(--ink)",
        position: "relative",
        overflow: "hidden",
      }}
      className="fx-grid-dark"
    >
      {/* Aurora glow */}
      <div className="fx-aurora" />
      {/* Noise overlay */}
      <div className="fx-noise" />

      {/* Card */}
      <div
        style={{
          position: "relative",
          zIndex: 1,
          width: 380,
          maxWidth: "92vw",
          background: "var(--paper)",
          borderRadius: 18,
          padding: "32px 36px 28px",
          border: "1px solid var(--line-light)",
          boxShadow: "var(--shadow-panel-lift)",
        }}
      >
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 24 }}>
          <div
            style={{
              width: 18,
              height: 18,
              background: "var(--accent)",
              borderRadius: 4,
              flexShrink: 0,
            }}
          />
          <span className="db-mono" style={{ fontSize: 14, fontWeight: 600, letterSpacing: "-0.01em" }}>
            Synapse
          </span>
        </div>

        {done ? (
          /* Success state */
          <div style={{ textAlign: "center", padding: "8px 0" }}>
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: "50%",
                background: "var(--status-ok-bg)",
                border: "1px solid rgba(78,196,106,0.3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto 20px",
              }}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--status-ok)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
            <div style={{ fontSize: 22, fontWeight: 500, letterSpacing: "-0.02em", marginBottom: 12 }}>
              Check your email
            </div>
            <div style={{ fontSize: 14, color: "var(--mute)", lineHeight: 1.55, marginBottom: 24 }}>
              We sent a confirmation link to{" "}
              <strong style={{ color: "var(--ink)", fontWeight: 600 }}>{email}</strong>.
              Click it to activate your account.
            </div>
            <button
              className="db-btn db-btn-primary"
              style={{ width: "100%", justifyContent: "center" }}
              onClick={onSignIn}
            >
              Back to sign in
            </button>
          </div>
        ) : (
          /* Sign-up form */
          <form onSubmit={submit} style={{ display: "grid", gap: 12 }}>
            <div style={{ marginBottom: 4 }}>
              <div style={{ fontSize: 22, fontWeight: 500, letterSpacing: "-0.02em", marginBottom: 4 }}>
                Create account
              </div>
              <div className="db-muted" style={{ fontSize: 13.5 }}>
                Start using Synapse today
              </div>
            </div>

            <input
              className="db-input"
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
            <input
              className="db-input"
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              required
            />
            <input
              className="db-input"
              type="password"
              placeholder="Confirm password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              required
            />

            {err && (
              <div className="db-mono" style={{ color: "var(--db-danger, #e5484d)", fontSize: 12 }}>
                {err}
              </div>
            )}

            <button
              className="db-btn db-btn-primary"
              type="submit"
              disabled={busy}
              style={{ width: "100%", justifyContent: "center", marginTop: 4 }}
            >
              {busy ? "Creating…" : "Create account"}
            </button>

            <div style={{ textAlign: "center", fontSize: 13, color: "var(--mute)", marginTop: 4 }}>
              Already have an account?{" "}
              <button
                type="button"
                onClick={onSignIn}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--accent)",
                  cursor: "pointer",
                  fontWeight: 600,
                  fontSize: 13,
                  padding: 0,
                  fontFamily: "inherit",
                }}
              >
                Sign in
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
