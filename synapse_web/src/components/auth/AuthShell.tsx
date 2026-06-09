// Synapse Web UI — full-viewport wrapper for all auth pages.
import type { ReactNode } from "react";
import { LogoMark } from "../Primitives";

interface AuthShellProps {
  children: ReactNode;
  subtitle?: string;
}

export function AuthShell({ children, subtitle }: AuthShellProps) {
  return (
    <div
      style={{
        position: "relative",
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--ink-0)",
        overflow: "hidden",
      }}
      className="fx-grid-dark"
    >
      {/* Aurora glow */}
      <div className="fx-aurora" />

      {/* Noise overlay */}
      <div className="fx-noise" />

      {/* Hatch corners */}
      <div className="fx-hatch" style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
        <span className="hatch tl" />
        <span className="hatch tr" />
        <span className="hatch bl" />
        <span className="hatch br" />
      </div>

      {/* Content card */}
      <div
        style={{
          position: "relative",
          zIndex: 1,
          width: 380,
          maxWidth: "calc(100vw - 32px)",
          background: "var(--paper)",
          borderRadius: 18,
          border: "1px solid var(--line-light)",
          boxShadow: "0 32px 80px -24px rgba(0,0,0,0.5), 0 8px 24px -8px rgba(0,0,0,0.3)",
          overflow: "hidden",
        }}
      >
        {/* Card header with logo */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "20px 28px 0",
          }}
        >
          <LogoMark size={18} />
          <span
            className="db-mono"
            style={{
              fontWeight: 600,
              fontSize: 17,
              letterSpacing: "-0.02em",
              color: "var(--ink)",
            }}
          >
            Synapse
          </span>
        </div>

        {/* Subtitle if provided */}
        {subtitle && (
          <div
            style={{
              padding: "8px 28px 0",
              fontSize: 13,
              color: "var(--mute)",
              fontFamily: "var(--font-mono)",
            }}
          >
            {subtitle}
          </div>
        )}

        {/* Main content */}
        <div style={{ padding: "24px 28px 28px" }}>
          {children}
        </div>
      </div>
    </div>
  );
}
