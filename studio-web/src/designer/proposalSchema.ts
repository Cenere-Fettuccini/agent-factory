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
  /** Optional tier. Omitted or unrecognized → the agent is placed tier-less for
   * the user to drag into a lane. */
  layer?: string;
  /** "none" is the SLM-friendly stand-in for "no trigger"; mapped to null on apply. */
  trigger?: TriggerKind | "none";
}

export interface ProposalEdge {
  source: string;
  target: string;
}

/** Explicit deletions. Empty/omitted means "delete nothing" — omission of an
 * existing item never removes it; only listing it here does. */
export interface ProposalRemoval {
  /** Agent ids to delete. */
  agents?: string[];
  /** Tier names to delete (agents left in a deleted tier are deleted too). */
  layers?: string[];
  /** Call edges to delete. */
  edges?: ProposalEdge[];
}

export interface DesignProposal {
  /** Tiers to add or keep, top to bottom. A call edge may stay within a tier or cross to the one below. */
  layers: string[];
  /** Agents to add (new id) or modify (existing id). */
  agents: ProposalAgent[];
  /** Call edges to add. */
  edges: ProposalEdge[];
  /** What to delete. Omitted/empty deletes nothing. */
  remove?: ProposalRemoval;
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
        required: ["id", "description"],
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
    remove: {
      type: "object",
      properties: {
        agents: { type: "array", items: { type: "string" } },
        layers: { type: "array", items: { type: "string" } },
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
    },
  },
  required: ["layers", "agents", "edges"],
} as const;

export const DESIGNER_SYSTEM_PROMPT = `You are a pipeline architect. You design a multi-agent network and return it as a
DELTA against the current design shown above. Output ONLY the changes, not the
whole design.

Output ONLY a JSON object:
- "layers": tier names, ordered top to bottom. Each tier is one stage of work.
  Reuse existing tier names verbatim; add a name to add a tier.
- "agents": agents to add or modify. Each has "id" (lowercase-hyphen, e.g.
  "scope-narrower"), a short SPECIFIC "name", a one-line "description", a
  "layer" (one of the tiers), and optionally "trigger": "user_query" (a top-tier
  entry point the user starts), "auto_action" (fired automatically), or "none".
  Use a NEW id to add an agent; reuse an EXISTING id to modify it.
- "edges": directed calls {"source","target"} where source calls target. An edge
  may go DOWN to the tier directly below, OR sideways to another agent in the
  SAME tier (e.g. a coordinator calling its specialists, or one peer handing
  work to another). Never skip a tier going down.
- "remove": what to DELETE — "agents" (ids), "layers" (names), "edges" (pairs).
  Omit or leave empty to delete nothing.

HOW TO DESIGN — this is the important part:
1. DECOMPOSE the request into its distinct STAGES, one tier per stage. A real
   pipeline has MANY tiers, not two. "First do X, then do Y" means a tier for X
   and a separate tier for Y.
2. ORCHESTRATE — do not have one agent do everything. In most tiers include a
   COORDINATOR agent that delegates to 2-3 specialist agents and gathers their
   results. Wire the coordinator to its specialists with SAME-TIER edges, and
   wire specialists down to the next tier. This is what makes it multi-agent.
3. SEPARATE NETWORKS. When the request names distinct pipelines/sections, give
   each its OWN block of tiers, and connect the last tier of one to the first
   tier of the next (a handoff edge).
4. NAME AGENTS SPECIFICALLY. Each name must describe the exact job in THIS
   domain. NEVER use generic labels like "Agent 1", "Worker", "Processor",
   "Handler", "Analyst", "Manager", or "Node". Good names: "Topic Interviewer",
   "Scope Clarifier", "Query Formulator", "Source Harvester", "Citation Vetter",
   "Outline Architect", "Section Drafter", "Coherence Editor". The name alone
   should make the agent's purpose obvious.
5. Aim for 8-14 agents across the tiers. Never collapse a multi-step request into
   one or two agents.
6. If the request mentions asking the user questions, refinement, clarification,
   or direction-setting, include a user-triggered intake agent and separate agents
   that ask focused follow-up questions before handoff.
7. If the request mentions schedules, recurring scans, iteration, or monitoring,
   model that as a separate automatically-triggered network with scheduler,
   collector, summarizer, idea extractor, and updater roles.
8. If the request mentions schemas, plans, prompts, specs, or handoff contracts,
   include explicit agents that draft, critique, revise, and publish that artifact.

EXAMPLE — request: "Get a topic from the user, then research it into a paper.
Keep topic intake and research as separate networks." A good response on an empty
canvas is:
{
  "layers": ["Topic Intake","Topic Shaping","Research Planning","Source Gathering","Synthesis","Drafting"],
  "agents": [
    {"id":"topic-interviewer","name":"Topic Interviewer","description":"Asks the user what they want to study and captures the raw topic.","layer":"Topic Intake","trigger":"user_query"},
    {"id":"scope-clarifier","name":"Scope Clarifier","description":"Probes for angle, audience, and constraints.","layer":"Topic Intake"},
    {"id":"intake-lead","name":"Intake Lead","description":"Coordinates intake and decides when the topic is well formed.","layer":"Topic Shaping"},
    {"id":"angle-finder","name":"Angle Finder","description":"Proposes a sharp, defensible research angle.","layer":"Topic Shaping"},
    {"id":"keyword-extractor","name":"Keyword Extractor","description":"Distills the angle into search terms.","layer":"Topic Shaping"},
    {"id":"research-director","name":"Research Director","description":"Plans the research and assigns subtopics to gatherers.","layer":"Research Planning"},
    {"id":"subtopic-splitter","name":"Subtopic Splitter","description":"Breaks the angle into researchable questions.","layer":"Research Planning"},
    {"id":"web-harvester","name":"Web Harvester","description":"Collects sources from the open web.","layer":"Source Gathering"},
    {"id":"paper-harvester","name":"Paper Harvester","description":"Collects academic papers and citations.","layer":"Source Gathering"},
    {"id":"citation-vetter","name":"Citation Vetter","description":"Checks each source for credibility and relevance.","layer":"Source Gathering"},
    {"id":"evidence-synthesizer","name":"Evidence Synthesizer","description":"Merges findings into supported claims.","layer":"Synthesis"},
    {"id":"outline-architect","name":"Outline Architect","description":"Builds the paper's section outline from the claims.","layer":"Synthesis"},
    {"id":"section-drafter","name":"Section Drafter","description":"Writes each section from the outline and evidence.","layer":"Drafting"},
    {"id":"coherence-editor","name":"Coherence Editor","description":"Edits the full draft for flow, tone, and consistency.","layer":"Drafting"}
  ],
  "edges": [
    {"source":"topic-interviewer","target":"scope-clarifier"},
    {"source":"scope-clarifier","target":"intake-lead"},
    {"source":"intake-lead","target":"angle-finder"},
    {"source":"intake-lead","target":"keyword-extractor"},
    {"source":"angle-finder","target":"research-director"},
    {"source":"keyword-extractor","target":"research-director"},
    {"source":"research-director","target":"subtopic-splitter"},
    {"source":"subtopic-splitter","target":"web-harvester"},
    {"source":"subtopic-splitter","target":"paper-harvester"},
    {"source":"web-harvester","target":"citation-vetter"},
    {"source":"paper-harvester","target":"citation-vetter"},
    {"source":"citation-vetter","target":"evidence-synthesizer"},
    {"source":"evidence-synthesizer","target":"outline-architect"},
    {"source":"outline-architect","target":"section-drafter"},
    {"source":"section-drafter","target":"coherence-editor"}
  ]
}
Notice in the example: (a) two separate networks — Topic Intake/Topic Shaping,
then Research Planning/Source Gathering/Synthesis/Drafting — joined by the
scope-clarifier -> intake-lead handoff; (b) coordinators ("Intake Lead",
"Research Director") that delegate to specialists in the SAME tier via same-tier
edges; (c) concrete, specific names, never generic ones; (d) 14 agents across 6
tiers. Match this depth and style.

When the request instead asks to TWEAK an existing design, make a small delta and
only touch what it asks for. Only delete what the task asks for — omitting an
existing agent does NOT delete it; list its id under "remove" to drop it. Do not
invent tools or model names.`;

const PROMPT_REFINER_RULES = [
  {
    pattern: /\b(user|human).*\b(question|ask|query|interview|clarif|direction|preference)/i,
    line:
      "Include a user-facing intake network that asks targeted follow-up questions about direction, scope, constraints, audience, and desired output before any orchestrator handoff.",
  },
  {
    pattern: /\b(refine|narrow|clarif|scope|direction|topic)\b/i,
    line:
      "Represent refinement as its own stage with agents for topic capture, scope probing, angle selection, and handoff brief creation.",
  },
  {
    pattern: /\b(orchestrator|handoff|hand off|delegate)\b/i,
    line:
      "Create a clear handoff agent that packages the refined brief and calls the downstream orchestrator or network entry point.",
  },
  {
    pattern: /\b(another|separate|second).*\b(network|flow|pipeline)|\b(network|flow|pipeline).*\b(another|separate|second)/i,
    line:
      "Keep distinct requested networks as distinct tier blocks, connected only by explicit handoff edges.",
  },
  {
    pattern: /\b(schedule|scheduled|recurring|iterate|iterates|monitor|cron|daily|weekly|new papers|new paper)\b/i,
    line:
      "Include an automatically triggered scheduled research network with scheduler, paper discovery, deduplication, relevance screening, summarization, idea extraction, and iteration roles.",
  },
  {
    pattern: /\b(paper|papers|research|academic|citation|arxiv|scholar)\b/i,
    line:
      "For paper gathering, include agents that search for new papers, vet relevance and novelty, summarize contributions, and extract reusable key ideas.",
  },
  {
    pattern: /\b(schema|schemas|spec|contract|format|structured output)\b/i,
    line:
      "For schema work, include agents that synthesize schema candidates, critique them against gathered evidence, revise iteratively, and publish the newest schema version.",
  },
] as const;

/**
 * Small deterministic prompt refiner that turns a rough sentence into the design
 * brief the local SLM is better at following. It does not invent a graph; it
 * makes implicit requirements explicit before constrained JSON generation.
 */
export function refineDesignerPrompt(prompt: string): string {
  const raw = prompt.trim().replace(/\s+/g, " ");
  const refinements = PROMPT_REFINER_RULES.filter((rule) => rule.pattern.test(raw)).map(
    (rule) => rule.line
  );
  const uniqueRefinements = [...new Set(refinements)];

  if (uniqueRefinements.length === 0) return raw;

  return [
    "Refined design brief:",
    raw,
    "",
    "Make these implicit requirements explicit in the proposed network:",
    ...uniqueRefinements.map((line) => `- ${line}`),
    "",
    "Use concrete domain-specific agent names and produce enough agents and tiers to show the full workflow.",
  ].join("\n");
}

/** Snapshot of what's already on the canvas, handed to the model as context. */
export interface CurrentDesign {
  layers: string[];
  agents: {
    id: string;
    description?: string;
    layer: string | null;
    trigger?: TriggerKind | "none" | null;
  }[];
  edges: ProposalEdge[];
}

/**
 * Compact, readable description of the current canvas so the model can see — and
 * extend — what's already there (tiers, each agent's id/tier/description, and the
 * call edges between them) rather than designing blind.
 */
export function describeCurrent(current: CurrentDesign): string {
  const tiers = current.layers.length ? current.layers.join(" -> ") : "(none yet)";
  const agents = current.agents.length
    ? current.agents
        .map((a) => {
          const layer = a.layer ?? "(no tier)";
          const desc = a.description?.trim() ? ` — ${a.description.trim()}` : "";
          return `  - ${a.id} [${layer}]${desc}`;
        })
        .join("\n")
    : "  (none yet)";
  const edges = current.edges.length
    ? current.edges.map((e) => `  - ${e.source} -> ${e.target}`).join("\n")
    : "  (none yet)";
  return `Current tiers: ${tiers}\nCurrent agents:\n${agents}\nCurrent calls:\n${edges}`;
}
