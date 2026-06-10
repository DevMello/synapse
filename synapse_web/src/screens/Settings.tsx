// Synapse Web UI — personal user settings (Profile + Security).
// Replaces the old org-focused Settings screen. Org-level settings
// (members, billing, tokens) will live in a separate OrgSettings screen.
import { useState, useEffect, useCallback } from "react";
import { supabase, isSupabaseConfigured } from "../lib/supabase";
import { PageHead, SectionRow } from "../components/Common";
import { Button, Icon } from "../components/Primitives";
import { MfaEnrollTotp } from "../components/auth/MfaEnrollTotp";
import { MfaEnrollPasskey } from "../components/auth/MfaEnrollPasskey";
import { RecoveryCodesDisplay } from "../components/auth/RecoveryCodesDisplay";
import { useUI } from "../store/ui";

// ── Types ─────────────────────────────────────────────────────────────────────
type SubTab = "profile" | "security";

interface Factor {
  id: string;
  friendly_name?: string;
  factor_type: "totp" | "webauthn";
  status: "verified" | "unverified";
}

type EnrollingType = "totp" | "passkey" | null;

// ── Root component ────────────────────────────────────────────────────────────
export default function Settings() {
  const [sub, setSub] = useState<SubTab>("profile");
  const showToast = useUI((s) => s.showToast);

  return (
    <>
      <PageHead
        kicker="Account"
        title="Your"
        serif="settings"
        sub="Profile, security, and account preferences."
      />

      <div className="db-subtabs">
        {([
          ["profile", "Profile"],
          ["security", "Security"],
        ] as [SubTab, string][]).map(([id, label]) => (
          <button
            key={id}
            className={"db-subtab" + (sub === id ? " active" : "")}
            onClick={() => setSub(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {sub === "profile" && <ProfileTab showToast={showToast} />}
      {sub === "security" && <SecurityTab />}
    </>
  );
}

// ── Profile tab ───────────────────────────────────────────────────────────────
function ProfileTab({
  showToast,
}: {
  showToast: (m: { text: string; variant?: "ok" | "warn" }) => void;
}) {
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [userId, setUserId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Load user data on mount
  useEffect(() => {
    if (!isSupabaseConfigured || !supabase) {
      // Mock mode
      setDisplayName("Avery Koss");
      setEmail("avery@northwind.io");
      return;
    }

    void (async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return;
      setUserId(user.id);
      setEmail(user.email ?? "");

      const { data } = await supabase
        .from("users")
        .select("display_name")
        .eq("id", user.id)
        .maybeSingle();

      if (data?.display_name != null) {
        setDisplayName(data.display_name);
      }
    })();
  }, []);

  async function saveChanges() {
    if (!isSupabaseConfigured || !supabase) {
      showToast({ text: "Save not available in demo mode", variant: "warn" });
      return;
    }
    if (!userId) {
      showToast({ text: "Profile not loaded yet — try again in a moment", variant: "warn" });
      return;
    }
    setSaving(true);
    try {
      const { error } = await supabase
        .from("users")
        .upsert({ id: userId, display_name: displayName });
      if (error) {
        showToast({ text: error.message, variant: "warn" });
      } else {
        setDirty(false);
        showToast({ text: "Profile saved" });
      }
    } finally {
      setSaving(false);
    }
  }

  async function signOut() {
    if (!isSupabaseConfigured || !supabase) {
      showToast({ text: "Sign out not available in demo mode", variant: "warn" });
      return;
    }
    const { error } = await supabase.auth.signOut();
    if (error) showToast({ text: error.message, variant: "warn" });
  }

  return (
    <>
      <div className="db-panel" style={{ maxWidth: 560 }}>
        <div className="db-panel-head">
          <h3 className="db-panel-title">Profile</h3>
        </div>

        <span className="db-sublabel">Display name</span>
        <input
          className="db-input"
          value={displayName}
          disabled={!isSupabaseConfigured}
          onChange={(e) => {
            setDisplayName(e.target.value);
            setDirty(true);
          }}
          placeholder="Your display name"
        />

        <span className="db-sublabel">Email</span>
        <input
          className="db-input"
          value={email}
          readOnly
          style={{ color: "var(--mute)", cursor: "default" }}
        />

        <div style={{ marginTop: 18 }}>
          <Button
            variant="primary"
            icon="save"
            onClick={saveChanges}
            disabled={saving || !dirty}
          >
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </div>

      {/* Danger zone */}
      <SectionRow title="Sign out" />
      <div
        className="db-panel"
        style={{
          maxWidth: 560,
          borderColor: "rgba(201,82,26,0.25)",
          background: "rgba(201,82,26,0.03)",
        }}
      >
        <p
          style={{
            margin: "0 0 14px",
            fontSize: 13,
            color: "var(--mute)",
            lineHeight: 1.5,
          }}
        >
          Sign out of your account on this device.
        </p>
        <Button
          icon="log-out"
          onClick={signOut}
        >
          Sign out
        </Button>
      </div>
    </>
  );
}

// ── Security tab ──────────────────────────────────────────────────────────────
// Mirrors AccountSecurity.tsx logic, inlined here as a tab (no PageHead).
function SecurityTab() {
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
    setErr(null);
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

  // Sub-views replace the tab content area when enrolling or viewing recovery codes
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
