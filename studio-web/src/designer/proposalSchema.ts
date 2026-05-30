// The constrained target an in-browser SLM aims at.
//
// We deliberately do NOT ask the model to emit a full backend `Graph` (partial
// layer dicts, telemetry, error policies…). A 1–3B model writes the *high-level
// structure* — tiers, agents, who-calls-whom — and the backend Resolver fills
// every layer config afterwards. Keeping the grammar small is exactly what makes
// a tiny model reliable: the JSON Schema below is fed to WebLLM's constrained
// decoder, so the model can only emit tokens that keep the output valid. The
// worst case is a structurally-valid-but-odd graph, which `/graph/validate` then
// catches. Two nets.

import type { TriggerKind } from "../api/types";

export interface ProposalAgent {
  id: string;
  name?: string;
  description: string;
  layer: string;
  /** "none" is the SLM-friendly stand-in for "no trigger"; mapped to null on apply. */
  trigger?: TriggerKind | "none";
}

export interface ProposalEdge {
  source: string;
  target: string;
}

export interface DesignProposal {
  /** Network tiers, top to bottom. A call edge may only cross to the tier below. */
  layers: string[];
  agents: ProposalAgent[];
  edges: ProposalEdge[];
}

// JSON Schema handed to WebLLM (`response_format.schema`). Kept to the XGrammar
// subset: objects, arrays, strings, enums, required. No $ref, no oneOf.
export const PROPOSAL_JSON_SCHEMA = {
  type: "object",
  properties: {
    layers: {
      type: "array",
      items: { type: "string" },
    },
    agents: {
      type: "array",
      items: {
        type: "object",
        properties: {
          id: { type: "string" },
          name: { type: "string" },
          description: { type: "string" },
          layer: { type: "string" },
          trigger: { type: "string", enum: ["user_query", "auto_action", "none"] },
        },
        required: ["id", "description", "layer"],
      },
    },
    edges: {
      type: "array",
      items: {
        type: "object",
        properties: {
          source: { type: "string" },
          target: { type: "string" },
        },
        required: ["source", "target"],
      },
    },
  },
  required: ["layers", "agents", "edges"],
} as const;

export const DESIGNER_SYSTEM_PROMPT = `You design layered networks of AI agents.

Output ONLY a JSON object with this shape:
- "layers": tier names, ordered top to bottom (e.g. the top tier refines the user
  request, the middle tier orchestrates, the bottom tier holds tool-using workers).
- "agents": each has "id" (lowercase, letters/digits/hyphen, e.g. "ticket_router"),
  a one-line "description", the "layer" it belongs to (must be one of "layers"),
  and optionally "trigger": "user_query" for a top-tier entry point a user starts,
  "auto_action" for one fired automatically, or "none".
- "edges": directed calls {"source","target"} where source calls target. An edge
  may only go from a tier to the tier directly below it.

Keep it small and sensible: 2-4 tiers, only the agents the task needs. Do not
invent tools or model names — only the structure. Reuse the existing tiers and
agents given as context when the user asks to extend the design.`;

/** Compact context string so the model can extend the current canvas. */
export function describeCurrent(layers: string[], agentIds: string[]): string {
  const tiers = layers.length ? layers.join(" -> ") : "(none yet)";
  const agents = agentIds.length ? agentIds.join(", ") : "(none yet)";
  return `Current tiers: ${tiers}\nCurrent agents: ${agents}`;
}
