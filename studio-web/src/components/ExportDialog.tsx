import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useGraph } from "../state/graphStore";

export function ExportDialog({ onClose }: { onClose: () => void }) {
  const toGraph = useGraph((s) => s.toGraph);
  const [destination, setDestination] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  async function doExport() {
    setBusy(true);
    setResult(null);
    try {
      const res = await api.export(toGraph(), destination, overwrite);
      setResult({
        kind: "ok",
        text: `Wrote ${res.files.length} files to ${res.destination}\nAgents: ${res.agent_ids.join(", ")}`,
      });
    } catch (e) {
      // The API owns the filesystem — surface its refusal reason verbatim.
      const text = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e);
      setResult({ kind: "err", text });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h2>Export project</h2>
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>
          The backend writes the folder — enter an absolute path on the server host.
        </p>
        <label className="field">
          destination (absolute path)
          <input
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            placeholder="C:\\Users\\me\\my-agents"
            autoFocus
          />
        </label>
        <label className="toggle" style={{ marginTop: 8 }}>
          <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
          overwrite if not empty
        </label>
        {result && <div className={`msg ${result.kind}`}>{result.text}</div>}
        <div className="row">
          <button className="ghost" onClick={onClose}>
            Close
          </button>
          <button className="primary" onClick={doExport} disabled={busy || !destination.trim()}>
            {busy ? "Exporting…" : "Export"}
          </button>
        </div>
      </div>
    </div>
  );
}
