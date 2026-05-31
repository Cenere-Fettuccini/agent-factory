// Mirrors of the AgentComposer payloads. These are the *only* place the wire
// shapes are typed; nothing else hardcodes catalog values or layer fields —
// dropdowns bind to /catalogs and forms to /node-types fetched at runtime.

export type TriggerKind = "user_query" | "auto_action";
export type NodeKind = "agent" | "tool";

/** A partial layer config dict. `null`/absent means "unset" — the Resolver fills it. */
export type LayerConfig = Record<string, unknown> | null;

export interface GraphNode {
  kind: NodeKind;
  id: string;
  description: string;
  name: string | null;
  version: string;
  tags: string[];
  module: string | null;
  layer: string | null;
  trigger: TriggerKind | null;
  model: LayerConfig;
  io: LayerConfig;
  tools: LayerConfig;
  policy: LayerConfig;
  errors: LayerConfig;
  telemetry: LayerConfig;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface ToolDefField {
  type_key: string;
  required: boolean;
  description: string;
}

export interface ToolDef {
  id: string;
  description: string;
  node_id: string | null;
  binding: {
    kind: "stub" | "python_import";
    module: string | null;
    callable: string | null;
    is_async: boolean;
  };
  args: Record<string, ToolDefField>;
  returns: Record<string, ToolDefField> | null;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  layers: string[];
  tool_defs: ToolDef[];
}

// ---- introspection ----

export interface ModelCatalogEntry {
  id: string;
  provider: string;
  provider_model_id: string;
  context_window: number;
  supports_tools: boolean;
}

export interface IoTypeEntry {
  id: string;
  description: string;
  python_type: string;
}

export interface ToolCatalogEntry {
  id: string;
  description: string;
  arg_schema: Record<string, unknown>;
  return_schema: Record<string, unknown> | null;
}

export interface ErrorCatalogEntry {
  id: string;
  description: string;
  default_action: string;
}

export interface SinkCatalogEntry {
  id: string;
  kind: string;
  endpoint: string | null;
}

export interface Catalogs {
  models: ModelCatalogEntry[];
  io_types: IoTypeEntry[];
  tools: ToolCatalogEntry[];
  errors: ErrorCatalogEntry[];
  sinks: SinkCatalogEntry[];
}

/** JSON Schema per layer, keyed by layer name. Rendered without hardcoding fields. */
export type NodeTypes = Record<string, Record<string, unknown>>;

// ---- authoring results ----

export interface ValidationIssue {
  severity: "error" | "warning";
  code: string;
  message: string;
  node_id: string | null;
  edge: [string, string] | null;
}

export interface ValidationResult {
  valid: boolean;
  issues: ValidationIssue[];
}

export interface PreviewResult {
  node_id: string;
  ok: boolean;
  agent: Record<string, unknown> | null;
  error: string | null;
}

export interface DryRunNode {
  node_id: string;
  ok: boolean;
  error: string | null;
}

export interface DryRunResult {
  ok: boolean;
  structural: ValidationResult;
  nodes: DryRunNode[];
}

export interface ExportResult {
  destination: string;
  files: string[];
  agent_ids: string[];
}

export interface ToolValidateResult {
  id: string;
  ok: boolean;
  error?: string;
  arg_schema?: Record<string, unknown>;
  return_schema?: Record<string, unknown> | null;
}
