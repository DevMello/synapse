// DB row → UI view-model. type/status enum mapping; rollups from view columns.
import type { Database } from "../../lib/database.types";
import type { Agent, AgentStatus } from "../../types";
import { relativeTime } from "../format";

type AgentOverviewRow = Database["public"]["Views"]["agent_overview"]["Row"];

const AGENT_STATUS: Record<Database["public"]["Enums"]["agent_status"], AgentStatus> = {
  active: "running",
  paused: "idle",
  archived: "offline",
};

export function toAgent(row: AgentOverviewRow): Agent {
  return {
    id: row.id ?? "",
    name: row.name ?? "",
    type: row.type === "cli" ? "CLI tool" : "API model",
    engine: row.engine ?? "API",
    daemonId: row.daemon_id ?? "",
    status: row.status ? AGENT_STATUS[row.status] : "idle",
    avail: row.status === "active",
    lastRun: row.last_run_at ? relativeTime(row.last_run_at) : "never",
    nextRun: row.next_run_at
      ? relativeTime(row.next_run_at)
      : row.has_webhook
        ? "on webhook"
        : "manual",
    spendToday: Number(row.spend_today ?? 0),
    runsTotal: Number(row.runs_total ?? 0),
    errRate: Number(row.err_rate ?? 0),
    tokensToday: Number(row.tokens_today ?? 0),
    model: row.model ?? "",
    desc: row.description ?? "",
  };
}
