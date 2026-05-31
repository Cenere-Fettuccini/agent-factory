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
  /** Functional module/network used for export folders. */
  module?: string;
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
          module: { type: "string" },
          layer: { type: "string" },
          trigger: { type: "string", enum: ["user_query", "auto_action", "none"] },
        },
        required: ["id", "description", "module"],
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

Important vocabulary:
- A CANVAS LAYER/TIER is an execution-role separation: user-question intake,
  prompt/spec refinement, model-facing reasoning, orchestration/delegation, tool
  interaction, evidence synthesis, review, publishing, etc.
- A FUNCTIONAL NETWORK is a larger workflow/module such as ideation, planning,
  paper collection, analysis, or summarization. Do NOT turn those module names
  into graph layers by default. Represent them as connected groups of agents and
  handoff points inside the role/function tiers. Folder/module separation happens
  outside this graph.

Output ONLY a JSON object:
- "layers": execution-role tier names, ordered top to bottom. Each tier says
  what the agents in that band DO, not the product/project module they belong to.
  Reuse existing tier names verbatim; add a name only when the role separation is
  missing.
- "agents": agents to add or modify. Each has "id" (lowercase-hyphen, e.g.
  "scope-narrower"), a short SPECIFIC "name", a one-line "description", a
  "module" (functional network/folder, lowercase snake or hyphen words), a
  "layer" (one of the execution-role tiers), and optionally "trigger":
  "user_query" (a top-tier entry point the user starts), "auto_action" (fired
  automatically), or "none". Use a NEW id to add an agent; reuse an EXISTING id
  to modify it.
- "edges": directed calls {"source","target"} where source calls target. An edge
  may go DOWN to the tier directly below, OR sideways to another agent in the
  SAME tier (e.g. a coordinator calling its specialists, or one peer handing
  work to another). Never skip a tier going down.
- "remove": what to DELETE — "agents" (ids), "layers" (names), "edges" (pairs).
  Omit or leave empty to delete nothing.

HOW TO DESIGN — this is the important part:
1. DECOMPOSE by execution role. Use tiers for what the agents do: ask the user,
   refine the brief, plan, orchestrate/delegate, call models/tools, synthesize,
   critique, and publish. If the request names modules like ideation, planning,
   collection, analysis, or summary, model those as connected agent groups and
   handoff briefs, not automatically as layer names.
2. ORCHESTRATE — do not have one agent do everything. In most tiers include a
   COORDINATOR agent that delegates to 2-3 specialist agents and gathers their
   results. Wire the coordinator to its specialists with SAME-TIER edges, and
   wire specialists down to the next tier. This is what makes it multi-agent.
3. CONNECT THE GRAPH. Every new agent should have at least one incoming or
   outgoing edge unless the user explicitly asks for an unconnected staging node.
   Multiple agents may call the same downstream agent. Prefer a real handoff edge
   over leaving an isolated idea on the canvas.
4. MODIFY BEFORE CLONING. If an existing agent already owns the requested
   function, reuse its exact existing id and improve its name/description/layer
   instead of adding a duplicate. Never create "refined", "updated", or
   "improved" copies of an existing node.
5. NAME AGENTS SPECIFICALLY. Each name must describe the exact job in THIS
   domain. NEVER use generic labels like "Agent 1", "Worker", "Processor",
   "Handler", "Analyst", "Manager", or "Node". Good names: "Topic Interviewer",
   "Scope Clarifier", "Query Formulator", "Source Harvester", "Citation Vetter",
   "Outline Architect", "Section Drafter", "Coherence Editor". The name alone
   should make the agent's purpose obvious.
6. Aim for 8-14 agents across the tiers. Never collapse a multi-step request into
   one or two agents.
7. If the request mentions asking the user questions, refinement, clarification,
   or direction-setting, include a user-triggered intake agent and separate agents
   that ask focused follow-up questions before handoff.
8. If the request mentions schedules, recurring scans, iteration, or monitoring,
   model that as a separate automatically-triggered network with scheduler,
   collector, summarizer, idea extractor, and updater roles.
9. If the request mentions schemas, plans, prompts, specs, or handoff contracts,
   include explicit agents that draft, critique, revise, and publish that artifact.

EXAMPLE — request: "Get a topic from the user, then research it into a paper.
Keep topic intake and research as separate functional networks." A good response on an empty
canvas is:
{
  "layers": ["User Intake","Brief Refinement","Planning","Tool Collection","Synthesis","Publishing"],
  "agents": [
    {"id":"topic-interviewer","name":"Topic Interviewer","description":"Asks the user what they want to study and captures the raw topic.","module":"topic_intake","layer":"User Intake","trigger":"user_query"},
    {"id":"scope-clarifier","name":"Scope Clarifier","description":"Probes for angle, audience, and constraints.","module":"topic_intake","layer":"User Intake"},
    {"id":"intake-lead","name":"Intake Lead","description":"Coordinates intake and decides when the topic is well formed.","module":"topic_intake","layer":"Brief Refinement"},
    {"id":"angle-finder","name":"Angle Finder","description":"Proposes a sharp, defensible research angle.","module":"topic_intake","layer":"Brief Refinement"},
    {"id":"keyword-extractor","name":"Keyword Extractor","description":"Distills the angle into search terms.","module":"topic_intake","layer":"Brief Refinement"},
    {"id":"research-director","name":"Research Director","description":"Plans the research and assigns subtopics to gatherers.","module":"paper_research","layer":"Planning"},
    {"id":"subtopic-splitter","name":"Subtopic Splitter","description":"Breaks the angle into researchable questions.","module":"paper_research","layer":"Planning"},
    {"id":"web-harvester","name":"Web Harvester","description":"Collects sources from the open web.","module":"paper_research","layer":"Tool Collection"},
    {"id":"paper-harvester","name":"Paper Harvester","description":"Collects academic papers and citations.","module":"paper_research","layer":"Tool Collection"},
    {"id":"citation-vetter","name":"Citation Vetter","description":"Checks each source for credibility and relevance.","module":"paper_research","layer":"Tool Collection"},
    {"id":"evidence-synthesizer","name":"Evidence Synthesizer","description":"Merges findings into supported claims.","module":"paper_writing","layer":"Synthesis"},
    {"id":"outline-architect","name":"Outline Architect","description":"Builds the paper's section outline from the claims.","module":"paper_writing","layer":"Synthesis"},
    {"id":"section-drafter","name":"Section Drafter","description":"Writes each section from the outline and evidence.","module":"paper_writing","layer":"Publishing"},
    {"id":"coherence-editor","name":"Coherence Editor","description":"Edits the full draft for flow, tone, and consistency.","module":"paper_writing","layer":"Publishing"}
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
Notice in the example: (a) two separate functional networks — topic intake,
then paper research/writing — represented as connected agent groups inside
role/function tiers and joined by the scope-clarifier -> intake-lead handoff; (b) coordinators ("Intake Lead",
"Research Director") that delegate to specialists in the SAME tier via same-tier
edges; (c) concrete, specific names, never generic ones; (d) 14 agents across 6
tiers. Match this depth and style.

When the request instead asks to TWEAK an existing design, make a small delta and
only touch what it asks for. Only delete what the task asks for — omitting an
existing agent does NOT delete it; list its id under "remove" to drop it. Do not
invent tools or model names. Prefer improving existing nodes and edges over
adding parallel duplicates.`;

const PROMPT_REFINER_RULES = [
  {
    pattern: /\b(user|human).*\b(question|ask|query|interview|clarif|direction|preference)/i,
    line:
      "Put all user-topic questioning and refinement agents in module topic_refinement. Include targeted follow-up questions about direction, scope, constraints, audience, and desired output before any orchestrator handoff.",
  },
  {
    pattern: /\b(refine|narrow|clarif|scope|direction|topic)\b/i,
    line:
      "Use module topic_refinement for topic capture, scope probing, direction selection, refinement, and handoff brief creation.",
  },
  {
    pattern: /\b(orchestrator|handoff|hand off|delegate)\b/i,
    line:
      "Create a clear handoff agent in module topic_refinement that packages the refined brief and calls the downstream orchestrator or network entry point.",
  },
  {
    pattern: /\b(another|separate|second).*\b(network|flow|pipeline)|\b(network|flow|pipeline).*\b(another|separate|second)/i,
    line:
      "Treat distinct requested networks as functional modules: keep them visibly separate through agent names and handoff agents, but keep graph layers reserved for execution roles.",
  },
  {
    pattern: /\b(modify|update|revise|improve|refine|change|edit|existing|current)\b/i,
    line:
      "Prefer reusing existing agent ids to improve the current nodes; do not add duplicate '-refined' or parallel nodes for the same function.",
  },
  {
    pattern: /\b(connect|wire|edge|handoff|call|unconnected|orphan)\b/i,
    line:
      "Every new or modified agent should be connected with valid same-tier or next-tier call edges unless explicitly described as a staging node.",
  },
  {
    pattern: /\b(schedule|scheduled|recurring|iterate|iterates|monitor|cron|daily|weekly|new papers|new paper)\b/i,
    line:
      "Use module scheduled_paper_research for the automatically triggered scheduled research network: scheduler, paper discovery, deduplication, relevance screening, summarization, key idea extraction, and iteration roles.",
  },
  {
    pattern: /\b(paper|papers|research|academic|citation|arxiv|scholar)\b/i,
    line:
      "For paper gathering use module scheduled_paper_research and include agents that search for new papers, vet relevance and novelty, summarize contributions, and extract reusable key ideas.",
  },
  {
    pattern: /\b(schema|schemas|spec|contract|format|structured output)\b/i,
    line:
      "Use module schema_iteration for schema work: synthesize schema candidates, critique them against gathered evidence, revise iteratively, and publish the newest schema version.",
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
    "Use module names as export folders. For this kind of request prefer topic_refinement, scheduled_paper_research, and schema_iteration.",
  ].join("\n");
}

function stripRefinedSuffix(value: string): string {
  return value
    .replace(/\s*\((?:re)?refined\)\s*$/i, "")
    .replace(/[-_](?:re)?refined$/i, "")
    .trim();
}

function normalizeLayer(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase().replace(/\s+/g, " ");
}

function slugModule(value: string | null | undefined): string | undefined {
  const slug = (value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
  if (!slug) return undefined;
  return /^[a-z]/.test(slug) ? slug : `module_${slug}`;
}

function inferModule(agent: ProposalAgent): string | undefined {
  const text = `${agent.id} ${agent.name ?? ""} ${agent.description} ${agent.module ?? ""}`
    .toLowerCase()
    .replace(/[_-]+/g, " ");
  if (/\b(schema|schemas|contract|structured output|version|candidate|critique|publish)\b/.test(text)) {
    return "schema_iteration";
  }
  if (
    /\b(schedule|scheduled|recurring|cron|daily|weekly|paper|papers|citation|arxiv|scholar|source|sources|novelty|summar|key idea|evidence)\b/.test(
      text
    )
  ) {
    return "scheduled_paper_research";
  }
  if (
    /\b(topic|user|human|question|ask|interview|clarif|scope|direction|preference|brief|handoff|orchestrator)\b/.test(
      text
    )
  ) {
    return "topic_refinement";
  }
  return slugModule(agent.module);
}

function normalizeAgentModule(agent: ProposalAgent): string | undefined {
  const slug = slugModule(agent.module);
  if (
    !slug ||
    ["network", "flow", "pipeline", "default", "general", "main", "research"].includes(slug)
  ) {
    return inferModule(agent);
  }
  return inferModule(agent) ?? slug;
}

/**
 * Tiny-model cleanup pass. The prompt tells the model to modify existing agents
 * and wire new ones in, but small local models sometimes emit foo-refined clones
 * or isolated nodes. This deterministic pass keeps the output as a delta while
 * nudging it toward graph-shaped edits.
 */
export function normalizeProposal(
  proposal: DesignProposal,
  current: CurrentDesign
): DesignProposal {
  const existingIds = new Set(current.agents.map((a) => a.id));
  const idMap = new Map<string, string>();

  const agents = proposal.agents.map((agent) => {
    const baseId = stripRefinedSuffix(agent.id);
    const id = existingIds.has(baseId) ? baseId : agent.id;
    if (id !== agent.id) idMap.set(agent.id, id);
    return {
      ...agent,
      id,
      name: agent.name ? stripRefinedSuffix(agent.name) : agent.name,
      module: normalizeAgentModule(agent),
    };
  });

  const knownLayerNames = new Set([...current.layers, ...proposal.layers].map(normalizeLayer));
  const layerRank = new Map(
    [...current.layers, ...proposal.layers].map((layer, index) => [normalizeLayer(layer), index])
  );
  const nodesById = new Map([
    ...current.agents.map((a) => [a.id, { id: a.id, layer: a.layer }] as const),
    ...agents.map((a) => [a.id, { id: a.id, layer: a.layer ?? null }] as const),
  ]);

  const edges = proposal.edges.map((edge) => ({
    source: idMap.get(edge.source) ?? edge.source,
    target: idMap.get(edge.target) ?? edge.target,
  }));
  const seen = new Set(current.edges.map((e) => `${e.source}->${e.target}`));
  for (const edge of edges) seen.add(`${edge.source}->${edge.target}`);

  const hasIncidentEdge = (id: string) =>
    current.edges.some((edge) => edge.source === id || edge.target === id) ||
    edges.some((edge) => edge.source === id || edge.target === id);

  const canConnect = (source: string, target: string) => {
    if (source === target) return false;
    const src = nodesById.get(source);
    const tgt = nodesById.get(target);
    if (!src || !tgt) return false;
    const srcLayer = normalizeLayer(src.layer);
    const tgtLayer = normalizeLayer(tgt.layer);
    if (!knownLayerNames.has(srcLayer) || !knownLayerNames.has(tgtLayer)) return false;
    const si = layerRank.get(srcLayer);
    const ti = layerRank.get(tgtLayer);
    return si !== undefined && ti !== undefined && (ti === si || ti === si + 1);
  };

  const addEdge = (source: string, target: string) => {
    const key = `${source}->${target}`;
    if (seen.has(key) || !canConnect(source, target)) return false;
    seen.add(key);
    edges.push({ source, target });
    return true;
  };

  const proposedIds = agents.map((agent) => agent.id);
  for (let i = 0; i < proposedIds.length; i += 1) {
    const id = proposedIds[i];
    if (hasIncidentEdge(id)) continue;
    const previous = [...proposedIds.slice(0, i).reverse(), ...current.agents.map((a) => a.id)].find(
      (candidate) => addEdge(candidate, id)
    );
    if (previous) continue;
    [...proposedIds.slice(i + 1), ...current.agents.map((a) => a.id)].find((candidate) =>
      addEdge(id, candidate)
    );
  }

  return {
    ...proposal,
    agents,
    edges,
    remove: proposal.remove
      ? {
          ...proposal.remove,
          edges: proposal.remove.edges?.map((edge) => ({
            source: idMap.get(edge.source) ?? edge.source,
            target: idMap.get(edge.target) ?? edge.target,
          })),
        }
      : proposal.remove,
  };
}

/** Snapshot of what's already on the canvas, handed to the model as context. */
export interface CurrentDesign {
  layers: string[];
  agents: {
    id: string;
    description?: string;
    module?: string | null;
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
          const module = a.module?.trim() ? a.module.trim() : "(no module)";
          const layer = a.layer ?? "(no tier)";
          const desc = a.description?.trim() ? ` — ${a.description.trim()}` : "";
          return `  - ${a.id} [module: ${module}; tier: ${layer}]${desc}`;
        })
        .join("\n")
    : "  (none yet)";
  const edges = current.edges.length
    ? current.edges.map((e) => `  - ${e.source} -> ${e.target}`).join("\n")
    : "  (none yet)";
  return `Current tiers: ${tiers}\nCurrent agents:\n${agents}\nCurrent calls:\n${edges}`;
}
