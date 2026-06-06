// DB row → UI view-model. severity from hitl_severity; command/reason/context from
// the context jsonb; agent/daemon names from joins.
import type { Database } from "../../lib/database.types";
import type { Approval } from "../../types";
import { relativeTime } from "../format";

type HitlRow = Database["public"]["Tables"]["hitl_requests"]["Row"] & {
  agents: { name: string } | null;
  daemons: { name: string } | null;
};

export function toApproval(row: HitlRow): Approval {
  const ctx = (row.context ?? {}) as {
    command?: string;
    reason?: string;
    context_label?: string;
    context?: string;
  };
  return {
    id: row.id,
    agentId: row.agent_id ?? "",
    agent: row.agents?.name ?? "—",
    daemon: row.daemons?.name ?? "—",
    severity: row.severity,
    action: row.action,
    command: ctx.command ?? "",
    reason: ctx.reason ?? "",
    context: ctx.context_label ?? ctx.context ?? "",
    when: relativeTime(row.created_at),
  };
}
