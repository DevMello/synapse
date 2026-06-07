// DB row → UI view-model. Param includes the embedded agent (runs ⋈ agents).
import type { Database } from "../../lib/database.types";
import type { Run, RunStatus, RunTrigger } from "../../types";
import { relativeTime } from "../format";

type RunRow = Database["public"]["Tables"]["runs"]["Row"] & {
  agents: { name: string } | null;
};

const TRIGGER: Record<Database["public"]["Enums"]["trigger_source"], RunTrigger> = {
  manual: "manual",
  schedule: "schedule",
  webhook: "webhook",
  recovery: "manual",
};

const STATUS: Record<Database["public"]["Enums"]["run_status"], RunStatus> = {
  pending: "running",
  running: "running",
  succeeded: "passed",
  failed: "blocked",
  cancelled: "blocked",
  interrupted: "blocked",
  recovering: "recovering",
  resumed: "recovering",
};

function formatDuration(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const totalSec = Math.round(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

export function toRun(row: RunRow): Run {
  return {
    id: row.id,
    agentId: row.agent_id,
    agent: row.agents?.name ?? "—",
    trigger: TRIGGER[row.trigger],
    status: STATUS[row.status],
    started: row.started_at ? relativeTime(row.started_at) : "—",
    dur: formatDuration(row.started_at, row.ended_at),
    cost: Number(row.cost_usd ?? 0),
    tokens: Number(row.tokens_in ?? 0) + Number(row.tokens_out ?? 0),
    exit: row.exit_code != null ? String(row.exit_code) : "—",
  };
}
