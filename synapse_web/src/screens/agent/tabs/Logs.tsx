import { Fragment, useMemo, useState, type ReactNode } from "react";
import { Icon } from "../../../components/Primitives";
import { Segmented } from "../../../components/Common";
import { useCurrentAgent } from "../context";
import { useLogLines } from "../../../api/queries";

// Agent Detail — Logs tab (redaction-aware). Searchable/filterable access & tool
// logs. Redacted values arrive pre-masked from the daemon and render as visible
// markers — the UI never sees raw secrets. Guardrail findings are tagged inline
// with category, severity, and the action the daemon took.

type LogFilter = "all" | "guard";

// Map a guardrail category to the severity + action the daemon took. The daemon
// is the source of truth for these; this lookup mirrors its policy so the inline
// finding reads the same in the UI (web-ui.md §4.10 / §4.6).
const GUARD_META: Record<string, { severity: string; action: string }> = {
  override: { severity: "high", action: "blocked" },
  exfiltration: { severity: "critical", action: "blocked" },
  "tool-bypass": { severity: "high", action: "blocked" },
  "policy-divergence": { severity: "medium", action: "sent to approval" },
  "secret-leak": { severity: "critical", action: "blocked" },
};

function guardMeta(category: string): { severity: string; action: string } {
  return GUARD_META[category] ?? { severity: "medium", action: "warned" };
}

// Render a log message, wrapping any <REDACTED:…> markers in the redacted span.
// Done by splitting (not dangerouslySetInnerHTML) so the secret marker can never
// be interpreted as live markup. A capturing split keeps the markers as their own
// segments; the non-global test below avoids lastIndex statefulness.
const REDACTED_SPLIT = /(<REDACTED:[^>]+>)/g;
const REDACTED_ONE = /^<REDACTED:[^>]+>$/;

function renderMsg(msg: string): ReactNode[] {
  return msg.split(REDACTED_SPLIT).map((part, i) =>
    REDACTED_ONE.test(part)
      ? <span key={i} className="db-redacted">{part}</span>
      : <Fragment key={i}>{part}</Fragment>,
  );
}

export default function LogsTab() {
  const agent = useCurrentAgent();
  const { data: logLines = [] } = useLogLines();
  const [filter, setFilter] = useState<LogFilter>("all");
  const [query, setQuery] = useState("");

  const maskedCount = useMemo(
    () => logLines.reduce((n, l) => n + (l.msg.match(REDACTED_SPLIT)?.length ?? 0), 0),
    [logLines],
  );

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return logLines.filter((l) => {
      if (filter === "guard" && !l.guard) return false;
      if (q && !(l.msg + " " + l.tag + " " + (l.guard ?? "")).toLowerCase().includes(q)) return false;
      return true;
    });
  }, [logLines, filter, query]);

  return (
    <div className="db-logs">
      <div className="db-toolbar">
        <div className="db-search-inline">
          <Icon name="search" size={15} style={{ color: "var(--mute)" }} />
          <input
            placeholder="Search access & tool logs…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="db-toolbar-r">
          <Segmented
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: "All events" },
              { value: "guard", label: "Guardrail only" },
            ]}
          />
        </div>
      </div>

      <div className="db-redact-summary db-mono">
        <Icon name="shield-check" size={14} />
        {maskedCount} {maskedCount === 1 ? "secret" : "secrets"} masked on the daemon before
        upload for {agent.name} · this UI never receives raw secrets.
      </div>

      <div className="db-log-panel">
        {rows.map((l, i) => {
          const meta = l.guard ? guardMeta(l.guard) : null;
          return (
            <div key={i} className={"db-log-line" + (l.guard ? " guard" : "")}>
              <span className="db-log-time db-mono">{l.time}</span>
              <span className={"db-log-tag " + l.tag}>{l.tag}</span>
              <span className="db-log-msg db-mono">{renderMsg(l.msg)}</span>
              {l.guard && meta && (
                <span className="db-log-guard">
                  <Icon name="shield-alert" size={12} />
                  {l.guard} · {meta.severity} · {meta.action}
                </span>
              )}
            </div>
          );
        })}
        {rows.length === 0 && (
          <div className="db-muted db-mono" style={{ padding: 16 }}>
            {filter === "guard" ? "No guardrail events for this run." : "No matching log lines."}
          </div>
        )}
      </div>
    </div>
  );
}
