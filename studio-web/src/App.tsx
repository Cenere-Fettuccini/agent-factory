import { useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import { useCatalog } from "./catalog/CatalogProvider";
import { useGraph } from "./state/graphStore";
import { TierCanvas } from "./canvas/TierCanvas";
import { DesignerPanel } from "./components/DesignerPanel";
import { Toolbar } from "./components/Toolbar";
import { Inspector } from "./components/Inspector";
import { StatusBar } from "./components/StatusBar";
import { ExportDialog } from "./components/ExportDialog";

const DEBOUNCE_MS = 300;

export function App() {
  const { connected } = useCatalog();
  const autoResolve = useGraph((s) => s.autoResolve);
  const structuralRev = useGraph((s) => s.structuralRev);
  const graphRev = useGraph((s) => s.graphRev);
  const selectedId = useGraph((s) => s.selectedNodeId);
  const [showExport, setShowExport] = useState(false);

  // Structural changes (adds/deletes/edges/tiers) -> debounced Resolve. Parameter
  // edits never reach here, so resolve can't clobber what the user is typing.
  const didMount = useRef(false);
  useEffect(() => {
    if (!connected || !autoResolve) return;
    if (!didMount.current) {
      didMount.current = true;
      return;
    }
    const t = setTimeout(runResolve, DEBOUNCE_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structuralRev, connected, autoResolve]);

  // Any change -> debounced Validate.
  useEffect(() => {
    if (!connected) return;
    const t = setTimeout(runValidate, DEBOUNCE_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphRev, connected]);

  // Selecting a node (or its config changing) -> preview it.
  useEffect(() => {
    if (!connected || !selectedId) {
      useGraph.getState().setPreview(null);
      return;
    }
    const t = setTimeout(runPreview, DEBOUNCE_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, graphRev, connected]);

  async function runResolve() {
    const s = useGraph.getState();
    try {
      const resolved = await api.resolve(s.toGraph());
      s.mergeResolved(resolved);
    } catch {
      /* validation surfaces problems; a resolve hiccup is non-fatal */
    }
  }

  async function runValidate() {
    const s = useGraph.getState();
    try {
      const result = await api.validateGraph(s.toGraph());
      s.setIssues(result.issues);
    } catch {
      /* leave prior issues in place if the call fails */
    }
  }

  async function runPreview() {
    const s = useGraph.getState();
    const node = s.nodes.find((n) => n.id === s.selectedNodeId);
    if (!node) return;
    try {
      s.setPreview(await api.preview(node, s.toGraph().tool_defs));
    } catch {
      /* ignore preview transport errors */
    }
  }

  async function runDryRun() {
    const s = useGraph.getState();
    try {
      const result = await api.dryRun(s.toGraph());
      s.setDryRun(result);
      s.setIssues(result.structural.issues);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="app">
      <Toolbar onResolve={runResolve} onDryRun={runDryRun} onExport={() => setShowExport(true)} />
      {!connected && (
        <div className="banner">
          Not connected to the AgentComposer API. Start it with{" "}
          <code>uv run uvicorn composer.app:app --reload</code>. Resolve, dry-run, and export
          are disabled until it&apos;s reachable.
        </div>
      )}
      <div className="body">
        <div className="canvas-wrap">
          <TierCanvas />
          <DesignerPanel />
        </div>
        <Inspector />
      </div>
      <StatusBar />
      {showExport && <ExportDialog onClose={() => setShowExport(false)} />}
    </div>
  );
}
