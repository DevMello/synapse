// DB row → UI view-model for handoff flows + chain grants (§11).
import type { Database } from "../../lib/database.types";
import type {
  AgentFlow,
  ChainGrant,
  FlowEdge,
  FlowNode,
  FlowSettings,
  HandoffMode,
} from "../../types";
import { relativeTime } from "../format";

type FlowRow = Database["public"]["Tables"]["agent_flows"]["Row"];
type GrantRow = Database["public"]["Tables"]["agent_chain_grants"]["Row"];

const DEFAULT_SETTINGS: FlowSettings = {
  maxHops: 8,
  chainBudgetUsd: 5.0,
  maxPayloadBytes: 32768,
  modes: ["tail", "return"],
  routing: "first_match",
};

export function toFlowSettings(raw: unknown): FlowSettings {
  const s = (raw ?? {}) as Record<string, unknown>;
  return {
    maxHops: Number(s.max_hops ?? s.maxHops ?? DEFAULT_SETTINGS.maxHops),
    chainBudgetUsd: Number(s.chain_budget_usd ?? s.chainBudgetUsd ?? DEFAULT_SETTINGS.chainBudgetUsd),
    maxPayloadBytes: Number(s.max_payload_bytes ?? s.maxPayloadBytes ?? DEFAULT_SETTINGS.maxPayloadBytes),
    modes: (Array.isArray(s.modes) ? s.modes : DEFAULT_SETTINGS.modes) as HandoffMode[],
    routing: "first_match",
  };
}

export function toFlow(row: FlowRow): AgentFlow {
  return {
    id: row.id,
    daemonId: row.daemon_id ?? undefined,
    name: row.name,
    version: row.version,
    status: row.status as AgentFlow["status"],
    nodes: (row.nodes ?? []) as unknown as FlowNode[],
    edges: (row.edges ?? []) as unknown as FlowEdge[],
    settings: toFlowSettings(row.settings),
    publishedGrantId: row.published_grant_id,
    created: relativeTime(row.created_at),
    updated: relativeTime(row.updated_at),
  };
}

// AgentFlow → the jsonb columns we persist (settings stored snake_case for the daemon).
export function flowToRow(flow: AgentFlow): Partial<FlowRow> {
  return {
    name: flow.name,
    daemon_id: flow.daemonId ?? null,
    status: flow.status,
    version: flow.version,
    nodes: flow.nodes as unknown as Database["public"]["Tables"]["agent_flows"]["Row"]["nodes"],
    edges: flow.edges as unknown as Database["public"]["Tables"]["agent_flows"]["Row"]["edges"],
    settings: {
      max_hops: flow.settings.maxHops,
      chain_budget_usd: flow.settings.chainBudgetUsd,
      max_payload_bytes: flow.settings.maxPayloadBytes,
      modes: flow.settings.modes,
      routing: flow.settings.routing,
    } as unknown as Database["public"]["Tables"]["agent_flows"]["Row"]["settings"],
  };
}

export function toChainGrant(row: GrantRow): ChainGrant {
  return {
    id: row.id,
    daemonId: row.daemon_id,
    flowId: row.flow_id ?? undefined,
    edges: (row.edges ?? []) as ChainGrant["edges"],
    routing: row.routing,
    maxHops: row.max_hops,
    chainBudgetUsd: Number(row.chain_budget_usd),
    maxPayloadBytes: row.max_payload_bytes,
    modes: (row.modes ?? []) as HandoffMode[],
    expiresAt: relativeTime(row.expires_at),
    revoked: row.revoked_at != null,
    grantedBy: row.granted_by ?? "—",
    created: relativeTime(row.created_at),
  };
}
