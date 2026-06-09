// Synapse Web UI — WebAuthn/passkey MFA enrollment step.
import { useState } from "react";
import { supabase } from "../../lib/supabase";
import { AuthShell } from "./AuthShell";

interface MfaEnrollPasskeyProps {
  onEnrolled: () => void;
  onCancel: () => void;
}

export function MfaEnrollPasskey({ onEnrolled, onCancel }: MfaEnrollPasskeyProps) {
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const webAuthnSupported = typeof window !== "undefined" && !!window.PublicKeyCredential;

  async function enroll() {
    if (!supabase) return;
    setBusy(true);
    setErr(null);

    try {
      // Enroll a webauthn factor
      const { data, error } = await supabase.auth.mfa.enroll({
        factorType: "webauthn" as Parameters<typeof supabase.auth.mfa.enroll>[0]["factorType"],
      });

      if (error) {
        // Gracefully handle unsupported webauthn factor type
        if (
          error.message.toLowerCase().includes("not supported") ||
          error.message.toLowerCase().includes("invalid") ||
          error.message.toLowerCase().includes("unknown")
        ) {
          setErr("WebAuthn enrollment not available in this environment.");
        } else {
          setErr(error.message);
        }
        setBusy(false);
        return;
      }

      if (!data) {
        setErr("No enrollment data returned. Please try again.");
        setBusy(false);
        return;
      }

      const factorId = data.id;

      // Get the credential creation options from the webauthn field
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const webauthnData = (data as any).webauthn as
        | { credential_creation_options: PublicKeyCredentialCreationOptions }
        | undefined;

      if (!webauthnData?.credential_creation_options) {
        setErr("WebAuthn enrollment not available in this environment.");
        setBusy(false);
        return;
      }

      // Trigger the browser's WebAuthn credential creation dialog
      const credential = await navigator.credentials.create({
        publicKey: webauthnData.credential_creation_options,
      });

      if (!credential) {
        setErr("Passkey registration was cancelled or failed.");
        setBusy(false);
        return;
      }

      // Challenge then verify
      const { data: challenge, error: challengeErr } = await supabase.auth.mfa.challenge({
        factorId,
      });

      if (challengeErr || !challenge) {
        setErr(challengeErr?.message ?? "Failed to start challenge.");
        setBusy(false);
        return;
      }

      const { error: verifyErr } = await supabase.auth.mfa.verify({
        factorId,
        challengeId: challenge.id,
        code: btoa(JSON.stringify(credential)),
      });

      if (verifyErr) {
        setErr(verifyErr.message);
        setBusy(false);
        return;
      }

      setDone(true);
      onEnrolled();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Passkey registration failed.";
      // DOMException: user cancelled
      if (msg.toLowerCase().includes("cancel") || msg.toLowerCase().includes("abort")) {
        setErr("Passkey registration was cancelled.");
      } else if (msg.toLowerCase().includes("not supported")) {
        setErr("WebAuthn enrollment not available in this environment.");
      } else {
        setErr(msg);
      }
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
          Add a passkey or security key
        </h1>
        <p
          style={{
            margin: 0,
            fontSize: 13.5,
            color: "var(--mute)",
            lineHeight: 1.5,
          }}
        >
          Use a fingerprint, face scan, or security key (YubiKey, etc.) as your second factor.
        </p>
      </div>

      {!webAuthnSupported ? (
        <div
          className="db-mono"
          style={{
            color: "#c9521a",
            fontSize: 13,
            lineHeight: 1.5,
            marginBottom: 16,
            padding: "10px 14px",
            background: "rgba(201,82,26,0.07)",
            border: "1px solid rgba(201,82,26,0.2)",
            borderRadius: 8,
          }}
        >
          Your browser doesn't support passkeys. Try Chrome, Safari, or Edge on a modern device.
        </div>
      ) : (
        <>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 8,
              marginBottom: 20,
              padding: "12px 14px",
              background: "var(--ink-0)",
              border: "1px solid var(--line-light)",
              borderRadius: 10,
              fontSize: 13,
              color: "var(--mute)",
              lineHeight: 1.6,
            }}
          >
            <span>• Touch ID / Face ID (Mac, iPhone, iPad)</span>
            <span>• Windows Hello (fingerprint, face, PIN)</span>
            <span>• Security keys (YubiKey, Google Titan, etc.)</span>
          </div>

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

          {done ? (
            <div
              className="db-mono"
              style={{
                color: "var(--accent)",
                fontSize: 13,
                textAlign: "center",
                marginBottom: 16,
              }}
            >
              Passkey registered successfully!
            </div>
          ) : (
            <button
              className="db-btn db-btn-primary"
              type="button"
              onClick={enroll}
              disabled={busy || !supabase}
              style={{
                width: "100%",
                justifyContent: "center",
                borderRadius: 11,
                padding: "12px 16px",
                marginBottom: 0,
              }}
            >
              {busy ? "Registering…" : "Register passkey"}
            </button>
          )}
        </>
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
