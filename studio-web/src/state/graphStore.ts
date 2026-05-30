// Canonical graph state (mirrors the backend Graph) plus UI state. React Flow
// nodes/edges are *derived* from this; this store is the single source of truth.
//
// Two revision counters drive backend calls:
//   structuralRev — bumped by adds, deletes, edges, tier changes -> triggers Resolve
//   graphRev      — bumped by any change -> triggers Validate
// Parameter edits (model pick, tool edits, description) bump only graphRev, so a
// resolve never clobbers what the user is typing.

import { create } from "zustand";
import type { DesignProposal } from "../designer/proposalSchema";
import type {
  DryRunResult,
  Graph,
  GraphEdge,
  GraphNode,
  PreviewResult,
  ToolDef,
  TriggerKind,
  ValidationIssue,
} from "../api/types";

export interface NodePosition {
  x: number;
  y: number;
}

export const DEFAULT_LAYERS = ["Refinement", "Orchestrator", "Tools"];
export const LANE_HEIGHT = 240;
export const LANE_WIDTH = 1600;

function emptyNode(id: string, layer: string | null): GraphNode {
  return {
    id,
    description: "",
    name: null,
    version: "0.1.0",
    tags: [],
    layer,
    trigger: null,
    model: null,
    io: null,
    tools: null,
    policy: null,
    errors: null,
    telemetry: null,
  };
}

interface GraphState {
  nodes: GraphNode[];
  edges: GraphEdge[];
  layers: string[];
  toolDefs: ToolDef[];
  positions: Record<string, NodePosition>;

  selectedNodeId: string | null;
  autoResolve: boolean;
  designerOpen: boolean;
  issues: ValidationIssue[];
  preview: PreviewResult | null;
  dryRun: DryRunResult | null;

  structuralRev: number;
  graphRev: number;

  // derived helpers
  toGraph: () => Graph;
  layerIndex: (layer: string | null) => number | null;

  // mutations
  addNode: (layer: string, position: NodePosition) => void;
  updateNode: (id: string, patch: Partial<GraphNode>) => void;
  setNodeLayer: (id: string, layer: string) => void;
  setTrigger: (id: string, trigger: TriggerKind | null) => void;
  removeNode: (id: string) => void;
  setPosition: (id: string, pos: NodePosition) => void;
  addEdge: (source: string, target: string) => void;
  removeEdge: (source: string, target: string) => void;

  loadProposal: (proposal: DesignProposal) => void;

  addLayer: (name: string) => void;
  renameLayer: (oldName: string, newName: string) => void;

  setToolDefs: (defs: ToolDef[]) => void;

  select: (id: string | null) => void;
  toggleAutoResolve: () => void;
  setDesignerOpen: (open: boolean) => void;
  setIssues: (issues: ValidationIssue[]) => void;
  setPreview: (preview: PreviewResult | null) => void;
  setDryRun: (dryRun: DryRunResult | null) => void;
  mergeResolved: (graph: Graph) => void;
}

let counter = 0;
function nextId(existing: Set<string>): string {
  do {
    counter += 1;
  } while (existing.has(`agent-${counter}`));
  return `agent-${counter}`;
}

// SLM-proposed ids are free-form; agent ids must match ^[a-z][a-z0-9_-]*$ once
// they reach the backend. Coerce, then de-dupe against ids already placed.
function sanitizeId(raw: string, used: Set<string>): string {
  let id = raw
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "");
  if (!/^[a-z]/.test(id)) id = `a-${id}`;
  if (!id) id = "agent";
  let unique = id;
  let n = 2;
  while (used.has(unique)) unique = `${id}-${n++}`;
  return unique;
}

// Auto-layout: agents fan out left-to-right within their tier's horizontal band.
const PROPOSAL_X_START = 80;
const PROPOSAL_X_STEP = 260;
const PROPOSAL_Y_OFFSET = 40;

export const useGraph = create<GraphState>((set, get) => ({
  nodes: [],
  edges: [],
  layers: [...DEFAULT_LAYERS],
  toolDefs: [],
  positions: {},

  selectedNodeId: null,
  autoResolve: true,
  designerOpen: false,
  issues: [],
  preview: null,
  dryRun: null,

  structuralRev: 0,
  graphRev: 0,

  toGraph: () => {
    const { nodes, edges, layers, toolDefs } = get();
    return { nodes, edges, layers, tool_defs: toolDefs };
  },

  layerIndex: (layer) => {
    if (layer === null) return null;
    const i = get().layers.indexOf(layer);
    return i === -1 ? null : i;
  },

  addNode: (layer, position) =>
    set((s) => {
      const id = nextId(new Set(s.nodes.map((n) => n.id)));
      return {
        nodes: [...s.nodes, emptyNode(id, layer)],
        positions: { ...s.positions, [id]: position },
        selectedNodeId: id,
        structuralRev: s.structuralRev + 1,
        graphRev: s.graphRev + 1,
      };
    }),

  updateNode: (id, patch) =>
    set((s) => ({
      nodes: s.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)),
      graphRev: s.graphRev + 1,
    })),

  setNodeLayer: (id, layer) =>
    set((s) => ({
      nodes: s.nodes.map((n) => (n.id === id ? { ...n, layer } : n)),
      structuralRev: s.structuralRev + 1,
      graphRev: s.graphRev + 1,
    })),

  setTrigger: (id, trigger) =>
    set((s) => ({
      nodes: s.nodes.map((n) => (n.id === id ? { ...n, trigger } : n)),
      graphRev: s.graphRev + 1,
    })),

  removeNode: (id) =>
    set((s) => {
      const positions = { ...s.positions };
      delete positions[id];
      return {
        nodes: s.nodes.filter((n) => n.id !== id),
        edges: s.edges.filter((e) => e.source !== id && e.target !== id),
        positions,
        selectedNodeId: s.selectedNodeId === id ? null : s.selectedNodeId,
        structuralRev: s.structuralRev + 1,
        graphRev: s.graphRev + 1,
      };
    }),

  setPosition: (id, pos) =>
    set((s) => ({ positions: { ...s.positions, [id]: pos } })),

  addEdge: (source, target) =>
    set((s) => {
      if (source === target) return {};
      if (s.edges.some((e) => e.source === source && e.target === target)) return {};
      return {
        edges: [...s.edges, { source, target }],
        structuralRev: s.structuralRev + 1,
        graphRev: s.graphRev + 1,
      };
    }),

  removeEdge: (source, target) =>
    set((s) => ({
      edges: s.edges.filter((e) => !(e.source === source && e.target === target)),
      structuralRev: s.structuralRev + 1,
      graphRev: s.graphRev + 1,
    })),

  addLayer: (name) =>
    set((s) =>
      s.layers.includes(name)
        ? {}
        : { layers: [...s.layers, name], structuralRev: s.structuralRev + 1 }
    ),

  renameLayer: (oldName, newName) =>
    set((s) => {
      if (!s.layers.includes(oldName) || s.layers.includes(newName)) return {};
      return {
        layers: s.layers.map((l) => (l === oldName ? newName : l)),
        nodes: s.nodes.map((n) => (n.layer === oldName ? { ...n, layer: newName } : n)),
        structuralRev: s.structuralRev + 1,
        graphRev: s.graphRev + 1,
      };
    }),

  setToolDefs: (defs) =>
    set((s) => ({ toolDefs: defs, graphRev: s.graphRev + 1 })),

  select: (id) => set({ selectedNodeId: id }),
  toggleAutoResolve: () => set((s) => ({ autoResolve: !s.autoResolve })),
  setDesignerOpen: (open) => set({ designerOpen: open }),
  setIssues: (issues) => set({ issues }),
  setPreview: (preview) => set({ preview }),
  setDryRun: (dryRun) => set({ dryRun }),

  // Replace the canvas with an SLM-proposed structure. Only the high-level shape
  // (tiers, agents, edges) is taken; every layer config is left unset so the
  // backend Resolver fills it, and Validate then flags any tier-skipping edges.
  loadProposal: (proposal) =>
    set((s) => {
      const layers = proposal.layers.length ? proposal.layers : s.layers;
      const used = new Set<string>();
      const idMap = new Map<string, string>();
      const perLane: Record<number, number> = {};
      const nodes: GraphNode[] = [];
      const positions: Record<string, NodePosition> = {};

      for (const a of proposal.agents) {
        const id = sanitizeId(a.id, used);
        used.add(id);
        idMap.set(a.id, id);

        const li = layers.includes(a.layer) ? layers.indexOf(a.layer) : 0;
        const col = perLane[li] ?? 0;
        perLane[li] = col + 1;

        const node = emptyNode(id, layers[li]);
        node.description = a.description;
        node.name = a.name?.trim() ? a.name.trim() : null;
        node.trigger =
          a.trigger === "user_query" || a.trigger === "auto_action" ? a.trigger : null;
        nodes.push(node);
        positions[id] = {
          x: PROPOSAL_X_START + col * PROPOSAL_X_STEP,
          y: li * LANE_HEIGHT + PROPOSAL_Y_OFFSET,
        };
      }

      const nodeIds = new Set(nodes.map((n) => n.id));
      const seen = new Set<string>();
      const edges: GraphEdge[] = [];
      for (const e of proposal.edges) {
        const source = idMap.get(e.source) ?? e.source;
        const target = idMap.get(e.target) ?? e.target;
        const key = `${source}->${target}`;
        if (source === target || !nodeIds.has(source) || !nodeIds.has(target)) continue;
        if (seen.has(key)) continue;
        seen.add(key);
        edges.push({ source, target });
      }

      return {
        layers,
        nodes,
        edges,
        positions,
        selectedNodeId: null,
        preview: null,
        dryRun: null,
        structuralRev: s.structuralRev + 1,
        graphRev: s.graphRev + 1,
      };
    }),

  // Merge a resolved graph back in: only layer configs change; positions, ids,
  // tiers, triggers, and edges are preserved from local state.
  mergeResolved: (graph) =>
    set((s) => {
      const byId = new Map(graph.nodes.map((n) => [n.id, n]));
      return {
        nodes: s.nodes.map((n) => {
          const r = byId.get(n.id);
          if (!r) return n;
          return {
            ...n,
            model: r.model,
            io: r.io,
            tools: r.tools,
            policy: r.policy,
            errors: r.errors,
            telemetry: r.telemetry,
          };
        }),
        // Re-validate against the freshly filled graph, but don't re-trigger
        // resolve (structuralRev is untouched).
        graphRev: s.graphRev + 1,
      };
    }),
}));
