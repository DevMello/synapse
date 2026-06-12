// Right rail — context inspector. Shows the selected edge's config (mode, router
// condition, payload field-mapping + redaction preview), the selected node's config
// (agent / label), or — when nothing is selected — the flow-wide grant settings.
import { Icon } from "../../../components/Primitives";
import type { Agent, HandoffMode } from "../../../types";
import type { FlowGraph } from "../useFlowGraph";

interface Props {
  graph: FlowGraph;
  agents: Agent[];
}

export default function Inspector({ graph, agents }: Props) {
  const edge = graph.edges.find((e) => e.id === graph.selectedEdge);
  const node = graph.nodes.find((n) => n.id === graph.selectedNode);

  if (edge) {
    const from = graph.nodes.find((n) => n.id === edge.from);
    const to = graph.nodes.find((n) => n.id === edge.to);
    const fromName = agents.find((a) => a.id === from?.agentId)?.name ?? from?.label ?? "?";
    const toName = agents.find((a) => a.id === to?.agentId)?.name ?? to?.label ?? "?";
    return (
      <aside className="fc-inspector">
        <div className="fc-insp-head">
          <span className="fc-insp-kicker">Handoff edge</span>
          <button className="fc-insp-del" title="Delete edge" onClick={() => graph.deleteEdge(edge.id)}>
            <Icon name="trash-2" size={14} />
          </button>
        </div>
        <div className="fc-insp-route">
          <span>{fromName}</span><Icon name="arrow-right" size={13} /><span>{toName}</span>
        </div>

        <label className="fc-insp-label">Mode</label>
        <div className="fc-seg">
          {(["tail", "return"] as HandoffMode[]).map((m) => (
            <button
              key={m}
              className={"fc-seg-btn" + (edge.mode === m ? " is-on" : "")}
              onClick={() => graph.updateEdge(edge.id, { mode: m })}
            >
              {m === "tail" ? "Tail · baton-pass" : "Return · loop back"}
            </button>
          ))}
        </div>

        <label className="fc-insp-label">Router condition (when)</label>
        <input
          className="db-input fc-insp-input"
          placeholder="e.g. approved — blank = always"
          value={edge.when ?? ""}
          onChange={(e) => graph.updateEdge(edge.id, { when: e.target.value || null })}
        />

        <label className="fc-insp-label">Payload mapping</label>
        <div className="fc-map">
          {(["task", "summary", "artifacts"] as const).map((f) => (
            <div className="fc-map-row" key={f}>
              <span className="fc-map-field">{f}</span>
              <input
                className="db-input fc-insp-input"
                placeholder={`source field → ${f}`}
                value={edge.mapping?.[f] ?? ""}
                onChange={(e) =>
                  graph.updateEdge(edge.id, {
                    mapping: { ...edge.mapping, [f]: e.target.value || undefined },
                  })
                }
              />
            </div>
          ))}
        </div>

        <div className="fc-redact">
          <Icon name="shield" size={13} />
          <span>
            <b>Layer A redaction</b> screens this envelope on-device before it leaves the
            source agent — secrets are tokenised, capped at {graph.settings.maxPayloadBytes.toLocaleString()} bytes.
          </span>
        </div>
      </aside>
    );
  }

  if (node) {
    return (
      <aside className="fc-inspector">
        <div className="fc-insp-head">
          <span className="fc-insp-kicker">{node.kind === "agent" ? "Agent node" : "Structural node"}</span>
          <button className="fc-insp-del" title="Delete node" onClick={() => graph.deleteNode(node.id)}>
            <Icon name="trash-2" size={14} />
          </button>
        </div>

        {node.kind === "agent" && (
          <>
            <label className="fc-insp-label">Agent</label>
            <select
              className="db-input fc-insp-input"
              value={node.agentId ?? ""}
              onChange={(e) => graph.updateNode(node.id, { agentId: e.target.value })}
            >
              <option value="">— choose agent —</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>{a.name} · {a.daemonId}</option>
              ))}
            </select>
          </>
        )}

        <label className="fc-insp-label">Label</label>
        <input
          className="db-input fc-insp-input"
          value={node.label}
          onChange={(e) => graph.updateNode(node.id, { label: e.target.value })}
        />
      </aside>
    );
  }

  // Nothing selected → flow grant settings.
  const s = graph.settings;
  return (
    <aside className="fc-inspector">
      <div className="fc-insp-head"><span className="fc-insp-kicker">Chain grant settings</span></div>
      <p className="fc-insp-note">These become the signed grant's enforced limits on publish.</p>

      <label className="fc-insp-label">Max hops <span className="fc-insp-hint">loop guard</span></label>
      <input className="db-input fc-insp-input" type="number" value={s.maxHops}
        onChange={(e) => graph.updateSettings({ maxHops: Number(e.target.value) })} />

      <label className="fc-insp-label">Chain budget (USD) <span className="fc-insp-hint">shared across chain</span></label>
      <input className="db-input fc-insp-input" type="number" step="0.5" value={s.chainBudgetUsd}
        onChange={(e) => graph.updateSettings({ chainBudgetUsd: Number(e.target.value) })} />

      <label className="fc-insp-label">Max payload (bytes) <span className="fc-insp-hint">H4 envelope cap</span></label>
      <input className="db-input fc-insp-input" type="number" step="1024" value={s.maxPayloadBytes}
        onChange={(e) => graph.updateSettings({ maxPayloadBytes: Number(e.target.value) })} />

      <label className="fc-insp-label">Allowed modes</label>
      <div className="fc-seg">
        {(["tail", "return"] as HandoffMode[]).map((m) => (
          <button key={m} className={"fc-seg-btn" + (s.modes.includes(m) ? " is-on" : "")}
            onClick={() => graph.toggleMode(m)}>{m}</button>
        ))}
      </div>
    </aside>
  );
}
