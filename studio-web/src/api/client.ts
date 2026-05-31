// Thin typed fetch wrapper over the AgentComposer API. The UI never reimplements
// validation or owns the filesystem — every answer comes from these endpoints.

import type {
  Catalogs,
  DryRunResult,
  ExportResult,
  Graph,
  GraphNode,
  NodeTypes,
  PreviewResult,
  ToolDef,
  ToolValidateResult,
  ValidationResult,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      // non-JSON error body; keep the status text
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

const post = <T>(path: string, body: unknown): Promise<T> =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  base: BASE,
  health: () => request<{ status: string }>("/health"),
  catalogs: () => request<Catalogs>("/catalogs"),
  nodeTypes: () => request<NodeTypes>("/node-types"),
  validateGraph: (graph: Graph) => post<ValidationResult>("/graph/validate", graph),
  resolve: (graph: Graph) => post<Graph>("/presets/resolve", graph),
  preview: (node: GraphNode, graph: Graph) =>
    post<PreviewResult>("/agents/preview", { node, tool_defs: graph.tool_defs, graph }),
  validateTool: (toolDef: ToolDef) => post<ToolValidateResult>("/tools/validate", toolDef),
  dryRun: (graph: Graph) => post<DryRunResult>("/export/dry-run", graph),
  export: (graph: Graph, destination: string, overwrite: boolean) =>
    post<ExportResult>("/export", { graph, destination, overwrite }),
};
