// Flow templates + the offline mock seed (§11.11 "start from a template"). Pure data —
// no React — so it can be imported by both the API layer (mock seed) and the library UI.
import type { AgentFlow, FlowEdge, FlowNode, FlowSettings } from "../../types";

export const DEFAULT_SETTINGS: FlowSettings = {
  maxHops: 8,
  chainBudgetUsd: 5.0,
  maxPayloadBytes: 32768,
  modes: ["tail", "return"],
  routing: "first_match",
};

let _seq = 0;
export function nodeId(): string {
  return `n${(_seq++).toString(36)}_${Math.random().toString(16).slice(2, 6)}`;
}
export function edgeId(): string {
  return `e${(_seq++).toString(36)}_${Math.random().toString(16).slice(2, 6)}`;
}

export function blankFlow(name = "Untitled flow", daemonId?: string): AgentFlow {
  const start: FlowNode = { id: nodeId(), kind: "start", label: "Start", x: 120, y: 220 };
  return {
    id: `flw_draft_${Math.random().toString(16).slice(2, 8)}`,
    daemonId,
    name,
    version: 1,
    status: "draft",
    nodes: [start],
    edges: [],
    settings: { ...DEFAULT_SETTINGS },
    created: "just now",
    updated: "just now",
  };
}

interface TemplateAgent {
  agentId: string;
  label: string;
}

/** Planner ▸ Critic ▸ Executor with a critic→planner revision loop (the canonical §11
 *  pipeline). Agents are wired left-to-right; the critic routes onward when approved or
 *  loops back (return mode) when revision is needed. */
export function plannerCriticExecutor(agents: TemplateAgent[], daemonId?: string): AgentFlow {
  const [planner, critic, executor] = agents;
  const start: FlowNode = { id: nodeId(), kind: "start", label: "Start", x: 100, y: 260 };
  const nPlanner: FlowNode = { id: nodeId(), kind: "agent", agentId: planner?.agentId, label: "Planner", x: 320, y: 180 };
  const nCritic: FlowNode = { id: nodeId(), kind: "agent", agentId: critic?.agentId, label: "Critic", x: 580, y: 180 };
  const nExec: FlowNode = { id: nodeId(), kind: "agent", agentId: executor?.agentId, label: "Executor", x: 840, y: 180 };
  const end: FlowNode = { id: nodeId(), kind: "end", label: "End", x: 1080, y: 260 };

  const edges: FlowEdge[] = [
    { id: edgeId(), from: start.id, to: nPlanner.id, mode: "tail" },
    { id: edgeId(), from: nPlanner.id, to: nCritic.id, mode: "tail" },
    { id: edgeId(), from: nCritic.id, to: nExec.id, mode: "tail", when: "approved" },
    { id: edgeId(), from: nCritic.id, to: nPlanner.id, mode: "return", when: "needs_revision" },
    { id: edgeId(), from: nExec.id, to: end.id, mode: "tail" },
  ];
  return {
    id: `flw_draft_${Math.random().toString(16).slice(2, 8)}`,
    daemonId,
    name: "Planner ▸ Critic ▸ Executor",
    version: 1,
    status: "draft",
    nodes: [start, nPlanner, nCritic, nExec, end],
    edges,
    settings: { ...DEFAULT_SETTINGS, maxHops: 8 },
    created: "just now",
    updated: "just now",
  };
}

/** Draft ▸ Review-loop ▸ Publish — a two-agent critic loop then a publish hop. */
export function draftReviewPublish(agents: TemplateAgent[], daemonId?: string): AgentFlow {
  const [drafter, reviewer] = agents;
  const start: FlowNode = { id: nodeId(), kind: "start", label: "Start", x: 100, y: 240 };
  const nDraft: FlowNode = { id: nodeId(), kind: "agent", agentId: drafter?.agentId, label: "Drafter", x: 340, y: 180 };
  const nRev: FlowNode = { id: nodeId(), kind: "agent", agentId: reviewer?.agentId, label: "Reviewer", x: 620, y: 180 };
  const end: FlowNode = { id: nodeId(), kind: "end", label: "Publish", x: 880, y: 240 };
  const edges: FlowEdge[] = [
    { id: edgeId(), from: start.id, to: nDraft.id, mode: "tail" },
    { id: edgeId(), from: nDraft.id, to: nRev.id, mode: "tail" },
    { id: edgeId(), from: nRev.id, to: nDraft.id, mode: "return", when: "changes_requested" },
    { id: edgeId(), from: nRev.id, to: end.id, mode: "tail", when: "approved" },
  ];
  return {
    id: `flw_draft_${Math.random().toString(16).slice(2, 8)}`,
    daemonId,
    name: "Draft ▸ Review-loop ▸ Publish",
    version: 1,
    status: "draft",
    nodes: [start, nDraft, nRev, end],
    edges,
    settings: { ...DEFAULT_SETTINGS },
    created: "just now",
    updated: "just now",
  };
}

/** A valid, pre-populated flow seeded into the offline mock store so the canvas renders
 *  out-of-the-box (mock agents a-prr + a-bf both live on daemon d-mbp → single-daemon OK). */
export function seedMockFlows(): AgentFlow[] {
  const flow = plannerCriticExecutor(
    [
      { agentId: "a-prr", label: "Planner" },
      { agentId: "a-bf", label: "Critic" },
      { agentId: "a-prr", label: "Executor" },
    ],
    "d-mbp",
  );
  // Trim to a valid two-agent critic loop (a-prr ⇄ a-bf), dropping the duplicate executor.
  flow.id = "flw_demo";
  flow.name = "PR review ▸ critic loop";
  flow.nodes = flow.nodes.filter((n) => n.label !== "Executor" && n.label !== "End");
  const planner = flow.nodes.find((n) => n.label === "Planner")!;
  const critic = flow.nodes.find((n) => n.label === "Critic")!;
  const start = flow.nodes.find((n) => n.kind === "start")!;
  flow.edges = [
    { id: edgeId(), from: start.id, to: planner.id, mode: "tail" },
    { id: edgeId(), from: planner.id, to: critic.id, mode: "tail" },
    { id: edgeId(), from: critic.id, to: planner.id, mode: "return", when: "needs_revision" },
  ];
  flow.created = "2 days ago";
  flow.updated = "20 min ago";
  return [flow];
}
