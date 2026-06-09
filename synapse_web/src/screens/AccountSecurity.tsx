// Synapse Web UI — account security page: MFA factor management.
import { useState, useEffect, useCallback } from "react";
import { supabase } from "../lib/supabase";
import { PageHead, SectionRow } from "../components/Common";
import { Button, Icon } from "../components/Primitives";
import { MfaEnrollTotp } from "../components/auth/MfaEnrollTotp";
import { MfaEnrollPasskey } from "../components/auth/MfaEnrollPasskey";
import { RecoveryCodesDisplay } from "../components/auth/RecoveryCodesDisplay";

interface Factor {
  id: string;
  friendly_name?: string;
  factor_type: "totp" | "webauthn";
  status: "verified" | "unverified";
}

type EnrollingType = "totp" | "passkey" | null;

export default function AccountSecurity() {
  const [factors, setFactors] = useState<Factor[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [enrolling, setEnrolling] = useState<EnrollingType>(null);
  const [showRecoveryCodes, setShowRecoveryCodes] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const loadFactors = useCallback(async () => {
    if (!supabase) {
      setLoading(false);
      return;
    }
    setLoading(true);
    const { data, error } = await supabase.auth.mfa.listFactors();
    if (error) {
      setErr(error.message);
    } else if (data) {
      const totp = (data.totp ?? []) as Factor[];
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const webauthn = ((data as any).webauthn ?? []) as Factor[];
      setFactors([...totp, ...webauthn]);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadFactors();
  }, [loadFactors]);

  async function removeFactor(factorId: string) {
    if (!supabase) return;
    setRemovingId(factorId);
    const { error } = await supabase.auth.mfa.unenroll({ factorId });
    if (error) {
      setErr(error.message);
    } else {
      await loadFactors();
    }
    setRemovingId(null);
  }

  function factorLabel(f: Factor): string {
    if (f.friendly_name) return f.friendly_name;
    return f.factor_type === "totp" ? "Authenticator app" : "Security key";
  }

  function factorIcon(f: Factor): string {
    return f.factor_type === "webauthn" ? "shield" : "clock";
  }

  // Enrollment views take over the whole content area
  if (enrolling === "totp") {
    return (
      <MfaEnrollTotp
        onEnrolled={() => {
          setEnrolling(null);
          setShowRecoveryCodes(true);
          void loadFactors();
        }}
        onCancel={() => setEnrolling(null)}
      />
    );
  }

  if (enrolling === "passkey") {
    return (
      <MfaEnrollPasskey
        onEnrolled={() => {
          setEnrolling(null);
          setShowRecoveryCodes(true);
          void loadFactors();
        }}
        onCancel={() => setEnrolling(null)}
      />
    );
  }

  if (showRecoveryCodes) {
    return <RecoveryCodesDisplay onConfirmed={() => setShowRecoveryCodes(false)} />;
  }

  return (
    <>
      <PageHead
        kicker="Account"
        title="Account"
        serif="security"
        sub="Manage two-factor authentication methods and recovery options."
      />

      {/* Enrolled factors */}
      <SectionRow title="Two-factor methods" />

      {loading && (
        <div className="db-mono db-muted" style={{ padding: "12px 0" }}>
          Loading factors…
        </div>
      )}

      {!loading && err && (
        <div
          className="db-mono"
          style={{ color: "#c9521a", fontSize: 13, padding: "8px 0" }}
        >
          {err}
        </div>
      )}

      {!loading && !err && factors.length === 0 && (
        <div className="db-panel" style={{ padding: "16px 18px" }}>
          <span className="db-mono db-muted" style={{ fontSize: 13 }}>
            No MFA factors enrolled. Add one below to secure your account.
          </span>
        </div>
      )}

      {!loading && factors.length > 0 && (
        <div className="db-panel" style={{ padding: 0 }}>
          {factors.map((f, idx) => (
            <div
              key={f.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "12px 16px",
                borderTop: idx > 0 ? "1px solid var(--line-light)" : "none",
              }}
            >
              <Icon name={factorIcon(f)} size={18} style={{ color: "var(--mute)", flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    fontSize: 14,
                    fontWeight: 500,
                    color: "var(--ink)",
                    fontFamily: "var(--font-sans)",
                  }}
                >
                  {factorLabel(f)}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
                  <span
                    className="db-mono"
                    style={{
                      fontSize: 11,
                      padding: "2px 6px",
                      background: "var(--ink-0)",
                      border: "1px solid var(--line-light)",
                      borderRadius: 5,
                      color: "var(--mute)",
                      textTransform: "uppercase",
                      letterSpacing: "0.06em",
                    }}
                  >
                    {f.factor_type === "totp" ? "TOTP" : "WebAuthn"}
                  </span>
                  {f.status === "unverified" && (
                    <span
                      className="db-mono"
                      style={{
                        fontSize: 11,
                        padding: "2px 6px",
                        background: "rgba(201,82,26,0.08)",
                        border: "1px solid rgba(201,82,26,0.2)",
                        borderRadius: 5,
                        color: "#c9521a",
                      }}
                    >
                      unverified
                    </span>
                  )}
                </div>
              </div>
              <button
                className="db-icon-mini danger"
                title="Remove this factor"
                disabled={removingId === f.id}
                onClick={() => void removeFactor(f.id)}
              >
                {removingId === f.id ? (
                  <span className="db-mono" style={{ fontSize: 11 }}>…</span>
                ) : (
                  <Icon name="trash" size={15} />
                )}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add factor */}
      <SectionRow title="Add a factor" />
      <div className="db-panel" style={{ padding: "16px 18px" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          <Button
            icon="clock"
            onClick={() => setEnrolling("totp")}
          >
            Add authenticator app
          </Button>
          <Button
            icon="shield"
            onClick={() => setEnrolling("passkey")}
          >
            Add security key / passkey
          </Button>
        </div>
      </div>

      {/* Recovery codes */}
      <SectionRow title="Recovery codes" />
      <div className="db-panel" style={{ padding: "16px 18px" }}>
        <p
          style={{
            margin: "0 0 12px",
            fontSize: 13,
            color: "var(--mute)",
            lineHeight: 1.5,
          }}
        >
          Recovery codes let you sign in if you lose access to your MFA device. Regenerating
          codes invalidates all existing ones.
        </p>
        <Button
          icon="key"
          onClick={() => setShowRecoveryCodes(true)}
        >
          Regenerate recovery codes
        </Button>
      </div>
    </>
  );
}
