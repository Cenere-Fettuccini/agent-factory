import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { GraphNode } from "../api/types";

export interface AgentNodeData {
  node: GraphNode;
  hasError: boolean;
  errorMsg: string | null;
  onPath: boolean;
  isTopTier: boolean;
  [key: string]: unknown;
}

export function AgentNode({ data, selected }: NodeProps) {
  const d = data as AgentNodeData;
  const n = d.node;
  const modelId =
    n.model && typeof n.model.model_id === "string" ? (n.model.model_id as string) : null;
  const grants =
    n.tools && Array.isArray(n.tools.tool_grants)
      ? (n.tools.tool_grants as string[])
      : [];

  const cls = [
    "agent-node",
    selected ? "selected" : "",
    d.hasError ? "error" : "",
    d.onPath ? "on-path" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={cls}>
      {/* Calls come in from the tier above (top) and go out to the tier below (bottom). */}
      <Handle type="target" position={Position.Top} />
      <div className="nid">{n.name || n.id}</div>
      <div className="desc">{n.description || "—"}</div>
      <div className="model">{modelId ?? "model: (auto)"}</div>
      <div>
        {n.trigger && (
          <span className="badge trigger">
            {n.trigger === "user_query" ? "user query" : "auto action"}
          </span>
        )}
        {grants.map((g) => (
          <span key={g} className="badge">
            🔧 {g}
          </span>
        ))}
      </div>
      {d.hasError && d.errorMsg && <div className="node-err">{d.errorMsg}</div>}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
