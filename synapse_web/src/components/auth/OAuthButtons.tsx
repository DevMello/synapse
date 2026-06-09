// Synapse Web UI — OAuth provider buttons.
// Only renders if VITE_OAUTH_PROVIDERS env var is set (e.g. "google,github").
import { useState } from "react";
import { supabase } from "../../lib/supabase";
import type { Provider } from "@supabase/supabase-js";

interface OAuthButtonsProps {
  onError: (msg: string) => void;
}

const PROVIDER_LABELS: Record<string, string> = {
  google: "Google",
  github: "GitHub",
  gitlab: "GitLab",
  azure: "Microsoft",
  bitbucket: "Bitbucket",
  discord: "Discord",
  slack: "Slack",
};

export function OAuthButtons({ onError }: OAuthButtonsProps) {
  const rawProviders = import.meta.env.VITE_OAUTH_PROVIDERS as string | undefined;
  if (!rawProviders) return null;

  const providers = rawProviders
    .split(",")
    .map((p) => p.trim().toLowerCase())
    .filter(Boolean);

  if (providers.length === 0) return null;

  return <OAuthButtonsList providers={providers} onError={onError} />;
}

function OAuthButtonsList({
  providers,
  onError,
}: {
  providers: string[];
  onError: (msg: string) => void;
}) {
  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const isBusy = busyProvider !== null;

  async function handleOAuth(provider: string) {
    if (!supabase) {
      onError("Supabase is not configured.");
      return;
    }
    setBusyProvider(provider);
    const { error } = await supabase.auth.signInWithOAuth({
      provider: provider as Provider,
      options: { redirectTo: window.location.origin },
    });
    if (error) {
      onError(error.message);
      setBusyProvider(null);
    }
    // On success, browser redirects — no need to clear busy state.
  }

  return (
    <div style={{ marginTop: 20 }}>
      {/* Separator */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: 16,
        }}
      >
        <div style={{ flex: 1, height: 1, background: "var(--line-light)" }} />
        <span
          style={{
            fontSize: 11.5,
            color: "var(--mute)",
            fontFamily: "var(--font-mono)",
            whiteSpace: "nowrap",
          }}
        >
          or continue with
        </span>
        <div style={{ flex: 1, height: 1, background: "var(--line-light)" }} />
      </div>

      {/* Provider buttons */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {providers.map((provider) => (
          <button
            key={provider}
            type="button"
            disabled={isBusy || !supabase}
            onClick={() => handleOAuth(provider)}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              padding: "11px 16px",
              borderRadius: 11,
              border: "1px solid var(--line-light)",
              background: "var(--bone-0)",
              fontFamily: "var(--font-sans)",
              fontSize: 14,
              fontWeight: 500,
              color: "var(--ink)",
              cursor: isBusy || !supabase ? "not-allowed" : "pointer",
              opacity: isBusy && busyProvider !== provider ? 0.5 : 1,
              transition: "all 150ms ease",
            }}
          >
            {busyProvider === provider ? "Connecting…" : `Continue with ${PROVIDER_LABELS[provider] ?? provider}`}
          </button>
        ))}
      </div>
    </div>
  );
}
