import { useState } from "react";
import { api } from "../api/client";
import { useCatalog } from "../catalog/CatalogProvider";
import { useGraph } from "../state/graphStore";
import type { GraphNode, ToolDef, ToolDefField } from "../api/types";

interface FieldDraft {
  name: string;
  type_key: string;
}

function grantsOf(node: GraphNode): string[] {
  return node.tools && Array.isArray(node.tools.tool_grants)
    ? (node.tools.tool_grants as string[])
    : [];
}

// Authoring + granting tools for one agent. Authored tools are carried in the
// graph's tool_defs (validated by the backend) and exported as typed stubs.
export function ToolsPanel({ node }: { node: GraphNode }) {
  const { catalogs } = useCatalog();
  const toolDefs = useGraph((s) => s.toolDefs);
  const setToolDefs = useGraph((s) => s.setToolDefs);
  const updateNode = useGraph((s) => s.updateNode);

  const ioTypes = catalogs?.io_types ?? [];
  const defaultType = ioTypes[0]?.id ?? "text";

  const [toolId, setToolId] = useState("");
  const [toolDesc, setToolDesc] = useState("");
  const [fields, setFields] = useState<FieldDraft[]>([{ name: "query", type_key: defaultType }]);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const grants = grantsOf(node);
  const available = [
    ...(catalogs?.tools ?? []).map((t) => t.id),
    ...toolDefs.map((t) => t.id),
  ].filter((v, i, a) => a.indexOf(v) === i);

  function setGrants(next: string[]) {
    const existing = (node.tools as Record<string, unknown> | null) ?? {};
    updateNode(node.id, { tools: { ...existing, tool_grants: next } });
  }

  function toggleGrant(id: string) {
    setGrants(grants.includes(id) ? grants.filter((g) => g !== id) : [...grants, id]);
  }

  async function authorTool() {
    setMsg(null);
    const args: Record<string, ToolDefField> = {};
    for (const f of fields) {
      if (!f.name.trim()) continue;
      args[f.name.trim()] = { type_key: f.type_key, required: true, description: "" };
    }
    const def: ToolDef = { id: toolId.trim(), description: toolDesc.trim(), args, returns: null };
    try {
      const result = await api.validateTool(def);
      if (!result.ok) {
        setMsg({ kind: "err", text: result.error ?? "invalid tool" });
        return;
      }
      // Replace any existing def with the same id, then grant it to this node.
      setToolDefs([...toolDefs.filter((t) => t.id !== def.id), def]);
      setGrants(grants.includes(def.id) ? grants : [...grants, def.id]);
      setMsg({ kind: "ok", text: `Tool '${def.id}' validated and granted.` });
      setToolId("");
      setToolDesc("");
      setFields([{ name: "query", type_key: defaultType }]);
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    }
  }

  return (
    <div>
      <h3>Tools</h3>
      {available.length > 0 && (
        <div className="pill-list">
          {available.map((id) => (
            <span
              key={id}
              className={`pill ${grants.includes(id) ? "granted" : ""}`}
              onClick={() => toggleGrant(id)}
              title={grants.includes(id) ? "Click to revoke" : "Click to grant"}
            >
              {grants.includes(id) ? "✓ " : "+ "}
              {id}
            </span>
          ))}
        </div>
      )}

      <h3>Define a tool</h3>
      <label className="field">
        id
        <input
          value={toolId}
          onChange={(e) => setToolId(e.target.value)}
          placeholder="web-search"
        />
      </label>
      <label className="field">
        description
        <input value={toolDesc} onChange={(e) => setToolDesc(e.target.value)} />
      </label>
      {fields.map((f, i) => (
        <div className="tool-row" key={i}>
          <input
            value={f.name}
            placeholder="arg name"
            onChange={(e) =>
              setFields(fields.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))
            }
          />
          <select
            value={f.type_key}
            onChange={(e) =>
              setFields(fields.map((x, j) => (j === i ? { ...x, type_key: e.target.value } : x)))
            }
          >
            {ioTypes.map((t) => (
              <option key={t.id} value={t.id}>
                {t.id}
              </option>
            ))}
          </select>
          <button
            className="ghost"
            onClick={() => setFields(fields.filter((_, j) => j !== i))}
            disabled={fields.length === 1}
          >
            ✕
          </button>
        </div>
      ))}
      <button
        className="ghost"
        onClick={() => setFields([...fields, { name: "", type_key: defaultType }])}
      >
        + arg
      </button>{" "}
      <button onClick={authorTool} disabled={!toolId.trim()}>
        Validate &amp; add
      </button>
      {msg && <div className={`msg ${msg.kind}`}>{msg.text}</div>}
    </div>
  );
}
