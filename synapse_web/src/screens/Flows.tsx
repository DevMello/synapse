// Flow library (§11.11) — the home for handoff chains. New flow, start from a template,
// then open one on the visual canvas. Each card shows the chain shape at a glance and the
// signed/draft status. Archived flows are hidden.
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Icon } from "../components/Primitives";
import { PageHead } from "../components/Common";
import { useUI } from "../store/ui";
import { useAgents, useArchiveFlow, useCreateFlow, useFlows } from "../api/queries";
import type { Agent, AgentFlow } from "../types";
import { blankFlow, draftReviewPublish, plannerCriticExecutor } from "./flow/templates";
import "../styles/flow-canvas.css";

export default function Flows() {
  const navigate = useNavigate();
  const showToast = useUI((s) => s.showToast);
  const { data: flows = [], isLoading } = useFlows();
  const { data: agents = [] } = useAgents();
  const create = useCreateFlow();
  const archive = useArchiveFlow();

  // The daemon with the most non-production agents seeds the templates (H2 single-daemon).
  const seed = useMemo(() => pickDaemonAgents(agents), [agents]);

  function open(flow: AgentFlow) {
    navigate(`/flows/${flow.id}`);
  }

  function createAndOpen(flow: AgentFlow) {
    create.mutate(flow, {
      onSuccess: (f) => navigate(`/flows/${f.id}`),
      onError: (e) => showToast({ text: (e as Error).message, variant: "warn" }),
    });
  }

  return (
    <div className="db-screen">
      <PageHead
        kicker="Native Handoff Protocol"
        title="Flow"
        serif="Canvas"
        sub="Author agent handoff chains on a visual canvas. Publishing signs a chain grant the daemon enforces locally — a baton-pass, not new authority."
        actions={
          <Button variant="primary" icon="plus" onClick={() => createAndOpen(blankFlow("Untitled flow", seed.daemonId))}>
            New flow
          </Button>
        }
      />

      {/* ── templates ──────────────────────────────────────────────── */}
      <div className="fl-templates">
        <span className="fl-templates-label">Start from a template</span>
        <button className="fl-tmpl" onClick={() => createAndOpen(plannerCriticExecutor(seed.agents, seed.daemonId))}>
          <span className="fl-tmpl-shape"><b /><i /><b /><i /><b /></span>
          <span className="fl-tmpl-name">Planner ▸ Critic ▸ Executor</span>
          <span className="fl-tmpl-sub">A plan, a review loop, then execution</span>
        </button>
        <button className="fl-tmpl" onClick={() => createAndOpen(draftReviewPublish(seed.agents, seed.daemonId))}>
          <span className="fl-tmpl-shape"><b /><i /><b className="loop" /><i /><b /></span>
          <span className="fl-tmpl-name">Draft ▸ Review-loop ▸ Publish</span>
          <span className="fl-tmpl-sub">Iterate with a critic, then ship</span>
        </button>
      </div>

      {/* ── library ────────────────────────────────────────────────── */}
      {isLoading ? (
        <div className="db-mono db-muted" style={{ padding: 16 }}>Loading flows…</div>
      ) : flows.length === 0 ? (
        <div className="fl-empty">
          <Icon name="git-branch" size={26} />
          <p>No flows yet — start from a template or a blank canvas.</p>
        </div>
      ) : (
        <div className="fl-grid">
          {flows.map((f) => (
            <FlowCard key={f.id} flow={f} agents={agents} onOpen={() => open(f)}
              onArchive={() => archive.mutate(f.id, { onSuccess: () => showToast({ text: "Flow archived" }) })} />
          ))}
        </div>
      )}
    </div>
  );
}

function FlowCard({
  flow, agents, onOpen, onArchive,
}: {
  flow: AgentFlow;
  agents: Agent[];
  onOpen: () => void;
  onArchive: () => void;
}) {
  const agentNodes = flow.nodes.filter((n) => n.kind === "agent");
  const names = agentNodes
    .map((n) => agents.find((a) => a.id === n.agentId)?.name ?? n.label)
    .slice(0, 4);
  return (
    <div className="fl-card" onClick={onOpen}>
      <div className="fl-card-head">
        <h3 className="fl-card-name">{flow.name}</h3>
        <span className={"fc-status fc-status--" + flow.status}>{flow.status}</span>
      </div>
      <div className="fl-card-chain">
        {names.map((n, i) => (
          <span key={i} className="fl-chip">
            {n}
            {i < names.length - 1 && <Icon name="arrow-right" size={12} />}
          </span>
        ))}
      </div>
      <div className="fl-card-foot">
        <span><Icon name="server" size={12} /> {flow.daemonId ?? "—"}</span>
        <span>{agentNodes.length} agents · {flow.edges.length} edges</span>
        <span className="fl-card-time">updated {flow.updated}</span>
      </div>
      <button
        className="fl-card-archive"
        title="Archive"
        onClick={(e) => { e.stopPropagation(); onArchive(); }}
      >
        <Icon name="archive" size={14} />
      </button>
    </div>
  );
}

function pickDaemonAgents(agents: Agent[]): { daemonId?: string; agents: { agentId: string; label: string }[] } {
  const byDaemon = new Map<string, Agent[]>();
  for (const a of agents) {
    if ((a.tags ?? []).includes("production")) continue;
    const arr = byDaemon.get(a.daemonId) ?? [];
    arr.push(a);
    byDaemon.set(a.daemonId, arr);
  }
  let best: { daemonId?: string; list: Agent[] } = { list: [] };
  for (const [daemonId, list] of byDaemon) {
    if (list.length > best.list.length) best = { daemonId, list };
  }
  const labels = ["Planner", "Critic", "Executor"];
  return {
    daemonId: best.daemonId,
    agents: best.list.slice(0, 3).map((a, i) => ({ agentId: a.id, label: labels[i] ?? a.name })),
  };
}
