// DB row → UI view-model for Model Comparison Runs (§10). The run_groups / comparison
// columns are not in the generated Database types yet (migration 0020 isn't applied to
// live), so rows are typed loosely here; the live read path casts the Supabase client.
import type {
  ComparisonVariant,
  ProposedAction,
  RunGroup,
  RunGroupStatus,
  VariantStatus,
} from "../../types";
import { relativeTime } from "../format";

type Row = Record<string, unknown>;

function num(v: unknown, d = 0): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
}

export function toProposedAction(raw: Row): ProposedAction {
  return {
    name: String(raw.name ?? ""),
    argsRedacted: raw.args_redacted ?? raw.argsRedacted ?? null,
    hitl: Boolean(raw.hitl),
  };
}

export function toVariant(row: Row): ComparisonVariant {
  return {
    runId: String(row.run_id ?? row.id ?? ""),
    model: String(row.variant_model ?? row.model ?? ""),
    status: (String(row.status ?? "running") as VariantStatus),
    costUsd: num(row.cost_usd),
    tokensIn: num(row.tokens_in),
    tokensOut: num(row.tokens_out),
    latencyMs: row.latency_ms != null ? num(row.latency_ms) : undefined,
    output: String(row.output ?? ""),
    error: (row.error as string | null) ?? null,
    toolCalls: Array.isArray(row.tool_calls)
      ? (row.tool_calls as Row[]).map((t) => ({
          name: String(t.name ?? ""),
          simulated: Boolean(t.simulated),
        }))
      : [],
    proposedActions: Array.isArray(row.proposed_actions)
      ? (row.proposed_actions as Row[]).map(toProposedAction)
      : [],
    simulatedHitl: Array.isArray(row.simulated_hitl)
      ? (row.simulated_hitl as Row[]).map((h) => ({
          name: String(h.name ?? ""),
          argsRedacted: h.args_redacted ?? null,
        }))
      : [],
    isWinner: Boolean(row.is_winner),
  };
}

export function toRunGroup(row: Row, variants: ComparisonVariant[] = []): RunGroup {
  return {
    id: String(row.id ?? row.group_id ?? ""),
    agentId: String(row.agent_id ?? ""),
    status: (String(row.status ?? "running") as RunGroupStatus),
    models: Array.isArray(row.selected_models)
      ? (row.selected_models as string[])
      : Array.isArray(row.models)
        ? (row.models as string[])
        : [],
    totalCostUsd: num(row.total_cost_usd ?? row.total_cost),
    groupCostCap: (row.group_cost_cap as number | null) ?? null,
    winnerRunId: (row.winner_run_id as string | null) ?? null,
    created: row.created_at ? relativeTime(String(row.created_at)) : "just now",
    variants,
  };
}
