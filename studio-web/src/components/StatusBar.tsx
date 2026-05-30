import { useCatalog } from "../catalog/CatalogProvider";
import { useGraph } from "../state/graphStore";

export function StatusBar() {
  const { connected, error } = useCatalog();
  const issues = useGraph((s) => s.issues);
  const dryRun = useGraph((s) => s.dryRun);

  const errors = issues.filter((i) => i.severity === "error").length;
  const warnings = issues.filter((i) => i.severity === "warning").length;

  return (
    <div className="statusbar">
      <span className="status-pill">
        <span className={`dot ${connected ? "ok" : "bad"}`} />
        {connected ? "Connected to AgentComposer" : "Disconnected"}
      </span>
      {!connected && error && <span className="count err">· {error}</span>}
      {connected && (
        <>
          <span className={errors ? "count err" : "count ok"}>
            {errors} error{errors === 1 ? "" : "s"}
          </span>
          <span className={warnings ? "count warn" : ""}>
            {warnings} warning{warnings === 1 ? "" : "s"}
          </span>
          {dryRun && (
            <span className={dryRun.ok ? "count ok" : "count err"}>
              · dry-run {dryRun.ok ? "green" : "failing"}
            </span>
          )}
        </>
      )}
    </div>
  );
}
