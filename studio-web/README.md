# Agent Studio UI (Era III)

A ComfyUI-style web canvas for authoring **layered agent networks** over the
AgentComposer API. The framework becomes usable without writing Python.

The canvas is not six internal knobs per agent -- it is a network of agent
**roles** arranged in horizontal **tiers** (e.g. *Refinement -> Orchestrator ->
Tools*). A tier may only call the tier directly below it, so the path from a
trigger to query resolution is explicit. You fill in almost nothing: pick a
model per agent, and define tools on the tool tier. IO schemas, inter-agent
wiring, and caller permissions auto-resolve.

## Principles (a thin shell over the API)

- **Nothing is hardcoded.** Every dropdown binds to live `/catalogs`; every form
  to `/node-types`. Point it at a newer framework and new fields just appear.
- **Validation is the backend's.** Answers come from `/graph/validate`,
  `/agents/preview`, `/export/dry-run` and render on the specific node/edge.
- **The UI never writes files.** `/export` owns the filesystem.

## Run

```bash
# 1. Backend (from the repo root)
uv sync --extra api
uv run uvicorn composer.app:app --reload    # http://localhost:8000

# 2. Frontend
cd studio-web
npm install
npm run dev                                 # http://localhost:5173
```

The API base URL defaults to `http://localhost:8000`; override with
`VITE_API_BASE`. The backend allows the Vite dev origin via CORS (configure
other origins with `AGENTCOMPOSER_CORS_ORIGINS`).

## Walkthrough

1. Drag **+ Agent** onto a tier lane; pick a model (the only required input).
2. On a tool-tier agent, **define a tool** (name + arg types) -- it's validated
   by `/tools/validate`, then granted.
3. Draw calls from an agent to the tier directly below; non-adjacent
   connections are refused.
4. With **auto-resolve** on, IO and caller allowlists fill in by themselves.
5. Mark a top-tier agent as a **trigger** (user query / auto action); selecting
   it highlights the downward resolution path.
6. **Dry-run** (green) -> **Export** to an absolute path -> an importable folder.

## Stack

Vite / React / TypeScript / React Flow (`@xyflow/react`) / TanStack Query
(catalog boot + debounced resolve/validate) / Zustand (graph state).
