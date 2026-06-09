// Synapse Web UI — recovery codes display after MFA enrollment.
import { useState, useEffect } from "react";
import { apiPost } from "../../api/client";
import { AuthShell } from "./AuthShell";

interface RecoveryCodesDisplayProps {
  onConfirmed: () => void;
}

export function RecoveryCodesDisplay({ onConfirmed }: RecoveryCodesDisplayProps) {
  const [codes, setCodes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  useEffect(() => {
    apiPost<{ codes: string[] }>("/mfa/recovery-codes")
      .then(({ codes: c }) => {
        setCodes(c);
        setLoading(false);
      })
      .catch((e: Error) => {
        setErr(e.message);
        setLoading(false);
      });
  }, []);

  function copyCode(code: string, idx: number) {
    void navigator.clipboard.writeText(code).catch(() => undefined);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 1500);
  }

  function downloadCodes() {
    const content = codes.join("\n");
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "synapse-recovery-codes.txt";
    a.click();
    URL.revokeObjectURL(url);
  }

  // Split codes into two columns
  const col1 = codes.filter((_, i) => i % 2 === 0);
  const col2 = codes.filter((_, i) => i % 2 !== 0);

  return (
    <AuthShell>
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
          Save your recovery codes
        </h1>
        <p
          style={{
            margin: 0,
            fontSize: 13.5,
            color: "var(--mute)",
            lineHeight: 1.5,
          }}
        >
          If you lose access to your authenticator, these codes let you sign in.
        </p>
      </div>

      {/* Warning banner */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 10,
          padding: "10px 14px",
          background: "rgba(201,82,26,0.08)",
          border: "1px solid rgba(201,82,26,0.25)",
          borderRadius: 8,
          marginBottom: 18,
          fontSize: 13,
          color: "#c9521a",
          lineHeight: 1.5,
        }}
      >
        <span style={{ fontSize: 16, lineHeight: 1 }}>!</span>
        <span>
          <b>These codes won't be shown again.</b> Save them now in a password manager or secure location.
        </span>
      </div>

      {loading && (
        <div className="db-mono db-muted" style={{ textAlign: "center", padding: "16px 0" }}>
          Generating recovery codes…
        </div>
      )}

      {err && (
        <div
          className="db-mono"
          style={{ color: "#c9521a", fontSize: 12, marginBottom: 14, lineHeight: 1.4 }}
        >
          {err}
        </div>
      )}

      {!loading && !err && codes.length > 0 && (
        <>
          {/* 2-column grid of codes */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 6,
              marginBottom: 14,
            }}
          >
            {[col1, col2].map((col, colIdx) =>
              col.map((code, rowIdx) => {
                const globalIdx = rowIdx * 2 + colIdx;
                return (
                  <button
                    key={code}
                    type="button"
                    onClick={() => copyCode(code, globalIdx)}
                    title="Click to copy"
                    style={{
                      background: "var(--ink-0)",
                      border: "1px solid var(--line-light)",
                      borderRadius: 7,
                      padding: "7px 10px",
                      fontFamily: "var(--font-mono)",
                      fontSize: 13,
                      color: copiedIdx === globalIdx ? "var(--accent)" : "var(--ink)",
                      cursor: "pointer",
                      textAlign: "center",
                      letterSpacing: "0.05em",
                      transition: "color 0.15s",
                    }}
                  >
                    {copiedIdx === globalIdx ? "Copied!" : code}
                  </button>
                );
              })
            )}
          </div>

          {/* Download button */}
          <button
            type="button"
            onClick={downloadCodes}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              background: "none",
              border: "1px solid var(--line-light)",
              borderRadius: 8,
              padding: "8px 14px",
              fontSize: 13,
              color: "var(--mute)",
              cursor: "pointer",
              fontFamily: "var(--font-sans)",
              width: "100%",
              justifyContent: "center",
              marginBottom: 18,
            }}
          >
            Download codes (.txt)
          </button>

          {/* Confirmation checkbox */}
          <label
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              fontSize: 13,
              color: "var(--ink)",
              cursor: "pointer",
              marginBottom: 16,
              lineHeight: 1.5,
            }}
          >
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              style={{ marginTop: 2, cursor: "pointer", flexShrink: 0 }}
            />
            I've saved my recovery codes in a safe place
          </label>

          {/* Continue button */}
          <button
            className="db-btn db-btn-primary"
            type="button"
            disabled={!confirmed}
            onClick={onConfirmed}
            style={{
              width: "100%",
              justifyContent: "center",
              borderRadius: 11,
              padding: "12px 16px",
            }}
          >
            Continue
          </button>
        </>
      )}
    </AuthShell>
  );
}
