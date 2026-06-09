// Synapse Web UI — MFA verification step (TOTP + WebAuthn).
import { useState, type FormEvent } from "react";
import { supabase } from "../../lib/supabase";
import { AuthShell } from "./AuthShell";

interface MfaPageProps {
  email: string;
  onBack: () => void;
  onRecoveryCode: () => void;
}

type MfaMethod = "totp" | "webauthn";

export function MfaPage({ onBack, onRecoveryCode }: MfaPageProps) {
  const [code, setCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [method, setMethod] = useState<MfaMethod>("totp");

  async function submitTotp(e: FormEvent) {
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

  async function submitWebAuthn() {
    if (!supabase) return;
    setBusy(true);
    setErr(null);

    try {
      const { data: factors, error: listErr } = await supabase.auth.mfa.listFactors();
      if (listErr) {
        setErr(listErr.message);
        setBusy(false);
        return;
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const webauthnFactors = (factors as any)?.webauthn as Array<{ id: string }> | undefined;
      const webauthnFactor = webauthnFactors?.[0];

      if (!webauthnFactor) {
        console.warn("[MFA] No WebAuthn factor found, falling back to TOTP UI.");
        setMethod("totp");
        setErr("No passkey found. Please use your authenticator app.");
        setBusy(false);
        return;
      }

      const { data: challenge, error: challengeErr } = await supabase.auth.mfa.challenge({
        factorId: webauthnFactor.id,
      });

      if (challengeErr || !challenge) {
        setErr(challengeErr?.message ?? "Failed to start passkey challenge.");
        setBusy(false);
        return;
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const credentialRequestOptions = (challenge as any).webauthn
        ?.credential_request_options as PublicKeyCredentialRequestOptions | undefined;

      if (!credentialRequestOptions) {
        console.warn("[MFA] WebAuthn challenge returned unexpected shape.");
        setErr("Passkey challenge not available. Please use your authenticator app.");
        setMethod("totp");
        setBusy(false);
        return;
      }

      const credential = await navigator.credentials.get({
        publicKey: credentialRequestOptions,
      });

      if (!credential) {
        setErr("Passkey verification was cancelled or failed.");
        setBusy(false);
        return;
      }

      const { error: verifyErr } = await supabase.auth.mfa.verify({
        factorId: webauthnFactor.id,
        challengeId: challenge.id,
        code: "",
      });

      if (verifyErr) {
        setErr(verifyErr.message);
        setBusy(false);
        return;
      }

      // On success, supabase fires onAuthStateChange → session is set → app mounts.
    } catch (ex) {
      const msg = ex instanceof Error ? ex.message : "Passkey verification failed.";
      if (msg.toLowerCase().includes("cancel") || msg.toLowerCase().includes("abort")) {
        setErr("Passkey verification was cancelled.");
      } else {
        setErr(msg);
      }
      setBusy(false);
    }
  }

  return (
    <AuthShell>
      {/* Page heading */}
      <div style={{ marginBottom: 20 }}>
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
          {method === "totp"
            ? "Enter the 6-digit code from your authenticator app"
            : "Use your passkey or security key to verify"}
        </p>
      </div>

      {/* Method tabs */}
      <div
        style={{
          display: "flex",
          gap: 4,
          marginBottom: 20,
          background: "var(--ink-0)",
          border: "1px solid var(--line-light)",
          borderRadius: 9,
          padding: 3,
        }}
      >
        {(["totp", "webauthn"] as MfaMethod[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => { setMethod(m); setErr(null); }}
            style={{
              flex: 1,
              padding: "6px 10px",
              borderRadius: 7,
              border: "none",
              background: method === m ? "var(--paper)" : "transparent",
              boxShadow: method === m ? "0 1px 3px rgba(0,0,0,0.15)" : "none",
              color: method === m ? "var(--ink)" : "var(--mute)",
              fontSize: 12,
              fontFamily: "var(--font-sans)",
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            {m === "totp" ? "Authenticator app" : "Passkey / security key"}
          </button>
        ))}
      </div>

      {/* TOTP form */}
      {method === "totp" && (
        <form onSubmit={submitTotp} style={{ display: "flex", flexDirection: "column", gap: 0 }}>
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
      )}

      {/* WebAuthn flow */}
      {method === "webauthn" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
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
            type="button"
            onClick={() => void submitWebAuthn()}
            disabled={busy || !supabase}
            style={{
              width: "100%",
              justifyContent: "center",
              borderRadius: 11,
              padding: "12px 16px",
            }}
          >
            {busy ? "Waiting for passkey…" : "Use your passkey or security key"}
          </button>
        </div>
      )}

      {/* Footer links */}
      <div
        style={{
          marginTop: 18,
          textAlign: "center",
          display: "flex",
          flexDirection: "column",
          gap: 10,
        }}
      >
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
            justifyContent: "center",
            gap: 4,
          }}
        >
          ← Use a different account
        </button>
        <button
          type="button"
          onClick={onRecoveryCode}
          style={{
            background: "none",
            border: "none",
            padding: 0,
            color: "var(--mute)",
            fontSize: 12,
            cursor: "pointer",
            fontFamily: "var(--font-sans)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 4,
            textDecoration: "underline",
          }}
        >
          Lost your device? Use a recovery code →
        </button>
      </div>
    </AuthShell>
  );
}
