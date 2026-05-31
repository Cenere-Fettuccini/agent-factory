import { useState } from "react";
import { api } from "../api/client";
import { useCatalog } from "../catalog/CatalogProvider";
import { useGraph } from "../state/graphStore";
import type { GraphNode, IoTypeEntry, ToolDef, ToolDefField } from "../api/types";

interface FieldDraft {
  name: string;
  type_key: string;
  required: boolean;
  description: string;
}

function grantsOf(node: GraphNode): string[] {
  return node.tools && Array.isArray(node.tools.tool_grants)
    ? (node.tools.tool_grants as string[])
    : [];
}

function draftsToFields(drafts: FieldDraft[]): Record<string, ToolDefField> {
  const out: Record<string, ToolDefField> = {};
  for (const f of drafts) {
    const name = f.name.trim();
    if (!name) continue;
    out[name] = {
      type_key: f.type_key,
      required: f.required,
      description: f.description.trim(),
    };
  }
  return out;
}

function fieldsToDrafts(
  fields: Record<string, ToolDefField> | null | undefined,
  defaultType: string,
): FieldDraft[] {
  if (!fields) return [];
  return Object.entries(fields).map(([name, spec]) => ({
    name,
    type_key: spec.type_key || defaultType,
    required: spec.required ?? true,
    description: spec.description ?? "",
  }));
}

// One editable list of typed fields — reused for a tool's arguments and returns.
function FieldEditor({
  heading,
  drafts,
  setDrafts,
  ioTypes,
  defaultType,
  emptyHint,
}: {
  heading: string;
  drafts: FieldDraft[];
  setDrafts: (next: FieldDraft[]) => void;
  ioTypes: IoTypeEntry[];
  defaultType: string;
  emptyHint: string;
}) {
  const patch = (i: number, change: Partial<FieldDraft>) =>
    setDrafts(drafts.map((x, j) => (j === i ? { ...x, ...change } : x)));

  return (
    <div className="field-editor">
      <div className="field-editor-head">{heading}</div>
      {drafts.length === 0 && <div className="field-empty">{emptyHint}</div>}
      {drafts.map((f, i) => (
        <div className="tool-field" key={i}>
          <div className="tool-row">
            <input
              value={f.name}
              placeholder="field name"
              onChange={(e) => patch(i, { name: e.target.value })}
            />
            <select
              value={f.type_key}
              onChange={(e) => patch(i, { type_key: e.target.value })}
            >
              {ioTypes.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.id}
                </option>
              ))}
            </select>
            <label className="req" title="Required field">
              <input
                type="checkbox"
                checked={f.required}
                onChange={(e) => patch(i, { required: e.target.checked })}
              />
              req
            </label>
            <button className="ghost" onClick={() => setDrafts(drafts.filter((_, j) => j !== i))}>
              ✕
            </button>
          </div>
          <input
            className="field-desc"
            value={f.description}
            placeholder="description (optional)"
            onChange={(e) => patch(i, { description: e.target.value })}
          />
        </div>
      ))}
      <button
        className="ghost"
        onClick={() =>
          setDrafts([...drafts, { name: "", type_key: defaultType, required: true, description: "" }])
        }
      >
        + field
      </button>
    </div>
  );
}

// Authoring + granting tools for one agent or tool node. Authored tools are
// carried in the graph's tool_defs (validated by the backend) and exported with
// a real python_import binding or a typed stub the user fills in.
export function ToolsPanel({ node }: { node: GraphNode }) {
  const { catalogs } = useCatalog();
  const toolDefs = useGraph((s) => s.toolDefs);
  const setToolDefs = useGraph((s) => s.setToolDefs);
  const updateNode = useGraph((s) => s.updateNode);

  const ioTypes = catalogs?.io_types ?? [];
  const defaultType = ioTypes[0]?.id ?? "text";

  const [editingId, setEditingId] = useState<string | null>(null);
  const [toolId, setToolId] = useState("");
  const [toolDesc, setToolDesc] = useState("");
  const [bindingModule, setBindingModule] = useState("");
  const [bindingCallable, setBindingCallable] = useState("");
  const [argDrafts, setArgDrafts] = useState<FieldDraft[]>([
    { name: "query", type_key: defaultType, required: true, description: "" },
  ]);
  const [returnDrafts, setReturnDrafts] = useState<FieldDraft[]>([]);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const grants = grantsOf(node);
  const ownedTools = toolDefs.filter((t) => t.node_id === node.id);
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

  function resetForm() {
    setEditingId(null);
    setToolId("");
    setToolDesc("");
    setBindingModule("");
    setBindingCallable("");
    setArgDrafts([{ name: "query", type_key: defaultType, required: true, description: "" }]);
    setReturnDrafts([]);
    setMsg(null);
  }

  // Load an authored tool back into the form so its interface can be edited.
  function editTool(def: ToolDef) {
    setEditingId(def.id);
    setToolId(def.id);
    setToolDesc(def.description);
    setBindingModule(def.binding.module ?? "");
    setBindingCallable(def.binding.callable ?? "");
    setArgDrafts(fieldsToDrafts(def.args, defaultType));
    setReturnDrafts(fieldsToDrafts(def.returns, defaultType));
    setMsg(null);
  }

  async function authorTool() {
    setMsg(null);
    const args = draftsToFields(argDrafts);
    const returnFields = draftsToFields(returnDrafts);
    const module = bindingModule.trim();
    const callable = bindingCallable.trim();
    const def: ToolDef = {
      id: toolId.trim(),
      description: toolDesc.trim(),
      node_id: node.kind === "tool" ? node.id : null,
      binding: {
        kind: module && callable ? "python_import" : "stub",
        module: module || null,
        callable: callable || null,
        is_async: false,
      },
      args,
      // null (not {}) keeps the tool's return interface unset on the backend.
      returns: Object.keys(returnFields).length ? returnFields : null,
    };
    try {
      const result = await api.validateTool(def);
      if (!result.ok) {
        setMsg({ kind: "err", text: result.error ?? "invalid tool" });
        return;
      }
      // Replace any existing def with the same id (also covers renames while
      // editing). Agent nodes grant directly; tool nodes expose their functions
      // to connected agents during Resolve.
      const without = toolDefs.filter((t) => t.id !== def.id && t.id !== editingId);
      setToolDefs([...without, def]);
      if (node.kind !== "tool") {
        setGrants(grants.includes(def.id) ? grants : [...grants, def.id]);
      }
      const bound = def.binding.kind === "python_import";
      setMsg({
        kind: "ok",
        text: bound
          ? `Tool '${def.id}' bound to ${def.binding.module}.${def.binding.callable} — live on export.`
          : node.kind === "tool"
            ? `Tool '${def.id}' added (typed stub — fill in the callable, or set a Python binding).`
            : `Tool '${def.id}' validated and granted (typed stub).`,
      });
      resetForm();
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    }
  }

  return (
    <div>
      <h3>Tools</h3>
      {node.kind === "tool" && ownedTools.length > 0 && (
        <div className="pill-list">
          {ownedTools.map((t) => (
            <span
              key={t.id}
              className={`pill granted ${editingId === t.id ? "editing" : ""}`}
              onClick={() => editTool(t)}
              title="Click to edit this function"
            >
              {t.id}
            </span>
          ))}
        </div>
      )}

      {node.kind !== "tool" && available.length > 0 && (
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
      {node.kind !== "tool" && toolDefs.length > 0 && (
        <div className="pill-list" style={{ marginTop: 6 }}>
          {toolDefs.map((t) => (
            <span
              key={t.id}
              className={`pill edit ${editingId === t.id ? "editing" : ""}`}
              onClick={() => editTool(t)}
              title="Click to edit this tool's interface"
            >
              ✎ {t.id}
            </span>
          ))}
        </div>
      )}

      <h3>
        {editingId
          ? `Edit ${editingId}`
          : node.kind === "tool"
            ? "Add function"
            : "Define a tool"}
      </h3>
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
      <label className="field">
        Python module
        <input
          value={bindingModule}
          onChange={(e) => setBindingModule(e.target.value)}
          placeholder="myapp.tools.search"
        />
      </label>
      <label className="field">
        Callable
        <input
          value={bindingCallable}
          onChange={(e) => setBindingCallable(e.target.value)}
          placeholder="web_search"
        />
      </label>

      <FieldEditor
        heading="Arguments"
        drafts={argDrafts}
        setDrafts={setArgDrafts}
        ioTypes={ioTypes}
        defaultType={defaultType}
        emptyHint="No arguments — the tool takes no input."
      />
      <FieldEditor
        heading="Returns"
        drafts={returnDrafts}
        setDrafts={setReturnDrafts}
        ioTypes={ioTypes}
        defaultType={defaultType}
        emptyHint="No return interface — result is passed back untyped."
      />

      <div className="tool-actions">
        <button onClick={authorTool} disabled={!toolId.trim()}>
          {editingId ? "Update" : "Validate & add"}
        </button>
        {(editingId || toolId.trim()) && (
          <button className="ghost" onClick={resetForm}>
            {editingId ? "Cancel" : "Clear"}
          </button>
        )}
      </div>
      {msg && <div className={`msg ${msg.kind}`}>{msg.text}</div>}
    </div>
  );
}
