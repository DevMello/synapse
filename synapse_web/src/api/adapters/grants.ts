// DB row → UI view-model for orchestration grants.
import type { Database } from "../../lib/database.types";
import type { Grant, GrantVerb } from "../../types";
import { relativeTime } from "../format";

type GrantRow = Database["public"]["Tables"]["agent_orchestration_grants"]["Row"];

export function toGrant(row: GrantRow): Grant {
  return {
    id: row.id,
    agentId: row.agent_id,
    daemonId: row.daemon_id,
    verbs: (row.verbs ?? []) as GrantVerb[],
    targetAllow: row.target_allow ?? [],
    maxDepth: row.max_depth ?? 0,
    maxFanOut: row.max_fan_out ?? 0,
    treeBudgetUsd: Number(row.tree_budget_usd ?? 0),
    expiresAt: relativeTime(row.expires_at),
    revoked: row.revoked_at != null,
    grantedBy: row.granted_by ?? "—",
    created: relativeTime(row.created_at),
  };
}
