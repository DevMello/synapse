// Synapse Web UI — recovery code redemption page (unauthenticated).
import { useState, type FormEvent } from "react";
import { AuthShell } from "./AuthShell";

interface RecoveryCodePageProps {
  onBack: () => void;
}

const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export function RecoveryCodePage({ onBack }: RecoveryCodePageProps) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);

    try {
      const res = await fetch(`${API_BASE}/mfa/recovery-codes/redeem`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code }),
      });

      if (!res.ok) {
        const text = await res.text().catch(() => "");
        let msg = `${res.status} ${res.statusText}`;
        try {
          const json = JSON.parse(text) as { detail?: string; message?: string };
          msg = json.detail ?? json.message ?? msg;
        } catch {
          if (text) msg = text;
        }
        setErr(msg);
        setBusy(false);
        return;
      }

      setBusy(false);
      setSuccess(true);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : "An unexpected error occurred.");
      setBusy(false);
    }
  }

  return (
    <AuthShell>
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
          Use a recovery code
        </h1>
        <p
          style={{
            margin: 0,
            fontSize: 13.5,
            color: "var(--mute)",
            lineHeight: 1.5,
          }}
        >
          Enter your email and one of your saved recovery codes to remove MFA from your account.
        </p>
      </div>

      {success ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div
            style={{
              padding: "12px 14px",
              background: "rgba(34,197,94,0.08)",
              border: "1px solid rgba(34,197,94,0.25)",
              borderRadius: 8,
              fontSize: 13,
              color: "var(--ink)",
              lineHeight: 1.6,
            }}
          >
            MFA has been removed from your account. You can now sign in with your email and password.
          </div>
          <button
            className="db-btn db-btn-primary"
            type="button"
            onClick={onBack}
            style={{
              width: "100%",
              justifyContent: "center",
              borderRadius: 11,
              padding: "12px 16px",
            }}
          >
            Back to sign in
          </button>
        </div>
      ) : (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 0 }}>
          <label
            style={{
              fontSize: 12,
              color: "var(--mute)",
              marginBottom: 4,
              fontFamily: "var(--font-sans)",
            }}
          >
            Email address
          </label>
          <input
            className="db-input"
            type="email"
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={busy}
            required
            style={{ marginBottom: 12 }}
          />

          <label
            style={{
              fontSize: 12,
              color: "var(--mute)",
              marginBottom: 4,
              fontFamily: "var(--font-sans)",
            }}
          >
            Recovery code{" "}
            <span className="db-mono" style={{ fontSize: 11 }}>
              (XXXXX-XXXXX)
            </span>
          </label>
          <input
            className="db-input db-mono"
            type="text"
            autoComplete="off"
            placeholder="XXXXX-XXXXX"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            disabled={busy}
            required
            style={{ marginBottom: err ? 10 : 16, letterSpacing: "0.05em" }}
          />

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

          <button
            className="db-btn db-btn-primary"
            type="submit"
            disabled={busy || !email || !code}
            style={{
              width: "100%",
              justifyContent: "center",
              borderRadius: 11,
              padding: "12px 16px",
            }}
          >
            {busy ? "Verifying…" : "Redeem recovery code"}
          </button>
        </form>
      )}

      {!success && (
        <div style={{ marginTop: 18, textAlign: "center" }}>
          <button
            type="button"
            onClick={onBack}
            style={{
              background: "none",
              border: "none",
              padding: 0,
              color: "var(--mute)",
              fontSize: 13,
              cursor: "pointer",
              fontFamily: "var(--font-sans)",
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            ← Back to sign in
          </button>
        </div>
      )}
    </AuthShell>
  );
}
