// DB run rows → a RunLineage tree (orchestration lineage, §2.4).
import type { Database } from "../../lib/database.types";
import type { Run, RunLineage, RunStatus } from "../../types";
import { relativeTime } from "../format";

type RunRow = Database["public"]["Tables"]["runs"]["Row"] & {
  agents: { name: string } | null;
};

const STATUS: Record<string, RunStatus> = {
  pending: "running",
  running: "running",
  succeeded: "passed",
  failed: "blocked",
  cancelled: "blocked",
  interrupted: "blocked",
  recovering: "recovering",
  resumed: "recovering",
};

export function toLineageRun(row: RunRow): Run {
  return {
    id: row.id,
    agentId: row.agent_id,
    agent: row.agents?.name ?? "—",
    trigger: "manual",
    status: STATUS[row.status] ?? "running",
    started: row.started_at ? relativeTime(row.started_at) : "—",
    dur: "—",
    cost: Number(row.cost_usd ?? 0),
    tokens: Number(row.tokens_in ?? 0) + Number(row.tokens_out ?? 0),
    exit: row.exit_code != null ? String(row.exit_code) : "—",
    initiator: (row.initiator as Run["initiator"]) ?? "agent",
    initiatorAgentId: row.initiator_agent_id ?? undefined,
    rootRunId: row.root_run_id ?? undefined,
    parentRunId: row.parent_run_id ?? undefined,
    depth: row.depth ?? 0,
  };
}

/** Build a forest from run rows by parent_run_id; rows whose parent isn't present
 *  in the set become roots (so a partial tree still renders). */
export function buildLineage(rows: RunRow[]): RunLineage[] {
  const nodes = new Map<string, RunLineage>();
  for (const r of rows) nodes.set(r.id, { run: toLineageRun(r), children: [] });
  const roots: RunLineage[] = [];
  for (const node of nodes.values()) {
    const parentId = node.run.parentRunId;
    const parent = parentId ? nodes.get(parentId) : undefined;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  const sortRec = (ns: RunLineage[]) => {
    ns.sort((a, b) => (a.run.depth ?? 0) - (b.run.depth ?? 0));
    ns.forEach((n) => sortRec(n.children));
  };
  sortRec(roots);
  return roots;
}
