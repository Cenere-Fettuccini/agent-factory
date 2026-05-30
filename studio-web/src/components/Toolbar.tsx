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
  const [newLayer, setNewLayer] = useState("");

  return (
    <div className="toolbar">
      <div className="title">
        Agent <span>Studio</span>
      </div>

      {/* Palette: drag onto a tier lane to add an agent. */}
      <div
        draggable
        onDragStart={(e) => {
          e.dataTransfer.setData("application/agent-node", "1");
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
        title={!dryRun?.ok ? "Pass a dry-run first" : "Export to a folder"}
      >
        Export
      </button>
    </div>
  );
}
