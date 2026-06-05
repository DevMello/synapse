import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon, Chip } from "../components/Primitives";
import { PageHead, MetricCard, Segmented } from "../components/Common";
import { useRuns } from "../api/queries";
import type { Run, RunStatus, RunTrigger } from "../types";

// Global Runs — fleet-wide run history across every agent. Toolbar offers a status
// filter, a trigger filter, and inline search; rows drill into the owning agent's
// Runs tab (deep-linked to the specific run). Summary cards sit above the table.

type StatusFilter = "all" | RunStatus;
type TriggerFilter = "all" | RunTrigger;

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "running", label: "Running" },
  { value: "blocked", label: "Blocked" },
  { value: "passed", label: "Passed" },
  { value: "recovering", label: "Recovering" },
];

const TRIGGER_OPTIONS: { value: TriggerFilter; label: string }[] = [
  { value: "all", label: "Any trigger" },
  { value: "schedule", label: "Schedule" },
  { value: "webhook", label: "Webhook" },
  { value: "manual", label: "Manual" },
];

const TRIGGER_ICON: Record<RunTrigger, string> = {
  schedule: "clock",
  webhook: "webhook",
  manual: "play",
};

// "Today" is anything that hasn't rolled past an hours-ago marker — the mock data
// uses relative timestamps, so we treat sec/min/hr-ago as within the current day.
function isToday(started: string): boolean {
  return /\b(sec|min|hr|hour)s?\b/.test(started) || started === "just now";
}

export default function Runs() {
  const navigate = useNavigate();
  const { data: runs = [] } = useRuns();

  const [status, setStatus] = useState<StatusFilter>("all");
  const [trigger, setTrigger] = useState<TriggerFilter>("all");
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return runs.filter((r) => {
      if (status !== "all" && r.status !== status) return false;
      if (trigger !== "all" && r.trigger !== trigger) return false;
      if (q) {
        const hay = `${r.id} ${r.agent} ${r.trigger} ${r.exit}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [runs, status, trigger, query]);

  const metrics = useMemo(() => {
    const active = runs.filter((r) => r.status === "running" || r.status === "recovering").length;
    const today = runs.filter((r) => isToday(r.started));
    const spendToday = today.reduce((sum, r) => sum + r.cost, 0);
    const tokensToday = today.reduce((sum, r) => sum + r.tokens, 0);
    return { active, runsToday: today.length, spendToday, tokensToday };
  }, [runs]);

  const openRun = (run: Run) =>
    navigate(`/agents/${run.agentId}?tab=runs&runId=${run.id}`);

  const openAgent = (run: Run) => navigate(`/agents/${run.agentId}`);

  return (
    <>
      <PageHead
        kicker="Runs"
        title="Every run,"
        serif="across all agents"
        sub="Trigger source, status, duration, cost, tokens, and exit. Drill into any run for its live or replayed trace."
      />

      <div className="db-metric-grid">
        <MetricCard label="Active runs" n={metrics.active} sub="running or recovering" />
        <MetricCard label="Runs today" n={metrics.runsToday} sub="across the fleet" />
        <MetricCard label="Spend today" n={`$${metrics.spendToday.toFixed(2)}`} sub="all agents" />
        <MetricCard label="Tokens today" n={`${(metrics.tokensToday / 1000).toFixed(0)}k`} sub="in + out" />
      </div>

      <div className="db-toolbar">
        <div className="db-search-inline">
          <Icon name="search" size={15} style={{ color: "var(--mute)" }} />
          <input
            placeholder="Search runs by id, agent, trigger, or exit…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="db-toolbar-r">
          <Segmented<TriggerFilter> value={trigger} onChange={setTrigger} options={TRIGGER_OPTIONS} />
          <Segmented<StatusFilter> value={status} onChange={setStatus} options={STATUS_OPTIONS} />
        </div>
      </div>

      <div className="db-table-wrap">
        <table className="db-table">
          <thead>
            <tr>
              <th>Run</th>
              <th>Agent</th>
              <th>Trigger</th>
              <th>Started</th>
              <th>Duration</th>
              <th>Tokens</th>
              <th>Cost</th>
              <th>Exit</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.id} className="clickable-row" onClick={() => openRun(r)}>
                <td className="db-cell-primary db-mono">#{r.id.replace("r", "")}</td>
                <td>
                  <button
                    className="db-link"
                    onClick={(e) => {
                      e.stopPropagation();
                      openAgent(r);
                    }}
                  >
                    {r.agent}
                  </button>
                </td>
                <td className="db-mono">
                  <Icon name={TRIGGER_ICON[r.trigger]} size={13} style={{ color: "var(--mute)", marginRight: 6 }} />
                  {r.trigger}
                </td>
                <td className="db-mono">{r.started}</td>
                <td className="db-mono">{r.dur}</td>
                <td className="db-mono">{(r.tokens / 1000).toFixed(0)}k</td>
                <td className="db-mono">${r.cost.toFixed(2)}</td>
                <td className="db-mono">{r.exit}</td>
                <td><Chip s={r.status} /></td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={9} className="db-muted" style={{ textAlign: "center", padding: "28px 0" }}>
                  No runs match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
