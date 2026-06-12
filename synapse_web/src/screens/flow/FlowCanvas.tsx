// The Flow Canvas editor (§11.11) — a bespoke n8n-style drag-and-drop surface for
// authoring agent handoff chains. Pan/zoom infinite canvas, draggable agent nodes,
// output→input wiring with conditional routers, per-edge config, live §11 validation,
// a draft-mode "Test flow" that lights the baton up node-by-node, and publish-to-sign.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Icon } from "../../components/Primitives";
import { ScreenStub } from "../../components/Common";
import { useUI } from "../../store/ui";
import {
  useAgents,
  useFlow,
  usePublishFlow,
  useRevokeChainGrant,
  useSaveFlow,
} from "../../api/queries";
import type { Agent, AgentFlow, FlowNodeKind } from "../../types";
import { useFlowGraph, type FlowGraph } from "./useFlowGraph";
import { validateFlow, issueFor, compileAgentEdges, type AgentMeta } from "./validate";
import { inPort, outPort, screenToWorld, edgePath } from "./canvas/geometry";
import FlowNodeView, { type TraceState } from "./canvas/FlowNode";
import FlowEdgeView from "./canvas/FlowEdge";
import NodePalette from "./canvas/NodePalette";
import Inspector from "./canvas/Inspector";
import Toolbar from "./canvas/Toolbar";
import ConsentModal from "./canvas/ConsentModal";
import TraceBanner from "./canvas/TraceBanner";
import "../../styles/flow-canvas.css";

export default function FlowCanvas() {
  const { flowId } = useParams();
  const { data: flow, isLoading } = useFlow(flowId);
  if (isLoading) return <ScreenStub name="Flow" />;
  if (!flow) return <ScreenStub name="Flow not found" />;
  return <Editor key={flow.id} flow={flow} />;
}

type Interaction =
  | { type: "pan"; lastX: number; lastY: number }
  | { type: "drag"; nodeId: string; offX: number; offY: number }
  | { type: "link"; fromNodeId: string }
  | null;

interface TraceSim {
  draft: boolean;
  rootRunId: string;
  seq: string[]; // node ids in baton order
  idx: number;
  hashes: Record<string, string>; // edgeId → payload hash
  done: boolean;
}

function Editor({ flow }: { flow: AgentFlow }) {
  const navigate = useNavigate();
  const showToast = useUI((s) => s.showToast);
  const graph = useFlowGraph(flow);
  const { data: agents = [] } = useAgents();
  const save = useSaveFlow();
  const publish = usePublishFlow();
  const revoke = useRevokeChainGrant();

  const fcRef = useRef<HTMLDivElement>(null);
  const interaction = useRef<Interaction>(null);
  const cascade = useRef(0);
  const [consent, setConsent] = useState(false);
  const [trace, setTrace] = useState<TraceSim | null>(null);
  const [status, setStatus] = useState(flow.status);

  const agentsById = useMemo(() => {
    const m = new Map<string, Agent>();
    for (const a of agents) m.set(a.id, a);
    return m;
  }, [agents]);

  const resolve = useCallback(
    (id: string): AgentMeta | undefined => {
      const a = agentsById.get(id);
      return a ? { name: a.name, daemonId: a.daemonId, tags: a.tags } : undefined;
    },
    [agentsById],
  );

  const issues = useMemo(() => validateFlow(graph.snapshot, resolve), [graph.snapshot, resolve]);
  const nodeById = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph.nodes]);

  const effectiveDaemon = useMemo(() => {
    const an = graph.nodes.find((n) => n.kind === "agent" && n.agentId);
    return an?.agentId ? agentsById.get(an.agentId)?.daemonId ?? flow.daemonId : flow.daemonId;
  }, [graph.nodes, agentsById, flow.daemonId]);

  // ── native non-passive wheel zoom ───────────────────────────────────────────
  useEffect(() => {
    const el = fcRef.current;
    if (!el) return;
    const h = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      graph.zoomAt(e.deltaY < 0 ? 1.1 : 0.9, e.clientX - rect.left, e.clientY - rect.top);
    };
    el.addEventListener("wheel", h, { passive: false });
    return () => el.removeEventListener("wheel", h);
  }, [graph.zoomAt]);

  // ── draft-run animation (Test flow) ─────────────────────────────────────────
  useEffect(() => {
    if (!trace || trace.done) return;
    const t = setTimeout(() => {
      setTrace((tr) => {
        if (!tr) return tr;
        if (tr.idx >= tr.seq.length - 1) return { ...tr, done: true };
        return { ...tr, idx: tr.idx + 1 };
      });
    }, 900);
    return () => clearTimeout(t);
  }, [trace]);

  function centreWorld(): { x: number; y: number } {
    const el = fcRef.current;
    if (!el) return { x: 200, y: 200 };
    const rect = el.getBoundingClientRect();
    const w = screenToWorld(rect.left + rect.width / 2, rect.top + rect.height / 2, rect, graph.view);
    const off = (cascade.current++ % 5) * 26;
    return { x: w.x - 98 + off, y: w.y - 38 + off };
  }

  // ── pointer interactions ─────────────────────────────────────────────────────
  const onSurfaceDown = (e: React.PointerEvent) => {
    if (e.target !== e.currentTarget && !(e.target as HTMLElement).classList.contains("fc-grid"))
      return;
    graph.clearSelection();
    interaction.current = { type: "pan", lastX: e.clientX, lastY: e.clientY };
    fcRef.current?.setPointerCapture(e.pointerId);
  };

  const onNodeSelect = (id: string) => (e: React.PointerEvent) => {
    e.stopPropagation();
    graph.setSelectedNode(id);
  };

  const onNodeDrag = (id: string) => (e: React.PointerEvent) => {
    e.stopPropagation();
    graph.setSelectedNode(id);
    const n = nodeById.get(id);
    const el = fcRef.current;
    if (!n || !el) return;
    const rect = el.getBoundingClientRect();
    const w = screenToWorld(e.clientX, e.clientY, rect, graph.view);
    interaction.current = { type: "drag", nodeId: id, offX: w.x - n.x, offY: w.y - n.y };
    el.setPointerCapture(e.pointerId);
  };

  const onPortDown = (id: string, e: React.PointerEvent) => {
    const el = fcRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const w = screenToWorld(e.clientX, e.clientY, rect, graph.view);
    interaction.current = { type: "link", fromNodeId: id };
    graph.setLink({ fromNodeId: id, cursor: w });
    el.setPointerCapture(e.pointerId);
  };

  const onMove = (e: React.PointerEvent) => {
    const it = interaction.current;
    if (!it) return;
    const el = fcRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (it.type === "pan") {
      graph.panBy(e.clientX - it.lastX, e.clientY - it.lastY);
      it.lastX = e.clientX;
      it.lastY = e.clientY;
    } else if (it.type === "drag") {
      const w = screenToWorld(e.clientX, e.clientY, rect, graph.view);
      graph.moveNode(it.nodeId, w.x - it.offX, w.y - it.offY);
    } else if (it.type === "link") {
      const w = screenToWorld(e.clientX, e.clientY, rect, graph.view);
      graph.setLink({ fromNodeId: it.fromNodeId, cursor: w });
    }
  };

  const onUp = (e: React.PointerEvent) => {
    const it = interaction.current;
    if (it?.type === "drag") graph.touch?.();
    if (it?.type === "link") {
      const el = document.elementFromPoint(e.clientX, e.clientY);
      const inp = el?.closest("[data-node-input]");
      const target = inp?.getAttribute("data-node-input");
      if (target && target !== it.fromNodeId) graph.connect(it.fromNodeId, target);
      graph.setLink(null);
    }
    interaction.current = null;
    try {
      fcRef.current?.releasePointerCapture(e.pointerId);
    } catch {
      /* not captured */
    }
  };

  // ── palette add ──────────────────────────────────────────────────────────────
  const addAgent = (a: Agent) => graph.addNode("agent", centreWorld(), a.id, a.name);
  const addStruct = (kind: FlowNodeKind, label: string) => graph.addNode(kind, centreWorld(), undefined, label);

  // ── actions ──────────────────────────────────────────────────────────────────
  function doSave() {
    save.mutate(
      { ...graph.snapshot, daemonId: effectiveDaemon },
      {
        onSuccess: () => {
          graph.markSaved();
          showToast({ text: "Flow saved" });
        },
        onError: (err) => showToast({ text: (err as Error).message, variant: "warn" }),
      },
    );
  }

  function doTest() {
    const seq = batonOrder(graph);
    if (seq.length < 2) {
      showToast({ text: "Wire a Start → agent path to test", variant: "warn" });
      return;
    }
    const hashes: Record<string, string> = {};
    for (const e of graph.edges) hashes[e.id] = Math.random().toString(16).slice(2, 18);
    setTrace({ draft: true, rootRunId: "rn_" + Math.random().toString(16).slice(2, 12), seq, idx: 0, hashes, done: false });
  }

  function doConfirmPublish(hours: number) {
    save.mutate(
      { ...graph.snapshot, daemonId: effectiveDaemon },
      {
        onSettled: () =>
          publish.mutate(
            { flowId: flow.id, expiresInSeconds: Math.max(60, hours * 3600) },
            {
              onSuccess: () => {
                graph.markSaved();
                setStatus("published");
                setConsent(false);
                showToast({ text: "Chain grant signed & published" });
              },
              onError: (err) => showToast({ text: (err as Error).message, variant: "warn" }),
            },
          ),
      },
    );
  }

  function doRevoke() {
    setTrace(null);
    if (flow.publishedGrantId) {
      revoke.mutate(
        { grantId: flow.publishedGrantId, flowId: flow.id },
        { onSuccess: () => showToast({ text: "Chain grant revoked — chain halted", variant: "warn" }) },
      );
    } else {
      showToast({ text: "Chain halted", variant: "warn" });
    }
  }

  // ── trace state per node/edge ────────────────────────────────────────────────
  const nodeTrace = (nodeId: string): TraceState => {
    if (!trace) return "idle";
    const pos = trace.seq.indexOf(nodeId);
    if (pos === -1) return "idle";
    if (!trace.done && pos === trace.idx) return "active";
    if (trace.done || pos < trace.idx) return "done";
    return "idle";
  };
  const edgeTrace = (from: string, to: string): { active: boolean; done: boolean } => {
    if (!trace) return { active: false, done: false };
    const fi = trace.seq.indexOf(from);
    const ti = trace.seq.indexOf(to);
    if (fi === -1 || ti === -1) return { active: false, done: false };
    if (!trace.done && fi === trace.idx - 1 && ti === trace.idx) return { active: true, done: false };
    if (trace.done || ti <= trace.idx) return { active: false, done: ti <= trace.idx && fi < ti };
    return { active: false, done: false };
  };

  const linkGhost = (() => {
    if (!graph.link) return null;
    const from = nodeById.get(graph.link.fromNodeId);
    if (!from) return null;
    return edgePath(outPort(from), graph.link.cursor);
  })();

  const agentNodeCount = graph.nodes.filter((n) => n.kind === "agent").length;

  return (
    <div className="fc-root">
      <Toolbar
        graph={graph}
        status={status}
        issues={issues}
        saving={save.isPending}
        testing={false}
        tracing={trace != null}
        onBack={() => navigate("/flows")}
        onTest={doTest}
        onSave={doSave}
        onPublish={() => setConsent(true)}
      />

      <div className="fc-body">
        <NodePalette
          agents={agents}
          activeDaemon={effectiveDaemon}
          onAddStruct={addStruct}
          onAddAgent={addAgent}
        />

        <div
          ref={fcRef}
          className="fc-viewport"
          onPointerDown={onSurfaceDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          style={{
            backgroundSize: `${24 * graph.view.zoom}px ${24 * graph.view.zoom}px`,
            backgroundPosition: `${graph.view.x}px ${graph.view.y}px`,
          }}
        >
          <div className="fc-grid" />
          <div
            className="fc-world"
            style={{ transform: `translate(${graph.view.x}px, ${graph.view.y}px) scale(${graph.view.zoom})` }}
          >
            <svg className="fc-edges" aria-hidden>
              <defs>
                <marker id="fc-arrow" markerWidth="11" markerHeight="11" refX="8" refY="5" orient="auto">
                  <path d="M1,1 L9,5 L1,9" />
                </marker>
              </defs>
              {graph.edges.map((e) => {
                const from = nodeById.get(e.from);
                const to = nodeById.get(e.to);
                if (!from || !to) return null;
                const tr = edgeTrace(e.from, e.to);
                return (
                  <FlowEdgeView
                    key={e.id}
                    edge={e}
                    a={outPort(from)}
                    b={inPort(to)}
                    selected={graph.selectedEdge === e.id}
                    invalid={issueFor(issues, e.id)?.level === "error"}
                    active={tr.active}
                    done={tr.done}
                    payloadHash={trace?.hashes[e.id]}
                    onSelect={graph.setSelectedEdge}
                  />
                );
              })}
              {linkGhost && <path className="fc-edge-ghost" d={linkGhost} fill="none" />}
            </svg>

            {graph.nodes.map((n) => (
              <FlowNodeView
                key={n.id}
                node={n}
                agent={n.agentId ? resolve(n.agentId) : undefined}
                selected={graph.selectedNode === n.id}
                invalid={issueFor(issues, n.id)?.level === "error"}
                trace={nodeTrace(n.id)}
                onSelect={onNodeSelect(n.id)}
                onDragStart={onNodeDrag(n.id)}
                onPortDown={onPortDown}
              />
            ))}
          </div>

          {agentNodeCount === 0 && (
            <div className="fc-empty">
              <Icon name="git-branch" size={28} />
              <h3>Build a handoff chain</h3>
              <p>Drop agents from the left, then wire each output into the next agent's input.</p>
            </div>
          )}

          {trace && (
            <TraceBanner
              draft={trace.draft}
              rootRunId={trace.rootRunId}
              activeLabel={(() => {
                const id = trace.seq[trace.idx];
                const n = nodeById.get(id);
                return n?.agentId ? resolve(n.agentId)?.name ?? n.label : n?.label;
              })()}
              hop={trace.idx + 1}
              total={trace.seq.length}
              done={trace.done}
              onHalt={() => setTrace(null)}
              onRevoke={doRevoke}
              onClose={() => setTrace(null)}
            />
          )}
        </div>

        <Inspector graph={graph} agents={agents} />
      </div>

      {consent && (
        <ConsentModal
          flow={{ ...graph.snapshot, daemonId: effectiveDaemon }}
          edgeCount={compileAgentEdges(graph.snapshot).length}
          publishing={publish.isPending || save.isPending}
          onConfirm={doConfirmPublish}
          onCancel={() => setConsent(false)}
        />
      )}
    </div>
  );
}

/** Follow tail/return edges from Start to produce the baton order for the draft run. */
function batonOrder(graph: FlowGraph): string[] {
  const start = graph.nodes.find((n) => n.kind === "start") ?? graph.nodes[0];
  if (!start) return [];
  const seq: string[] = [start.id];
  const seen = new Set<string>([start.id]);
  let cur = start.id;
  for (let i = 0; i < 12; i++) {
    const next = graph.edges.find((e) => e.from === cur && !seen.has(e.to));
    if (!next) break;
    seq.push(next.to);
    seen.add(next.to);
    cur = next.to;
  }
  return seq;
}
