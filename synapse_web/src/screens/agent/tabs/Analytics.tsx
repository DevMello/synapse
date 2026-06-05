// Agent Detail — Analytics tab. Deep per-agent analytics: tokens (in/out over
// time), spend per day/model, runs completed, tool-call counts + latency, and
// cost breakdowns by model/daemon with trend comparisons to baselines.
//
// The cloud serves analytics rollups; here we synthesize illustrative 7-day
// series (per the prototype) and derive what we can from this agent's runs.
// Time-series + columns are Recharts; the breakdown bars keep the on-system
// `.db-breakdown*` markup, which is a clean fit for the share-of-cost rows.
import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";
import { useCurrentAgent } from "../context";
import { useRuns } from "../../../api/queries";
import { MetricCard } from "../../../components/Common";

const ACCENT = "#ef6a2a";
const ACCENT_DEEP = "#d44a14";
const ACCENT_SOFT = "#f59264";
const MUTE = "#8a8378";
const LINE = "rgba(12, 11, 9, 0.08)";

const LABELS = ["Th", "Fr", "Sa", "Su", "Mo", "Tu", "We"];

// Illustrative per-day series (millions of tokens, USD, seconds/run). Real data
// arrives via the cloud's analytics rollups; the shape stays the same.
const TOKENS = [0.9, 1.2, 0.8, 1.6, 1.4, 1.9, 1.84];
const SPEND = [3.1, 4.0, 2.8, 5.2, 4.6, 6.0, 4.82];
const LATENCY = [4.2, 3.8, 5.1, 4.6, 3.9, 4.4, 4.1];

type Breakdown = { name: string; pct: number; color: string };

const COST_BY_MODEL: Breakdown[] = [
  { name: "claude-sonnet-4", pct: 68, color: ACCENT },
  { name: "claude-haiku-4", pct: 20, color: ACCENT_SOFT },
  { name: "gpt-5-codex", pct: 12, color: ACCENT_DEEP },
];

const TOOL_CALLS: Breakdown[] = [
  { name: "git", pct: 42, color: ACCENT },
  { name: "fetch", pct: 31, color: ACCENT_SOFT },
  { name: "fs", pct: 18, color: ACCENT_DEEP },
  { name: "shell", pct: 9, color: MUTE },
];

// Tooltip skinned to the on-system palette — Recharts' default chrome is too loud.
function ChartTooltip({ active, payload, label, unit }: TooltipProps<number, string> & { unit?: string }) {
  if (!active || !payload || payload.length === 0) return null;
  const v = payload[0].value;
  return (
    <div
      className="db-mono"
      style={{
        background: "var(--paper)",
        border: "1px solid var(--line-light)",
        borderRadius: 10,
        padding: "6px 10px",
        fontSize: 12,
        color: "var(--ink)",
        boxShadow: "0 4px 16px rgba(12,11,9,0.08)",
      }}
    >
      <span style={{ color: "var(--mute)" }}>{label}</span>{" "}
      {unit === "$" ? "$" : ""}{v}{unit && unit !== "$" ? ` ${unit}` : ""}
    </div>
  );
}

const AXIS_TICK = { fontFamily: "var(--font-mono)", fontSize: 10.5, fill: MUTE };

function BreakdownBars({ rows }: { rows: Breakdown[] }) {
  return (
    <div className="db-breakdown">
      {rows.map((r) => (
        <div key={r.name} className="db-breakdown-row">
          <span className="db-breakdown-label db-mono">{r.name}</span>
          <div className="db-breakdown-track">
            <div className="db-breakdown-fill" style={{ width: r.pct + "%", background: r.color }} />
          </div>
          <span className="db-breakdown-pct db-mono">{r.pct}%</span>
        </div>
      ))}
    </div>
  );
}

export default function AnalyticsTab() {
  const agent = useCurrentAgent();
  const { data: allRuns } = useRuns();

  // Derive what we can from this agent's real runs; fall back to summary fields.
  const runs = useMemo(
    () => (allRuns ?? []).filter((r) => r.agentId === agent.id),
    [allRuns, agent.id],
  );

  const runsByDay = useMemo(() => {
    // Spread this agent's runs across the 7-day window for an illustrative
    // "runs completed / day" column chart, anchored on the total it reports.
    const total = agent.runsTotal || runs.length;
    const weights = [0.11, 0.16, 0.1, 0.18, 0.15, 0.17, 0.13];
    return LABELS.map((day, i) => ({ day, runs: Math.max(1, Math.round(total * weights[i])) }));
  }, [agent.runsTotal, runs.length]);

  const tokenSeries = useMemo(() => LABELS.map((day, i) => ({ day, tokens: TOKENS[i] })), []);
  const spendSeries = useMemo(() => LABELS.map((day, i) => ({ day, spend: SPEND[i] })), []);
  const latencySeries = useMemo(() => LABELS.map((day, i) => ({ day, latency: LATENCY[i] })), []);

  return (
    <div className="db-analytics">
      <div className="db-metric-grid">
        <MetricCard label="Tokens (7d)" n="9.6" unit="M" delta="+14% vs prior week" dir="up" />
        <MetricCard label="Spend (7d)" n="$30.5" delta="+8% vs prior week" dir="up" />
        <MetricCard label="Avg latency" n="4.1" unit="s" delta="−0.3s vs baseline" dir="up" />
        <MetricCard label="Tool calls" n="1,204" delta="git, fetch, fs top 3" />
      </div>

      <div className="db-chart-grid">
        <div className="db-panel">
          <div className="db-panel-head">
            <h3 className="db-panel-title">
              Tokens / day <span className="db-mono db-muted">millions</span>
            </h3>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={tokenSeries} margin={{ top: 8, right: 4, bottom: 0, left: -22 }}>
              <CartesianGrid vertical={false} stroke={LINE} />
              <XAxis dataKey="day" tickLine={false} axisLine={false} tick={AXIS_TICK} />
              <YAxis tickLine={false} axisLine={false} tick={AXIS_TICK} width={44} />
              <Tooltip cursor={{ fill: "rgba(239,106,42,0.06)" }} content={<ChartTooltip unit="M" />} />
              <Bar dataKey="tokens" fill={ACCENT} radius={[6, 6, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="db-panel">
          <div className="db-panel-head">
            <h3 className="db-panel-title">
              Spend / day <span className="db-mono db-muted">USD</span>
            </h3>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={spendSeries} margin={{ top: 8, right: 4, bottom: 0, left: -22 }}>
              <CartesianGrid vertical={false} stroke={LINE} />
              <XAxis dataKey="day" tickLine={false} axisLine={false} tick={AXIS_TICK} />
              <YAxis tickLine={false} axisLine={false} tick={AXIS_TICK} width={44} />
              <Tooltip cursor={{ fill: "rgba(239,106,42,0.06)" }} content={<ChartTooltip unit="$" />} />
              <Bar dataKey="spend" fill={ACCENT_DEEP} radius={[6, 6, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="db-chart-grid">
        <div className="db-panel">
          <div className="db-panel-head">
            <h3 className="db-panel-title">
              Latency trend <span className="db-mono db-muted">seconds / run</span>
            </h3>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={latencySeries} margin={{ top: 8, right: 8, bottom: 0, left: -22 }}>
              <CartesianGrid vertical={false} stroke={LINE} />
              <XAxis dataKey="day" tickLine={false} axisLine={false} tick={AXIS_TICK} />
              <YAxis tickLine={false} axisLine={false} tick={AXIS_TICK} width={44} domain={["dataMin - 1", "dataMax + 1"]} />
              <Tooltip cursor={{ stroke: LINE }} content={<ChartTooltip unit="s" />} />
              <Line
                type="monotone"
                dataKey="latency"
                stroke={ACCENT}
                strokeWidth={2}
                dot={{ r: 2.5, fill: ACCENT, strokeWidth: 0 }}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="db-panel">
          <div className="db-panel-head">
            <h3 className="db-panel-title">
              Runs / day <span className="db-mono db-muted">completed</span>
            </h3>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={runsByDay} margin={{ top: 8, right: 4, bottom: 0, left: -22 }}>
              <CartesianGrid vertical={false} stroke={LINE} />
              <XAxis dataKey="day" tickLine={false} axisLine={false} tick={AXIS_TICK} />
              <YAxis tickLine={false} axisLine={false} tick={AXIS_TICK} width={44} allowDecimals={false} />
              <Tooltip cursor={{ fill: "rgba(239,106,42,0.06)" }} content={<ChartTooltip />} />
              <Bar dataKey="runs" fill={ACCENT_SOFT} radius={[6, 6, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="db-chart-grid">
        <div className="db-panel">
          <div className="db-panel-head">
            <h3 className="db-panel-title">Cost by model</h3>
          </div>
          <BreakdownBars rows={COST_BY_MODEL} />
        </div>

        <div className="db-panel">
          <div className="db-panel-head">
            <h3 className="db-panel-title">Tool calls by type</h3>
          </div>
          <BreakdownBars rows={TOOL_CALLS} />
        </div>
      </div>
    </div>
  );
}
