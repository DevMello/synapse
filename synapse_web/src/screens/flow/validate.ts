// Build-time flow validation (§11.11) — the §11 envelope as an authoring guardrail.
// Pure: takes the flow + a resolver for agent metadata, returns issues keyed to the
// offending node/edge so the canvas can highlight them. Invalid flows can't be published.
import type { AgentFlow, FlowEdge } from "../../types";

export interface FlowIssue {
  level: "error" | "warn";
  message: string;
  nodeId?: string;
  edgeId?: string;
}

export interface AgentMeta {
  name: string;
  daemonId: string;
  tags?: string[];
}

export type AgentResolver = (agentId: string) => AgentMeta | undefined;

export function validateFlow(flow: AgentFlow, resolve: AgentResolver): FlowIssue[] {
  const issues: FlowIssue[] = [];
  const nodeById = new Map(flow.nodes.map((n) => [n.id, n]));
  const agentNodes = flow.nodes.filter((n) => n.kind === "agent");

  // Every agent node must resolve to a real agent.
  const daemons = new Set<string>();
  for (const n of agentNodes) {
    const a = n.agentId ? resolve(n.agentId) : undefined;
    if (!a) {
      issues.push({ level: "error", nodeId: n.id, message: "Node has no assigned agent." });
      continue;
    }
    daemons.add(a.daemonId);
    if ((a.tags ?? []).includes("production")) {
      issues.push({
        level: "error",
        nodeId: n.id,
        message: `${a.name} is production-tagged — excluded from chain nodes (§4).`,
      });
    }
  }

  // H2 — all agent nodes on a single daemon.
  if (daemons.size > 1) {
    for (const n of agentNodes) {
      issues.push({
        level: "error",
        nodeId: n.id,
        message: "All agents in a chain must share one daemon (H2: daemon-local).",
      });
    }
  }

  // Edges must connect existing nodes; agent→agent edges are what gets signed.
  const agentEdges: FlowEdge[] = [];
  for (const e of flow.edges) {
    const from = nodeById.get(e.from);
    const to = nodeById.get(e.to);
    if (!from || !to) {
      issues.push({ level: "error", edgeId: e.id, message: "Edge has a dangling endpoint." });
      continue;
    }
    if (from.kind === "agent" && to.kind === "agent") agentEdges.push(e);
  }
  if (agentEdges.length === 0) {
    issues.push({
      level: "error",
      message: "Wire at least one agent → agent handoff before publishing.",
    });
  }

  // H7 — multiple unconditional tail out-edges from one node looks like concurrent
  // fan-out (orchestration territory). A router needs `when` conditions to pick ONE.
  const outByNode = new Map<string, FlowEdge[]>();
  for (const e of flow.edges) {
    const arr = outByNode.get(e.from) ?? [];
    arr.push(e);
    outByNode.set(e.from, arr);
  }
  for (const [nid, outs] of outByNode) {
    const node = nodeById.get(nid);
    if (!node || node.kind !== "agent") continue;
    const unconditionalTails = outs.filter((e) => e.mode === "tail" && !e.when);
    if (outs.length > 1 && unconditionalTails.length > 1) {
      issues.push({
        level: "warn",
        nodeId: nid,
        message:
          "Multiple unconditional successors = a router needs conditions, or this is fan-out → promote to Orchestration (§2).",
      });
    }
  }

  return issues;
}

export function compileAgentEdges(
  flow: AgentFlow,
): { from: string; to: string; mode: string; when?: string | null }[] {
  const nodeById = new Map(flow.nodes.map((n) => [n.id, n]));
  const out: { from: string; to: string; mode: string; when?: string | null }[] = [];
  for (const e of flow.edges) {
    const from = nodeById.get(e.from);
    const to = nodeById.get(e.to);
    if (from?.kind === "agent" && to?.kind === "agent" && from.agentId && to.agentId) {
      out.push({ from: from.agentId, to: to.agentId, mode: e.mode, when: e.when ?? null });
    }
  }
  return out;
}

export function hasErrors(issues: FlowIssue[]): boolean {
  return issues.some((i) => i.level === "error");
}

export function issueFor(issues: FlowIssue[], id: string): FlowIssue | undefined {
  return issues.find((i) => i.nodeId === id || i.edgeId === id);
}
