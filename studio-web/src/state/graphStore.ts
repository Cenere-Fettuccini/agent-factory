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
// Tall enough for a ComfyUI-style node with its widgets always visible.
export const LANE_HEIGHT = 400;
export const LANE_WIDTH = 2000;

// One accent per tier (cycled), used for the node title bar and lane frame.
export const TIER_COLORS = ["#7cc4ff", "#76d49a", "#b794ff", "#e8a468", "#e8688f"];
export function tierColor(index: number): string {
  const n = TIER_COLORS.length;
  return TIER_COLORS[((index % n) + n) % n];
}

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

  /** Apply a proposed delta. Returns false (a no-op) when there's nothing to change. */
  loadProposal: (proposal: DesignProposal) => boolean;

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
const PROPOSAL_X_STEP = 320;
const PROPOSAL_Y_OFFSET = 28;

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

  // Apply an SLM-proposed DELTA to the canvas: add new agents/tiers/edges, modify
  // existing agents in place, and delete whatever the proposal explicitly lists in
  // `remove`. Deletion is opt-in by design — omitting an existing item never drops
  // it, so a thin/empty generation from the in-browser 0.5B model can't silently
  // wipe the user's work; only an explicit `remove` entry deletes. Modifying an
  // existing agent patches only the proposal-owned fields (description, name,
  // layer, trigger); its resolved config (model/tools/…) and id are preserved so a
  // later Resolve isn't clobbered. New layer configs stay unset for the backend
  // Resolver to fill, and Validate flags any tier-skipping edges.
  loadProposal: (proposal) => {
    const removal = proposal.remove ?? {};
    const removeAgentIds = new Set(removal.agents ?? []);
    const removeLayerNames = new Set(removal.layers ?? []);
    const removeEdgeKeys = new Set(
      (removal.edges ?? []).map((e) => `${e.source}->${e.target}`)
    );

    const hasAdds =
      proposal.agents.length > 0 ||
      proposal.layers.length > 0 ||
      proposal.edges.length > 0;
    const hasRemovals =
      removeAgentIds.size > 0 || removeLayerNames.size > 0 || removeEdgeKeys.size > 0;
    // Nothing to apply: a dud/empty generation leaves the canvas untouched and the
    // caller can tell the user the model returned nothing usable.
    if (!hasAdds && !hasRemovals) return false;

    set((s) => {
      // Tier names are matched loosely: the model rarely echoes "Orchestrator"
      // with the exact casing/spacing, so we compare on a normalized key. Without
      // this, a proposed "orchestration" tier piles up as a *new* lane below the
      // empty default and its agents scatter off-screen.
      const normLayer = (l: string) => l.trim().toLowerCase().replace(/\s+/g, " ");
      const removeLayerKeys = new Set([...removeLayerNames].map(normLayer));

      // --- Tiers --------------------------------------------------------------
      // On a blank canvas (no agents yet) the three default tiers are just a
      // scaffold — adopt the proposal's own tier structure instead of stacking
      // onto it, so the model's design fills the canvas top-to-bottom. With agents
      // present we delta-merge: keep existing tiers, append genuinely new ones.
      const fresh = s.nodes.length === 0;
      let layers = fresh && proposal.layers.length ? [] : [...s.layers];
      const canonicalByNorm = new Map<string, string>();
      for (const l of layers) canonicalByNorm.set(normLayer(l), l);
      for (const raw of proposal.layers) {
        const name = (raw ?? "").trim();
        if (!name) continue;
        const key = normLayer(name);
        if (canonicalByNorm.has(key)) continue; // same tier under any casing
        layers.push(name);
        canonicalByNorm.set(key, name);
      }
      layers = layers.filter((l) => !removeLayerKeys.has(normLayer(l)));
      for (const key of removeLayerKeys) canonicalByNorm.delete(key);
      if (layers.length === 0) layers = [...DEFAULT_LAYERS]; // never leave it tier-less

      // Resolve a proposed tier name to a canvas tier index, or -1 if unknown.
      const layerIndexOf = (raw: string | null | undefined): number => {
        if (raw == null) return -1;
        const canon = canonicalByNorm.get(normLayer(raw));
        return canon == null ? -1 : layers.indexOf(canon);
      };

      // An agent is deleted if named for removal, or its tier was removed.
      const isDeleted = (n: GraphNode) =>
        removeAgentIds.has(n.id) ||
        (n.layer != null && removeLayerKeys.has(normLayer(n.layer)));

      const positions: Record<string, NodePosition> = { ...s.positions };
      const proposedById = new Map(proposal.agents.map((a) => [a.id, a]));

      // --- Existing nodes: keep survivors; patch in place if re-proposed. ------
      const survivors: GraphNode[] = [];
      for (const n of s.nodes) {
        if (isDeleted(n)) {
          delete positions[n.id];
          continue;
        }
        const p = proposedById.get(n.id);
        if (!p) {
          survivors.push(n);
          continue;
        }
        // Delta edit: only the proposal-owned fields change.
        const ri = layerIndexOf(p.layer);
        const layer = ri >= 0 ? layers[ri] : n.layer;
        if (layer !== n.layer && ri >= 0) {
          positions[n.id] = {
            x: positions[n.id]?.x ?? PROPOSAL_X_START,
            y: ri * LANE_HEIGHT + PROPOSAL_Y_OFFSET,
          };
        }
        survivors.push({
          ...n,
          description: p.description,
          name: p.name?.trim() ? p.name.trim() : null,
          layer,
          trigger:
            p.trigger === "user_query" || p.trigger === "auto_action" ? p.trigger : null,
        });
      }

      // --- New agents: anything proposed whose id isn't already on the canvas. --
      const used = new Set(survivors.map((n) => n.id));
      // Pre-seed the id map with surviving ids (mapped to themselves) so proposal
      // edges referencing an existing agent still resolve.
      const idMap = new Map<string, string>();
      for (const n of survivors) idMap.set(n.id, n.id);

      const perLane: Record<number, number> = {};
      for (const n of survivors) {
        const li = n.layer ? layers.indexOf(n.layer) : -1;
        if (li >= 0) perLane[li] = (perLane[li] ?? 0) + 1;
      }

      // Tier assignment is opportunistic: if the proposal names a tier we
      // recognize, the agent lands in that lane; otherwise (missing/unknown tier)
      // it's dropped tier-less into a staging row below the lanes for the user to
      // drag into place — better than guessing a tier and scattering nodes.
      const unassignedY = layers.length * LANE_HEIGHT + PROPOSAL_Y_OFFSET;
      let unassignedCol = 0;

      const newNodes: GraphNode[] = [];
      for (const a of proposal.agents) {
        if (idMap.has(a.id)) continue; // already exists — patched above

        const id = sanitizeId(a.id, used);
        used.add(id);
        idMap.set(a.id, id);

        const ri = layerIndexOf(a.layer);
        const node = emptyNode(id, ri >= 0 ? layers[ri] : null);
        node.description = a.description;
        node.name = a.name?.trim() ? a.name.trim() : null;
        node.trigger =
          a.trigger === "user_query" || a.trigger === "auto_action" ? a.trigger : null;
        newNodes.push(node);

        if (ri >= 0) {
          const col = perLane[ri] ?? 0;
          perLane[ri] = col + 1;
          positions[id] = {
            x: PROPOSAL_X_START + col * PROPOSAL_X_STEP,
            y: ri * LANE_HEIGHT + PROPOSAL_Y_OFFSET,
          };
        } else {
          positions[id] = {
            x: PROPOSAL_X_START + unassignedCol * PROPOSAL_X_STEP,
            y: unassignedY,
          };
          unassignedCol += 1;
        }
      }

      const nodes = [...survivors, ...newNodes];
      const nodeIds = new Set(nodes.map((n) => n.id));

      // --- Edges: keep survivors minus removals/dangling, then add proposed. ---
      const edges: GraphEdge[] = [];
      const seen = new Set<string>();
      for (const e of s.edges) {
        const key = `${e.source}->${e.target}`;
        if (removeEdgeKeys.has(key)) continue;
        if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) continue;
        if (seen.has(key)) continue;
        seen.add(key);
        edges.push(e);
      }
      for (const e of proposal.edges) {
        const source = idMap.get(e.source) ?? e.source;
        const target = idMap.get(e.target) ?? e.target;
        const key = `${source}->${target}`;
        if (source === target || !nodeIds.has(source) || !nodeIds.has(target)) continue;
        if (removeEdgeKeys.has(key) || seen.has(key)) continue;
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
    });
    return true;
  },

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
