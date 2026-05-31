import { useState } from "react";
import { useCatalog } from "../catalog/CatalogProvider";
import { useGraph } from "../state/graphStore";

interface ToolbarProps {
  onResolve: () => void;
  onDryRun: () => void;
  onExport: () => void;
}

export function Toolbar({ onResolve, onDryRun, onExport }: ToolbarProps) {
  const { connected } = useCatalog();
  const autoResolve = useGraph((s) => s.autoResolve);
  const toggleAutoResolve = useGraph((s) => s.toggleAutoResolve);
  const addLayer = useGraph((s) => s.addLayer);
  const dryRun = useGraph((s) => s.dryRun);
  const canUndo = useGraph((s) => s.undoStack.length > 0);
  const canRedo = useGraph((s) => s.redoStack.length > 0);
  const undo = useGraph((s) => s.undo);
  const redo = useGraph((s) => s.redo);
  const [newLayer, setNewLayer] = useState("");
  const exportDisabledReason = !connected
    ? "Connect to the AgentComposer API first"
    : !dryRun?.ok
      ? "Run Dry-run successfully before exporting"
      : "Export to a folder";

  return (
    <div className="toolbar">
      <div className="title">
        Agent <span>Studio</span>
      </div>

      {/* Palette: drag onto a tier lane to add an agent. */}
      <div
        draggable
        onDragStart={(e) => {
          e.dataTransfer.setData("application/agent-node", "agent");
          e.dataTransfer.effectAllowed = "move";
        }}
        style={{
          border: "1px dashed var(--era3)",
          borderRadius: 7,
          padding: "6px 12px",
          fontSize: 13,
          cursor: "grab",
          color: "var(--era3)",
        }}
        title="Drag onto a tier lane to add an agent"
      >
        + Agent (drag)
      </div>

      <div
        draggable
        onDragStart={(e) => {
          e.dataTransfer.setData("application/agent-node", "tool");
          e.dataTransfer.effectAllowed = "move";
        }}
        style={{
          border: "1px dashed var(--era2)",
          borderRadius: 7,
          padding: "6px 12px",
          fontSize: 13,
          cursor: "grab",
          color: "var(--era2)",
        }}
        title="Drag onto a tier lane to add a tool provider node"
      >
        + Tool node
      </div>

      <input
        value={newLayer}
        onChange={(e) => setNewLayer(e.target.value)}
        placeholder="new tier…"
        style={{
          background: "var(--panel-2)",
          color: "var(--ink)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          padding: "5px 8px",
          width: 110,
        }}
      />
      <button
        className="ghost"
        onClick={() => {
          if (newLayer.trim()) {
            addLayer(newLayer.trim());
            setNewLayer("");
          }
        }}
      >
        Add tier
      </button>

      <div className="spacer" />

      <button className="ghost" onClick={undo} disabled={!canUndo} title="Undo">
        Undo
      </button>
      <button className="ghost" onClick={redo} disabled={!canRedo} title="Redo">
        Redo
      </button>

      <label className="toggle">
        <input type="checkbox" checked={autoResolve} onChange={toggleAutoResolve} />
        auto-resolve
      </label>
      <button onClick={onResolve} disabled={!connected}>
        Resolve
      </button>
      <button onClick={onDryRun} disabled={!connected}>
        Dry-run
      </button>
      <button
        className="primary"
        onClick={onExport}
        disabled={!connected || !dryRun?.ok}
        title={exportDisabledReason}
      >
        Export
      </button>
    </div>
  );
}
