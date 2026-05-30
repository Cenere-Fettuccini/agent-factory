import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";
import { AgentNode } from "./AgentNode";
import { LaneNode } from "./LaneNode";
import { LANE_HEIGHT, LANE_WIDTH, tierColor, useGraph } from "../state/graphStore";

const nodeTypes = { agent: AgentNode, lane: LaneNode };
const AGENT_NODE_ESTIMATED_HEIGHT = 340;
const LANE_PADDING = 16;

/** Downstream-reachable node + edge ids from a starting node (the resolution path). */
function reachableFrom(
  start: string | null,
  edges: { source: string; target: string }[]
): { nodes: Set<string>; edges: Set<string> } {
  const nodes = new Set<string>();
  const edgeIds = new Set<string>();
  if (!start) return { nodes, edges: edgeIds };
  nodes.add(start);
  const queue = [start];
  while (queue.length) {
    const cur = queue.shift()!;
    for (const e of edges) {
      if (e.source === cur) {
        edgeIds.add(`${e.source}->${e.target}`);
        if (!nodes.has(e.target)) {
          nodes.add(e.target);
          queue.push(e.target);
        }
      }
    }
  }
  return { nodes, edges: edgeIds };
}

function laneIndexFromY(y: number, layerCount: number): number {
  const idx = Math.floor(y / LANE_HEIGHT);
  return Math.max(0, Math.min(layerCount - 1, idx));
}

function clampPositionToLane(
  position: { x: number; y: number },
  laneIndex: number,
  nodeHeight = AGENT_NODE_ESTIMATED_HEIGHT
): { x: number; y: number } {
  const laneTop = laneIndex * LANE_HEIGHT;
  const minY = laneTop + LANE_PADDING;
  const maxY = laneTop + LANE_HEIGHT - nodeHeight - LANE_PADDING;

  return {
    x: position.x,
    y: Math.max(minY, Math.min(position.y, Math.max(minY, maxY))),
  };
}

interface CanvasMenu {
  x: number;
  y: number;
  flow: { x: number; y: number };
}

function InnerCanvas() {
  const store = useGraph();
  const { screenToFlowPosition, fitView } = useReactFlow();
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<Node>([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [menu, setMenu] = useState<CanvasMenu | null>(null);
  const didFit = useRef(false);

  const errorByNode = useMemo(() => {
    const m = new Map<string, string>();
    for (const issue of store.issues) {
      if (issue.severity === "error" && issue.node_id) {
        m.set(issue.node_id, issue.message);
      }
    }
    if (store.dryRun) {
      for (const dn of store.dryRun.nodes) {
        if (!dn.ok && dn.error) m.set(dn.node_id, dn.error);
      }
    }
    return m;
  }, [store.issues, store.dryRun]);

  const path = useMemo(
    () => reachableFrom(store.selectedNodeId, store.edges),
    [store.selectedNodeId, store.edges]
  );

  // Rebuild React Flow nodes/edges whenever the canonical graph changes.
  useEffect(() => {
    const lanes: Node[] = store.layers.map((label, i) => ({
      id: `lane-${i}`,
      type: "lane",
      position: { x: 0, y: i * LANE_HEIGHT },
      data: { label, index: i, color: tierColor(i) },
      draggable: false,
      selectable: false,
      zIndex: 0,
      style: { width: LANE_WIDTH, height: LANE_HEIGHT },
    }));

    const agents: Node[] = store.nodes.map((n) => ({
      id: n.id,
      type: "agent",
      position: store.positions[n.id] ?? { x: 60, y: 40 },
      selected: n.id === store.selectedNodeId,
      zIndex: 1,
      data: {
        node: n,
        hasError: errorByNode.has(n.id),
        errorMsg: errorByNode.get(n.id) ?? null,
        onPath: store.selectedNodeId !== null && path.nodes.has(n.id) && n.id !== store.selectedNodeId,
        isTopTier: store.layerIndex(n.layer) === 0,
      },
    }));

    setRfNodes([...lanes, ...agents]);
  }, [
    store.layers,
    store.nodes,
    store.positions,
    store.selectedNodeId,
    errorByNode,
    path,
    setRfNodes,
  ]);

  useEffect(() => {
    setRfEdges(
      store.edges.map((e) => {
        const onPath = path.edges.has(`${e.source}->${e.target}`);
        return {
          id: `${e.source}->${e.target}`,
          source: e.source,
          target: e.target,
          animated: onPath,
          style: onPath ? { stroke: "var(--era2)", strokeWidth: 2 } : { stroke: "var(--muted)" },
        };
      })
    );
  }, [store.edges, path, setRfEdges]);

  // Frame the tier stack on first paint, once the lanes exist. The tall stack is
  // height-bound, so all pre-established tiers land inside the viewport. After
  // that the user owns the viewport (the Controls fit button re-frames on demand).
  useEffect(() => {
    if (didFit.current || rfNodes.length === 0) return;
    didFit.current = true;
    requestAnimationFrame(() => fitView({ padding: 0.1, maxZoom: 1, duration: 0 }));
  }, [rfNodes, fitView]);

  const isValidConnection = useCallback(
    (c: Connection | Edge) => {
      if (!c.source || !c.target || c.source === c.target) return false;
      const src = store.nodes.find((n) => n.id === c.source);
      const tgt = store.nodes.find((n) => n.id === c.target);
      if (!src || !tgt) return false;
      const si = store.layerIndex(src.layer);
      const ti = store.layerIndex(tgt.layer);
      // Only allow a call to the tier directly below.
      return si !== null && ti !== null && ti === si + 1;
    },
    [store]
  );

  const onConnect = useCallback(
    (c: Connection) => {
      if (c.source && c.target) store.addEdge(c.source, c.target);
    },
    [store]
  );

  const onNodeDragStop = useCallback(
    (_e: unknown, node: Node) => {
      if (node.type !== "agent") return;
      const laneIndex = laneIndexFromY(node.position.y, store.layers.length);
      const clampedPosition = clampPositionToLane(node.position, laneIndex, node.measured?.height);
      store.setPosition(node.id, clampedPosition);
      const newLayer = store.layers[laneIndex];
      const current = store.nodes.find((n) => n.id === node.id);
      if (current && current.layer !== newLayer) store.setNodeLayer(node.id, newLayer);
    },
    [store]
  );

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      if (event.dataTransfer.getData("application/agent-node") !== "1") return;
      const pos = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const laneIndex = laneIndexFromY(pos.y, store.layers.length);
      const layer = store.layers[laneIndex];
      store.addNode(layer, clampPositionToLane(pos, laneIndex));
    },
    [screenToFlowPosition, store]
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  // ComfyUI-style: right-click the canvas to add an agent or open the designer.
  const onPaneContextMenu = useCallback(
    (event: React.MouseEvent | MouseEvent) => {
      event.preventDefault();
      const flow = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      setMenu({ x: event.clientX, y: event.clientY, flow });
    },
    [screenToFlowPosition]
  );

  const addAgentHere = useCallback(
    (flow: { x: number; y: number }) => {
      const laneIndex = laneIndexFromY(flow.y, store.layers.length);
      store.addNode(store.layers[laneIndex], clampPositionToLane(flow, laneIndex));
      setMenu(null);
    },
    [store]
  );

  return (
    <>
    <ReactFlow
      nodes={rfNodes}
      edges={rfEdges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      isValidConnection={isValidConnection}
      onNodeDragStop={onNodeDragStop}
      onNodeClick={(_e, node) => node.type === "agent" && store.select(node.id)}
      onPaneClick={() => {
        store.select(null);
        setMenu(null);
      }}
      onPaneContextMenu={onPaneContextMenu}
      onEdgeClick={(_e, edge) => {
        if (edge.source && edge.target) store.removeEdge(edge.source, edge.target);
      }}
      onDrop={onDrop}
      onDragOver={onDragOver}
      nodeTypes={nodeTypes}
      minZoom={0.3}
      proOptions={{ hideAttribution: true }}
    >
      <Background color="#2a3042" gap={24} />
      <Controls />
    </ReactFlow>

    {menu && (
      <>
        <div
          className="ctx-backdrop"
          onClick={() => setMenu(null)}
          onContextMenu={(e) => {
            e.preventDefault();
            setMenu(null);
          }}
        />
        <div className="ctx-menu" style={{ top: menu.y, left: menu.x }}>
          <button
            className="ctx-item accent"
            onClick={() => {
              store.setDesignerOpen(true);
              setMenu(null);
            }}
          >
            ✦ Design with AI
          </button>
          <button className="ctx-item" onClick={() => addAgentHere(menu.flow)}>
            + Add agent here
          </button>
        </div>
      </>
    )}
    </>
  );
}

export function TierCanvas() {
  return (
    <ReactFlowProvider>
      <InnerCanvas />
    </ReactFlowProvider>
  );
}
