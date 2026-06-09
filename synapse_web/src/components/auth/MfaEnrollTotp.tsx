// Synapse Web UI — TOTP MFA enrollment step.
import { useState, useEffect, type FormEvent } from "react";
import { supabase } from "../../lib/supabase";
import { AuthShell } from "./AuthShell";

interface MfaEnrollTotpProps {
  onEnrolled: () => void;
  onCancel: () => void;
}

export function MfaEnrollTotp({ onEnrolled, onCancel }: MfaEnrollTotpProps) {
  const [factorId, setFactorId] = useState<string | null>(null);
  const [qrCode, setQrCode] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [showSecret, setShowSecret] = useState(false);
  const [code, setCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return;
    }
    // Guard against double-invoke in React StrictMode (mount → unmount → remount).
    // Without this, two unverified TOTP factors would be created and the first
    // becomes an orphan even though the user only verifies the second one.
    let cancelled = false;
    supabase.auth.mfa
      .enroll({ factorType: "totp", issuer: "Synapse" })
      .then(({ data, error }) => {
        if (cancelled) return;
        if (error) {
          setErr(error.message);
        } else if (data) {
          setFactorId(data.id);
          setQrCode(data.totp?.qr_code ?? null);
          setSecret(data.totp?.secret ?? null);
        }
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!supabase || !factorId) return;
    setBusy(true);
    setErr(null);

    const { error } = await supabase.auth.mfa.challengeAndVerify({
      factorId,
      code,
    });

    if (error) {
      setErr(error.message);
      setBusy(false);
      return;
    }

    onEnrolled();
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
          Set up authenticator app
        </h1>
        <p
          style={{
            margin: 0,
            fontSize: 13.5,
            color: "var(--mute)",
            lineHeight: 1.5,
          }}
        >
          Scan the QR code with your authenticator app, then enter the 6-digit code to confirm.
        </p>
      </div>

      {loading && (
        <div className="db-mono db-muted" style={{ textAlign: "center", padding: "16px 0" }}>
          Generating QR code…
        </div>
      )}

      {!loading && !err && qrCode && (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: 20 }}>
          <img
            src={qrCode}
            alt="TOTP QR code"
            style={{
              width: 180,
              height: 180,
              border: "1px solid var(--line-light)",
              borderRadius: 10,
              background: "#fff",
              padding: 8,
              marginBottom: 12,
            }}
          />
          <button
            type="button"
            onClick={() => setShowSecret((s) => !s)}
            style={{
              background: "none",
              border: "none",
              padding: 0,
              color: "var(--mute)",
              fontSize: 12,
              cursor: "pointer",
              fontFamily: "var(--font-sans)",
            }}
          >
            {showSecret ? "Hide secret key" : "Can't scan? Show secret key"}
          </button>
          {showSecret && secret && (
            <code
              className="db-mono"
              style={{
                display: "block",
                marginTop: 8,
                padding: "8px 12px",
                background: "var(--ink-0)",
                border: "1px solid var(--line-light)",
                borderRadius: 8,
                fontSize: 13,
                letterSpacing: "0.1em",
                wordBreak: "break-all",
                textAlign: "center",
                color: "var(--ink)",
              }}
            >
              {secret}
            </code>
          )}
        </div>
      )}

      {!loading && (
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
            disabled={busy || loading || !factorId}
            required
            style={{
              marginBottom: err ? 10 : 16,
              fontFamily: "var(--font-mono)",
              letterSpacing: "0.25em",
              fontSize: 20,
              textAlign: "center",
            }}
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
            disabled={busy || !supabase || !factorId || code.length !== 6}
            style={{
              width: "100%",
              justifyContent: "center",
              borderRadius: 11,
              padding: "12px 16px",
            }}
          >
            {busy ? "Verifying…" : "Confirm setup"}
          </button>
        </form>
      )}

      <div style={{ marginTop: 18, textAlign: "center" }}>
        <button
          type="button"
          onClick={onCancel}
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
          ← Cancel
        </button>
      </div>
    </AuthShell>
  );
}
