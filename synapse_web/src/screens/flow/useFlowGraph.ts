// Working-copy graph state for the Flow Canvas — nodes, edges, settings, selection, the
// viewport transform, and the transient edge-linking interaction. Holds the editable
// design; persistence (Supabase / mock) is the caller's job via useSaveFlow.
import { useCallback, useMemo, useRef, useState } from "react";
import type {
  AgentFlow,
  FlowEdge,
  FlowNode,
  FlowNodeKind,
  FlowSettings,
  HandoffMode,
} from "../../types";
import { edgeId, nodeId } from "./templates";

export interface View {
  x: number;
  y: number;
  zoom: number;
}

export interface LinkDrag {
  fromNodeId: string;
  cursor: { x: number; y: number }; // world coords
}

const MIN_ZOOM = 0.35;
const MAX_ZOOM = 2.2;

export function useFlowGraph(initial: AgentFlow) {
  const [name, setName] = useState(initial.name);
  const [nodes, setNodes] = useState<FlowNode[]>(initial.nodes);
  const [edges, setEdges] = useState<FlowEdge[]>(initial.edges);
  const [settings, setSettings] = useState<FlowSettings>(initial.settings);
  const [view, setView] = useState<View>({ x: 40, y: 24, zoom: 1 });
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [link, setLink] = useState<LinkDrag | null>(null);
  const [dirty, setDirty] = useState(false);
  const baseId = useRef(initial.id);

  const touch = useCallback(() => setDirty(true), []);

  // ── node ops ───────────────────────────────────────────────────────────────
  const addNode = useCallback(
    (kind: FlowNodeKind, world: { x: number; y: number }, agentId?: string, label?: string) => {
      const id = nodeId();
      const n: FlowNode = {
        id,
        kind,
        agentId,
        label: label ?? kind.charAt(0).toUpperCase() + kind.slice(1),
        x: Math.round(world.x),
        y: Math.round(world.y),
      };
      setNodes((ns) => [...ns, n]);
      setSelectedNode(id);
      setSelectedEdge(null);
      touch();
      return id;
    },
    [touch],
  );

  const moveNode = useCallback(
    (id: string, x: number, y: number) => {
      setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, x: Math.round(x), y: Math.round(y) } : n)));
    },
    [],
  );

  const updateNode = useCallback(
    (id: string, patch: Partial<FlowNode>) => {
      setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, ...patch } : n)));
      touch();
    },
    [touch],
  );

  const deleteNode = useCallback(
    (id: string) => {
      setNodes((ns) => ns.filter((n) => n.id !== id));
      setEdges((es) => es.filter((e) => e.from !== id && e.to !== id));
      setSelectedNode((s) => (s === id ? null : s));
      touch();
    },
    [touch],
  );

  // ── edge ops ───────────────────────────────────────────────────────────────
  const connect = useCallback(
    (from: string, to: string) => {
      if (from === to) return;
      setEdges((es) => {
        if (es.some((e) => e.from === from && e.to === to)) return es; // no dup
        const e: FlowEdge = { id: edgeId(), from, to, mode: "tail", when: null };
        setSelectedEdge(e.id);
        setSelectedNode(null);
        return [...es, e];
      });
      touch();
    },
    [touch],
  );

  const updateEdge = useCallback(
    (id: string, patch: Partial<FlowEdge>) => {
      setEdges((es) => es.map((e) => (e.id === id ? { ...e, ...patch } : e)));
      touch();
    },
    [touch],
  );

  const deleteEdge = useCallback(
    (id: string) => {
      setEdges((es) => es.filter((e) => e.id !== id));
      setSelectedEdge((s) => (s === id ? null : s));
      touch();
    },
    [touch],
  );

  const updateSettings = useCallback(
    (patch: Partial<FlowSettings>) => {
      setSettings((s) => ({ ...s, ...patch }));
      touch();
    },
    [touch],
  );

  const toggleMode = useCallback(
    (mode: HandoffMode) => {
      setSettings((s) => {
        const has = s.modes.includes(mode);
        const modes = has ? s.modes.filter((m) => m !== mode) : [...s.modes, mode];
        return { ...s, modes: modes.length ? modes : ["tail"] };
      });
      touch();
    },
    [touch],
  );

  // ── viewport ───────────────────────────────────────────────────────────────
  const panBy = useCallback((dx: number, dy: number) => {
    setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
  }, []);

  const zoomAt = useCallback((factor: number, px: number, py: number) => {
    setView((v) => {
      const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v.zoom * factor));
      const k = zoom / v.zoom;
      // Keep the pivot (px,py in container space) fixed under the cursor.
      return { zoom, x: px - (px - v.x) * k, y: py - (py - v.y) * k };
    });
  }, []);

  const resetView = useCallback(() => setView({ x: 40, y: 24, zoom: 1 }), []);

  const clearSelection = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
  }, []);

  const snapshot = useMemo<AgentFlow>(
    () => ({
      ...initial,
      id: baseId.current,
      name,
      nodes,
      edges,
      settings,
    }),
    [initial, name, nodes, edges, settings],
  );

  return {
    name,
    setName: (v: string) => {
      setName(v);
      touch();
    },
    nodes,
    edges,
    settings,
    view,
    selectedNode,
    selectedEdge,
    link,
    dirty,
    snapshot,
    touch,
    setSelectedNode: (id: string | null) => {
      setSelectedNode(id);
      if (id) setSelectedEdge(null);
    },
    setSelectedEdge: (id: string | null) => {
      setSelectedEdge(id);
      if (id) setSelectedNode(null);
    },
    setLink,
    addNode,
    moveNode,
    updateNode,
    deleteNode,
    connect,
    updateEdge,
    deleteEdge,
    updateSettings,
    toggleMode,
    panBy,
    zoomAt,
    resetView,
    clearSelection,
    markSaved: () => setDirty(false),
  };
}

export type FlowGraph = ReturnType<typeof useFlowGraph>;
