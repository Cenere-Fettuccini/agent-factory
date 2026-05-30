import { useCatalog } from "../catalog/CatalogProvider";
import { useGraph } from "../state/graphStore";
import { ToolsPanel } from "./ToolsPanel";
import type { TriggerKind } from "../api/types";

export function Inspector() {
  const { catalogs } = useCatalog();
  const node = useGraph((s) => s.nodes.find((n) => n.id === s.selectedNodeId) ?? null);
  const layers = useGraph((s) => s.layers);
  const layerIndex = useGraph((s) => s.layerIndex);
  const updateNode = useGraph((s) => s.updateNode);
  const setTrigger = useGraph((s) => s.setTrigger);
  const setNodeLayer = useGraph((s) => s.setNodeLayer);
  const removeNode = useGraph((s) => s.removeNode);
  const preview = useGraph((s) => s.preview);
  const issues = useGraph((s) => s.issues);

  if (!node) {
    return (
      <div className="inspector">
        <p className="empty">
          Drag <strong>+ Agent</strong> onto a tier, then select a node to edit it.
          You only set its model and (for tool agents) its tools — everything else
          auto-resolves.
        </p>
      </div>
    );
  }

  const modelId =
    node.model && typeof node.model.model_id === "string"
      ? (node.model.model_id as string)
      : "";
  const isTopTier = layerIndex(node.layer) === 0;
  const isToolTier = node.layer !== null && layerIndex(node.layer) === layers.length - 1;
  const nodeIssues = issues.filter((i) => i.node_id === node.id);

  return (
    <div className="inspector">
      <h3>Agent · {node.id}</h3>

      <label className="field">
        name
        <input
          value={node.name ?? ""}
          onChange={(e) => updateNode(node.id, { name: e.target.value || null })}
        />
      </label>
      <label className="field">
        description
        <textarea
          value={node.description}
          onChange={(e) => updateNode(node.id, { description: e.target.value })}
          placeholder="One line — used to auto-pick defaults."
        />
      </label>

      <label className="field">
        tier
        <select value={node.layer ?? ""} onChange={(e) => setNodeLayer(node.id, e.target.value)}>
          {layers.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
      </label>

      <h3>Model</h3>
      <label className="field">
        model
        <select
          value={modelId}
          onChange={(e) =>
            updateNode(node.id, e.target.value ? { model: { model_id: e.target.value } } : { model: null })
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

      {isTopTier && (
        <>
          <h3>Trigger (entry point)</h3>
          <label className="field">
            <select
              value={node.trigger ?? ""}
              onChange={(e) =>
                setTrigger(node.id, (e.target.value || null) as TriggerKind | null)
              }
            >
              <option value="">none</option>
              <option value="user_query">user query</option>
              <option value="auto_action">auto action</option>
            </select>
          </label>
        </>
      )}

      {isToolTier && <ToolsPanel node={node} />}

      {nodeIssues.length > 0 && (
        <>
          <h3>Issues</h3>
          {nodeIssues.map((iss, i) => (
            <div className="issue" key={i}>
              <span className={`sev ${iss.severity}`}>{iss.severity}</span> {iss.message}
            </div>
          ))}
        </>
      )}

      {preview && preview.node_id === node.id && (
        <>
          <h3>Preview</h3>
          {preview.ok ? (
            <div className="msg ok">Builds cleanly.</div>
          ) : (
            <div className="msg err">{preview.error}</div>
          )}
        </>
      )}

      <h3>&nbsp;</h3>
      <button className="ghost" onClick={() => removeNode(node.id)}>
        Delete agent
      </button>
    </div>
  );
}
