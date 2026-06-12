// Pure canvas geometry — node sizing, port anchors, and the bezier edge path. Kept
// framework-free so it is trivially testable and shared across node/edge components.
import type { FlowNode } from "../../../types";

export const NODE_W = 196;
export const NODE_H = 76;
export const PORT_R = 7;

export interface Pt {
  x: number;
  y: number;
}

/** World-space anchor of a node's input (left) port. */
export function inPort(n: Pick<FlowNode, "x" | "y">): Pt {
  return { x: n.x, y: n.y + NODE_H / 2 };
}

/** World-space anchor of a node's output (right) port. */
export function outPort(n: Pick<FlowNode, "x" | "y">): Pt {
  return { x: n.x + NODE_W, y: n.y + NODE_H / 2 };
}

/** A horizontal-tangent cubic bezier between two points — the n8n/ComfyUI wire look.
 *  The control offset grows with horizontal distance so back-edges (loops) bow out
 *  gracefully instead of kinking. */
export function edgePath(a: Pt, b: Pt): string {
  const dx = Math.abs(b.x - a.x);
  const k = Math.max(40, Math.min(dx * 0.5, 160));
  return `M ${a.x},${a.y} C ${a.x + k},${a.y} ${b.x - k},${b.y} ${b.x},${b.y}`;
}

/** Midpoint of the bezier (t=0.5) — where an edge badge/label sits. */
export function edgeMidpoint(a: Pt, b: Pt): Pt {
  const dx = Math.abs(b.x - a.x);
  const k = Math.max(40, Math.min(dx * 0.5, 160));
  const c1 = { x: a.x + k, y: a.y };
  const c2 = { x: b.x - k, y: b.y };
  // Cubic bezier at t = 0.5.
  const mx = 0.125 * a.x + 0.375 * c1.x + 0.375 * c2.x + 0.125 * b.x;
  const my = 0.125 * a.y + 0.375 * c1.y + 0.375 * c2.y + 0.125 * b.y;
  return { x: mx, y: my };
}

/** Convert a client (screen) point to world coordinates given the viewport transform. */
export function screenToWorld(
  clientX: number,
  clientY: number,
  rect: DOMRect,
  view: { x: number; y: number; zoom: number },
): Pt {
  return {
    x: (clientX - rect.left - view.x) / view.zoom,
    y: (clientY - rect.top - view.y) / view.zoom,
  };
}
