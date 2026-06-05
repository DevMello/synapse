// Synapse Web UI — live trace viewer (streaming reasoning + running cost).
// Ported from design-reference/app/Trace.jsx. Streams a run's reasoning event by
// event with a running token/cost tally and a Pause/Play/Replay control.
//
// VISIBILITY NOTE: the original prototype's entrance animation could leave events
// stuck at opacity:0. Here every rendered event is visible by default — we only
// append events over time (slice 0..shown), never gate them behind an animation
// that lacks a guaranteed opacity:1 end state. A subtle, reduced-motion-safe
// fade-in is applied inline and always resolves to opacity:1.
import { useEffect, useRef, useState } from "react";
import { Icon } from "../../components/Primitives";

// Rich trace-event shape. This is intentionally richer than the terminal-style
// `TraceLine` in src/types.ts (which carries no tool/guard/cost fields), so it is
// modeled locally here for the streaming reasoning viewer.
export type TraceEventType =
  | "meta" | "prompt" | "think" | "tool-call" | "tool-result"
  | "guard" | "redact" | "completion" | "done";

export interface TraceEvent {
  type: TraceEventType;
  text: string;
  tok: number;
  cost: number;
  label?: string;
  tool?: string;
  args?: string;
  level?: "warn";
  cat?: string;
  action?: string;
}

export const TRACE_EVENTS: TraceEvent[] = [
  { type: "meta", text: "run #2214 · trigger: webhook (PR #2214 opened) · host my-macbook-pro", tok: 0, cost: 0 },
  { type: "prompt", label: "system", text: "Review the diff against the northwind ruleset. Gate coverage at 80%.", tok: 1200, cost: 0.004 },
  { type: "think", text: "Plan: read the diff, run coverage, scan for off-list network calls, write the report.", tok: 540, cost: 0.006 },
  { type: "tool-call", tool: "git.diff", args: "PR #2214", text: "Resolving changed files…", tok: 80, cost: 0.0 },
  { type: "tool-result", tool: "git.diff", text: "14 files changed (+612 / −188) across 3 modules.", tok: 3100, cost: 0.012 },
  { type: "think", text: "payments/retries.ts adds a new outbound call. Need to check it against the allow-list.", tok: 620, cost: 0.007 },
  { type: "tool-call", tool: "shell.coverage", args: "vitest --coverage", text: "Running test suite…", tok: 60, cost: 0.0 },
  { type: "tool-result", tool: "shell.coverage", text: "coverage 78.4% — 1.6 pts under the 80% gate.", tok: 2400, cost: 0.009, level: "warn" },
  { type: "tool-call", tool: "fetch", args: "api.unknown-vendor.com", text: "Probing new network call…", tok: 40, cost: 0.0 },
  { type: "guard", cat: "tool-bypass", text: "fetch to api.unknown-vendor.com blocked — host not on the network allow-list.", action: "blocked", tok: 0, cost: 0 },
  { type: "think", text: "Coverage gate failed and a new off-list call appeared. I will request changes, not approve.", tok: 700, cost: 0.008 },
  { type: "tool-call", tool: "fs.write", args: "reports/review/2214.md", text: "Writing review report…", tok: 120, cost: 0.0 },
  { type: "redact", text: "masked 1 secret (<REDACTED:API_KEY>) before upload", tok: 0, cost: 0 },
  { type: "completion", text: "Requested changes on PR #2214: restore coverage to ≥80% and remove the api.unknown-vendor.com call (or add it to the allow-list with a reason).", tok: 1800, cost: 0.021 },
  { type: "done", text: "run complete · exit gate · 1m 12s", tok: 0, cost: 0 },
];

const prefersReducedMotion = (): boolean =>
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

export interface TraceViewerProps {
  /** Stream events over time (live run) vs. show all immediately (replay). */
  autoplay?: boolean;
  /** Optional explicit body max-height. */
  height?: number;
  /** Drop the lifted shadow when embedded inside a tab. */
  embedded?: boolean;
  /** Title shown in the trace header (e.g. "pr-reviewer · run #2214"). */
  title?: string;
  /** Seed events to stream. Defaults to the bundled pr-reviewer trace. */
  events?: TraceEvent[];
}

export function TraceViewer({
  autoplay = true,
  height,
  embedded,
  title = "pr-reviewer · run #2214",
  events = TRACE_EVENTS,
}: TraceViewerProps) {
  const reduced = prefersReducedMotion();
  // When reduced motion is requested, render everything at once even if "live".
  const startCount = autoplay && !reduced ? 1 : events.length;
  const [shown, setShown] = useState(startCount);
  const [playing, setPlaying] = useState(autoplay && !reduced);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!playing || shown >= events.length) return;
    const ev = events[shown];
    const delay =
      ev.type === "tool-result" || ev.type === "completion" ? 1100
        : ev.type === "think" ? 850
          : 650;
    const t = window.setTimeout(() => setShown((s) => s + 1), delay);
    return () => window.clearTimeout(t);
  }, [shown, playing, events]);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [shown]);

  const visible = events.slice(0, shown);
  const tokens = visible.reduce((s, e) => s + (e.tok || 0), 0);
  const cost = visible.reduce((s, e) => s + (e.cost || 0), 0);
  const live = shown < events.length;
  const done = events[shown - 1]?.type === "done";

  const handleCtl = () => {
    if (!live) {
      setShown(1);
      setPlaying(true);
    } else {
      setPlaying((p) => !p);
    }
  };

  return (
    <div className={"db-trace" + (embedded ? " embedded" : "")}>
      <div className="db-trace-head">
        <div className="db-trace-head-l">
          {live ? <span className="status-chip running">streaming</span>
            : done ? <span className="status-chip blocked">gated</span>
              : <span className="status-chip passed">replay</span>}
          <span className="db-trace-title db-mono">{title}</span>
        </div>
        <div className="db-trace-stats">
          <div className="db-trace-stat">
            <span className="db-trace-stat-n db-mono">{tokens.toLocaleString()}</span>
            <span className="db-trace-stat-l">tokens</span>
          </div>
          <div className="db-trace-stat">
            <span className="db-trace-stat-n db-mono">${cost.toFixed(3)}</span>
            <span className="db-trace-stat-l">cost</span>
          </div>
          <button className="db-trace-ctl" onClick={handleCtl} type="button">
            <Icon name={!live ? "rotate-ccw" : playing ? "pause" : "play"} size={14} stroke={2} />
            {!live ? "Replay" : playing ? "Pause" : "Play"}
          </button>
        </div>
      </div>

      <div
        className="db-trace-body"
        ref={bodyRef}
        style={height ? { maxHeight: height } : undefined}
      >
        {visible.map((e, i) => <TraceEventRow key={i} e={e} />)}
        {live && <div className="db-trace-cursor"><span className="term-cursor" /></div>}
      </div>
    </div>
  );
}

// Each row renders fully visible by default — no opacity-gating animation. New
// events simply mount as `shown` grows, so the stream is always on screen.
function TraceEventRow({ e }: { e: TraceEvent }) {
  switch (e.type) {
    case "meta":
      return <div className="db-tev meta db-mono"><Icon name="git-commit" size={13} /> {e.text}</div>;
    case "prompt":
      return (
        <div className="db-tev prompt">
          <span className="db-tev-tag prompt">{e.label}</span>
          <span className="db-tev-text">{e.text}</span>
        </div>
      );
    case "think":
      return (
        <div className="db-tev think">
          <Icon name="brain" size={14} className="db-tev-glyph" />
          <span className="db-tev-text">{e.text}</span>
        </div>
      );
    case "tool-call":
      return (
        <div className="db-tev toolcall">
          <span className="db-tev-tag tool db-mono">{e.tool}</span>
          <span className="db-tev-args db-mono">{e.args}</span>
          <span className="db-tev-text">{e.text}</span>
        </div>
      );
    case "tool-result":
      return (
        <div className={"db-tev toolresult" + (e.level === "warn" ? " warn" : "")}>
          <span className="db-tev-rail" />
          <span className="db-tev-text db-mono">{e.text}</span>
        </div>
      );
    case "guard":
      return (
        <div className="db-tev guard">
          <span className="db-tev-tag guard"><Icon name="shield-alert" size={12} /> {e.cat}</span>
          <span className="db-tev-text">{e.text}</span>
          <span className="db-tev-action">{e.action}</span>
        </div>
      );
    case "redact":
      return <div className="db-tev redact db-mono"><Icon name="lock" size={13} /> {e.text}</div>;
    case "completion":
      return (
        <div className="db-tev completion">
          <span className="db-tev-tag done">output</span>
          <span className="db-tev-text">{e.text}</span>
        </div>
      );
    case "done":
      return <div className="db-tev donerow db-mono"><Icon name="check-circle" size={14} /> {e.text}</div>;
    default:
      return null;
  }
}

export default TraceViewer;
