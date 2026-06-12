// A single handoff wire — a horizontal-tangent bezier with a mode/condition badge at its
// midpoint. A wide transparent hit-path makes it easy to select. `return` edges render
// dashed (the critic-loop look); an active trace hop animates a flowing dash.
import { edgeMidpoint, edgePath, type Pt } from "./geometry";
import type { FlowEdge as FlowEdgeT } from "../../../types";

interface Props {
  edge: FlowEdgeT;
  a: Pt; // from output port
  b: Pt; // to input port
  selected: boolean;
  invalid: boolean;
  active: boolean; // trace: this hop is currently running
  done: boolean; // trace: this hop completed
  payloadHash?: string;
  onSelect: (id: string) => void;
}

export default function FlowEdge({
  edge,
  a,
  b,
  selected,
  invalid,
  active,
  done,
  payloadHash,
  onSelect,
}: Props) {
  const d = edgePath(a, b);
  const mid = edgeMidpoint(a, b);
  const cls = [
    "fc-edge",
    edge.mode === "return" ? "fc-edge--return" : "fc-edge--tail",
    selected ? "is-selected" : "",
    invalid ? "is-invalid" : "",
    active ? "is-active" : "",
    done ? "is-done" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <g className={cls} onPointerDown={() => onSelect(edge.id)}>
      <path className="fc-edge-hit" d={d} fill="none" />
      <path className="fc-edge-line" d={d} fill="none" markerEnd="url(#fc-arrow)" />
      {active && <circle className="fc-edge-spark" r={4} />}
      <g className="fc-edge-badge" transform={`translate(${mid.x}, ${mid.y})`}>
        <rect x={-34} y={-12} width={68} height={24} rx={12} />
        <text x={0} y={4} textAnchor="middle">
          {edge.when ? edge.when : edge.mode}
        </text>
      </g>
      {done && payloadHash && (
        <g className="fc-edge-hash" transform={`translate(${mid.x}, ${mid.y + 22})`}>
          <text x={0} y={0} textAnchor="middle">
            ⛓ {payloadHash.slice(0, 8)}
          </text>
        </g>
      )}
    </g>
  );
}
