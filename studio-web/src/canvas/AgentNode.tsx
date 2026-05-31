import { useState } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { useCatalog } from "../catalog/CatalogProvider";
import { tierColor, useGraph } from "../state/graphStore";
import { ToolsPanel } from "../components/ToolsPanel";
import type { GraphNode, TriggerKind } from "../api/types";

export interface AgentNodeData {
  node: GraphNode;
  hasError: boolean;
  errorMsg: string | null;
  onPath: boolean;
  isTopTier: boolean;
  [key: string]: unknown;
}

// A full ComfyUI-style node: tier-tinted title bar with a collapse caret and a
// close button, labelled call sockets, and — since there is no inspector — every
// editable widget (name, description, tier, model, trigger, tools) living on the
// node body itself. Edits go straight to the store; the backend Resolver still
// fills whatever is left blank.
export function AgentNode({ data, selected }: NodeProps) {
  const d = data as AgentNodeData;
  const n = d.node;

  const { catalogs } = useCatalog();
  const layers = useGraph((s) => s.layers);
  const layerIndex = useGraph((s) => s.layerIndex);
  const updateNode = useGraph((s) => s.updateNode);
  const setTrigger = useGraph((s) => s.setTrigger);
  const setNodeLayer = useGraph((s) => s.setNodeLayer);
  const removeNode = useGraph((s) => s.removeNode);
  const canUndo = useGraph((s) => s.undoStack.length > 0);
  const canRedo = useGraph((s) => s.redoStack.length > 0);
  const undo = useGraph((s) => s.undo);
  const redo = useGraph((s) => s.redo);
  const preview = useGraph((s) => s.preview);
  const issues = useGraph((s) => s.issues);

  const [collapsed, setCollapsed] = useState(false);

  const tierIdx = layerIndex(n.layer);
  const isTopTier = tierIdx === 0;
  const isToolTier = tierIdx !== null && tierIdx === layers.length - 1;
  const isToolNode = n.kind === "tool";
  const accent = tierColor(tierIdx ?? 0);

  const modelId =
    n.model && typeof n.model.model_id === "string" ? (n.model.model_id as string) : "";
  const nodeIssues = issues.filter((i) => i.node_id === n.id);

  const cls = [
    "cnode",
    selected ? "selected" : "",
    d.hasError ? "error" : "",
    d.onPath ? "on-path" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={cls} style={{ borderColor: accent }}>
      {/* Calls come in from the tier above and go out to the tier below. */}
      <Handle type="target" position={Position.Top} />

      <div className="cnode-title" style={{ background: `${accent}22`, borderColor: accent }}>
        <button
          className="cnode-caret nodrag"
          onClick={() => setCollapsed((c) => !c)}
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? "▸" : "▾"}
        </button>
        <span className="cnode-name" style={{ color: accent }}>
          {n.name || n.id}
        </span>
        <span className="cnode-tier">{n.layer ?? "—"}</span>
        <button
          className="cnode-x nodrag"
          onClick={undo}
          disabled={!canUndo}
          title="Undo"
          aria-label="Undo"
        >
          Undo
        </button>
        <button
          className="cnode-x nodrag"
          onClick={redo}
          disabled={!canRedo}
          title="Redo"
          aria-label="Redo"
        >
          Redo
        </button>
        <button
          className="cnode-x nodrag"
          onClick={() => removeNode(n.id)}
          title="Delete agent"
          aria-label="Delete agent"
        >
          ✕
        </button>
      </div>

      {!collapsed && (
        <div className="cnode-body nodrag nowheel">
          <label className="field">
            name
            <input
              value={n.name ?? ""}
              placeholder={n.id}
              onChange={(e) => updateNode(n.id, { name: e.target.value || null })}
            />
          </label>

          <label className="field">
            kind
            <select
              value={n.kind}
              onChange={(e) =>
                updateNode(n.id, { kind: e.target.value as GraphNode["kind"] })
              }
            >
              <option value="agent">agent</option>
              <option value="tool">tool node</option>
            </select>
          </label>

          <label className="field">
            description
            <textarea
              value={n.description}
              placeholder="One line — used to auto-pick defaults."
              onChange={(e) => updateNode(n.id, { description: e.target.value })}
            />
          </label>

          <label className="field">
            module / export folder
            <input
              value={n.module ?? ""}
              placeholder="paper_research"
              onChange={(e) => updateNode(n.id, { module: e.target.value || null })}
            />
          </label>

          <label className="field">
            tier
            <select value={n.layer ?? ""} onChange={(e) => setNodeLayer(n.id, e.target.value)}>
              {layers.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </label>

          {!isToolNode && (
            <label className="field">
              model
              <select
                value={modelId}
                onChange={(e) =>
                  updateNode(
                    n.id,
                    e.target.value ? { model: { model_id: e.target.value } } : { model: null }
                  )
                }
              >
                <option value="">(auto-resolve)</option>
                {(catalogs?.models ?? []).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.id}
                    {m.supports_tools ? "" : " (no tools)"}
                  </option>
                ))}
              </select>
            </label>
          )}

          {!isToolNode && isTopTier && (
            <label className="field">
              trigger (entry point)
              <select
                value={n.trigger ?? ""}
                onChange={(e) => setTrigger(n.id, (e.target.value || null) as TriggerKind | null)}
              >
                <option value="">none</option>
                <option value="user_query">user query</option>
                <option value="auto_action">auto action</option>
              </select>
            </label>
          )}

          {(isToolNode || isToolTier) && <ToolsPanel node={n} />}

          {nodeIssues.map((iss, i) => (
            <div className="issue" key={i}>
              <span className={`sev ${iss.severity}`}>{iss.severity}</span> {iss.message}
            </div>
          ))}

          {preview && preview.node_id === n.id && (
            <div className={`msg ${preview.ok ? "ok" : "err"}`}>
              {preview.ok ? "Builds cleanly." : preview.error}
            </div>
          )}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
