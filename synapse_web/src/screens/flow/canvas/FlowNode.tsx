// A single canvas node — an agent card or a structural node (Start/Router/Return/End).
// Absolutely positioned in world space; the parent applies the viewport transform. Ports
// carry data attributes so the canvas can hit-test a dropped wire (see FlowCanvas).
import { Icon } from "../../../components/Primitives";
import { NODE_H, NODE_W } from "./geometry";
import type { AgentMeta } from "../validate";
import type { FlowNode as FlowNodeT } from "../../../types";

export type TraceState = "idle" | "active" | "done";

const STRUCT_ICON: Record<string, string> = {
  start: "play",
  router: "git-branch",
  return: "rotate-ccw",
  end: "flag",
};

const ENGINE_GLYPH: Record<string, string> = {
  "Claude Code": "✶",
  Codex: "◆",
  "Gemini CLI": "✷",
  API: "❯",
};

interface Props {
  node: FlowNodeT;
  agent?: AgentMeta;
  selected: boolean;
  invalid: boolean;
  trace: TraceState;
  onSelect: (e: React.PointerEvent) => void;
  onDragStart: (e: React.PointerEvent) => void;
  onPortDown: (nodeId: string, e: React.PointerEvent) => void;
}

export default function FlowNode({
  node,
  agent,
  selected,
  invalid,
  trace,
  onSelect,
  onDragStart,
  onPortDown,
}: Props) {
  const isAgent = node.kind === "agent";
  const hasOut = node.kind !== "end";
  const hasIn = node.kind !== "start";

  const cls = [
    "fc-node",
    `fc-node--${node.kind}`,
    selected ? "is-selected" : "",
    invalid ? "is-invalid" : "",
    trace !== "idle" ? `is-${trace}` : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={cls}
      style={{ left: node.x, top: node.y, width: NODE_W, minHeight: NODE_H }}
      onPointerDown={onSelect}
    >
      {/* drag handle = the whole card body */}
      <div className="fc-node-grip" onPointerDown={onDragStart}>
        {isAgent ? (
          <>
            <div className="fc-node-avatar" data-engine={agent?.name ? "y" : "n"}>
              {ENGINE_GLYPH[agent?.name ?? ""] ?? (agent?.name?.[0]?.toUpperCase() ?? "?")}
            </div>
            <div className="fc-node-meta">
              <div className="fc-node-title">{agent?.name ?? "Unassigned agent"}</div>
              <div className="fc-node-sub">{node.label}</div>
            </div>
          </>
        ) : (
          <>
            <div className="fc-node-glyph">
              <Icon name={STRUCT_ICON[node.kind] ?? "circle"} size={15} />
            </div>
            <div className="fc-node-meta">
              <div className="fc-node-title">{node.label}</div>
              <div className="fc-node-sub">{node.kind}</div>
            </div>
          </>
        )}
      </div>

      {hasIn && (
        <span className="fc-port fc-port--in" data-node-input={node.id} aria-label="input" />
      )}
      {hasOut && (
        <span
          className="fc-port fc-port--out"
          aria-label="output"
          onPointerDown={(e) => {
            e.stopPropagation();
            onPortDown(node.id, e);
          }}
        />
      )}
      {trace === "active" && <span className="fc-node-pulse" aria-hidden />}
    </div>
  );
}
