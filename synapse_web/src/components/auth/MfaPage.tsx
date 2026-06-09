// Synapse Web UI — TOTP MFA verification step.
import { useState, type FormEvent } from "react";
import { supabase } from "../../lib/supabase";
import { AuthShell } from "./AuthShell";

interface MfaPageProps {
  email: string;
  onBack: () => void;
}

export function MfaPage({ onBack }: MfaPageProps) {
  const [code, setCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setErr(null);

    const { data: factors, error: listErr } = await supabase.auth.mfa.listFactors();
    if (listErr) {
      setErr(listErr.message);
      setBusy(false);
      return;
    }

    const totp = factors?.totp?.[0];
    if (!totp) {
      setErr("No MFA factor found. Please sign in again.");
      setBusy(false);
      return;
    }

    const { data: challenge, error: challengeErr } = await supabase.auth.mfa.challenge({
      factorId: totp.id,
    });
    if (challengeErr) {
      setErr(challengeErr.message);
      setBusy(false);
      return;
    }

    if (!challenge) {
      setErr("Failed to start MFA challenge. Please try again.");
      setBusy(false);
      return;
    }

    const { error: verifyErr } = await supabase.auth.mfa.verify({
      factorId: totp.id,
      challengeId: challenge.id,
      code,
    });

    if (verifyErr) {
      setErr(verifyErr.message);
      setBusy(false);
      return;
    }

    // On success, supabase fires onAuthStateChange → session is set → app mounts.
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
          Two-factor authentication
        </h1>
        <p
          style={{
            margin: 0,
            fontSize: 13.5,
            color: "var(--mute)",
            lineHeight: 1.5,
          }}
        >
          Enter the 6-digit code from your authenticator app
        </p>
      </div>

      {/* Form */}
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 0 }}>
        <input
          className="db-input db-mono"
          type="text"
          inputMode="numeric"
          placeholder="000000"
          maxLength={6}
          autoComplete="one-time-code"
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          disabled={busy}
          required
          style={{
            marginBottom: err ? 10 : 16,
            fontFamily: "var(--font-mono)",
            letterSpacing: "0.25em",
            fontSize: 20,
            textAlign: "center",
          }}
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
          disabled={busy || !supabase || code.length !== 6}
          style={{
            width: "100%",
            justifyContent: "center",
            borderRadius: 11,
            padding: "12px 16px",
          }}
        >
          {busy ? "Verifying…" : "Verify"}
        </button>
      </form>

      {/* Back link */}
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
          ← Use a different account
        </button>
      </div>
    </AuthShell>
  );
}
