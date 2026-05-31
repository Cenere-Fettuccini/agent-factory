// Floating "design with AI" panel. Runs a small language model entirely in the
// browser (WebGPU) to turn a sentence into a starter agent network, then drops
// the proposal onto the canvas. The backend Resolver/Validate then take over —
// the model drafts structure, the human refines, the contract stays the judge.

import { useEffect, useRef, useState } from "react";
import { useDesigner } from "../designer/useDesigner";
import { DESIGN_STAGES, type CurrentDesign, type StageId } from "../designer/proposalSchema";
import { useGraph } from "../state/graphStore";

type StagePhase = "pending" | "running" | "done" | "failed";
interface StageRun {
  id: StageId;
  label: string;
  phase: StagePhase;
  detail: string;
}

const STAGE_LABELS: Record<StageId, string> = {
  tiers: "Tiers",
  agents: "Agents",
  edges: "Connections",
};

const PHASE_ICON: Record<StagePhase, string> = {
  pending: "○",
  running: "…",
  done: "✓",
  failed: "✕",
};

/** One-line "what changed" for a finished stage, from before/after counts. */
function summarize(stage: StageId, before: CurrentDesign, after: CurrentDesign): string {
  const plural = (n: number, w: string) => `+${n} ${w}${n === 1 ? "" : "s"}`;
  if (stage === "tiers") {
    const n = after.layers.length - before.layers.length;
    return n > 0 ? plural(n, "tier") : "reused existing tiers";
  }
  if (stage === "agents") {
    const n = after.agents.length - before.agents.length;
    return n > 0 ? plural(n, "agent") : "updated existing agents";
  }
  const n = after.edges.length - before.edges.length;
  return n > 0 ? plural(n, "connection") : "no new connections";
}

/** Read the canvas into the shape the model is shown as context. */
function snapshotCurrent(): CurrentDesign {
  const s = useGraph.getState();
  return {
    layers: s.layers,
    agents: s.nodes.map((n) => ({
      id: n.id,
      description: n.description,
      module: n.module,
      layer: n.layer,
      trigger: n.trigger,
    })),
    edges: s.edges,
  };
}

// Platform-aware label so macOS sees ⌘ and everyone else sees Ctrl.
const SHORTCUT_LABEL =
  typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform)
    ? "⌘K"
    : "Ctrl+K";

const EXAMPLE = "Summarize incoming support tickets and route urgent ones to a human.";

export function DesignerPanel() {
  const designer = useDesigner();
  const loadProposal = useGraph((s) => s.loadProposal);
  // Open-state lives in the store so the canvas right-click menu can raise it.
  // The component stays mounted while closed (returns null) so a loaded model
  // survives open/close.
  const open = useGraph((s) => s.designerOpen);
  const setOpen = useGraph((s) => s.setDesignerOpen);
  const [prompt, setPrompt] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [stages, setStages] = useState<StageRun[] | null>(null);
  const [running, setRunning] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // Latest designer kept in a ref so the always-on key handler can read its
  // current status / call load() without re-subscribing the listener each render.
  const designerRef = useRef(designer);
  designerRef.current = designer;

  // Global shortcut: Ctrl/Cmd+K toggles the design panel from anywhere. The
  // component stays mounted while closed (returns null below), so this listener
  // is always live. We read designerOpen straight from the store inside the
  // handler — not the `open` prop — so the effect can depend only on the stable
  // setOpen and never goes stale.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "k") {
        e.preventDefault();
        const next = !useGraph.getState().designerOpen;
        setOpen(next);
        if (next) {
          // Reaching for the shortcut means the user already knows about the
          // model, so skip the "Enable AI design" gate and kick off the one-time
          // download right away. load() no-ops if it's already loaded or loading.
          if (designerRef.current.status === "idle") void designerRef.current.load();
          // Focus the prompt box once it renders (it only exists once ready, so
          // the optional chain is a no-op while it's still downloading).
          requestAnimationFrame(() => textareaRef.current?.focus());
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);

  const { status, progress, progressText, error } = designer;

  // Walk the stages from `startIndex`, applying each delta to the canvas as it
  // lands so the network assembles live. A stage that errors or returns nothing
  // halts the run and leaves a Retry button on that row — earlier stages stay.
  async function runStages(startIndex: number) {
    const text = prompt.trim();
    if (!text || running) return;
    setNotice(null);
    setRunning(true);

    setStages((prev) => {
      const base =
        prev ??
        DESIGN_STAGES.map((id) => ({
          id,
          label: STAGE_LABELS[id],
          phase: "pending" as StagePhase,
          detail: "",
        }));
      // Reset this stage and everything after it; keep completed earlier stages.
      return base.map((s, i) =>
        i >= startIndex ? { ...s, phase: "pending" as StagePhase, detail: "" } : s
      );
    });
    const patch = (i: number, change: Partial<StageRun>) =>
      setStages((prev) => prev?.map((s, j) => (j === i ? { ...s, ...change } : s)) ?? prev);

    for (let i = startIndex; i < DESIGN_STAGES.length; i += 1) {
      const stage = DESIGN_STAGES[i];
      patch(i, { phase: "running", detail: "" });

      const before = snapshotCurrent();
      const partial = await designer.proposeStage(stage, text, before);
      if (!partial) {
        patch(i, { phase: "failed", detail: "model error — see below" });
        setRunning(false);
        return;
      }

      const counts = {
        tiers: partial.layers?.length ?? 0,
        agents: partial.agents?.length ?? 0,
        edges: partial.edges?.length ?? 0,
      };
      loadProposal({
        layers: partial.layers ?? [],
        agents: partial.agents ?? [],
        edges: partial.edges ?? [],
      });

      // Tiers and agents must produce something; an empty edges stage is allowed
      // (a flat set of agents is still a valid, if unwired, starting point).
      if ((stage === "tiers" || stage === "agents") && counts[stage] === 0) {
        patch(i, { phase: "failed", detail: "returned nothing — retry or rephrase" });
        setRunning(false);
        return;
      }

      const after = snapshotCurrent();
      patch(i, { phase: "done", detail: summarize(stage, before, after) });
    }
    setRunning(false);
  }

  if (!open) return null;

  return (
    <div className="designer-panel">
      <div className="designer-head">
        <span>✦ Design with AI</span>
        <kbd
          title="Toggle this panel"
          style={{
            marginLeft: "auto",
            marginRight: 8,
            padding: "1px 6px",
            fontSize: 11,
            fontFamily: "inherit",
            lineHeight: 1.6,
            opacity: 0.7,
            border: "1px solid currentColor",
            borderRadius: 4,
          }}
        >
          {SHORTCUT_LABEL}
        </kbd>
        <button className="ghost" onClick={() => setOpen(false)} aria-label="Close">
          ✕
        </button>
      </div>

      {status === "unsupported" ? (
        <p className="msg err">
          This browser has no WebGPU, so the in-browser model can&apos;t run. Try
          Chrome or Edge (desktop).
        </p>
      ) : status === "idle" ? (
        <>
          <p className="designer-hint">
            Runs a small model <strong>fully in your browser</strong> — no server,
            no key. First use downloads it once (~1.9&nbsp;GB, then cached).
          </p>
          <button className="primary" onClick={designer.load}>
            Enable AI design (downloads model once)
          </button>
        </>
      ) : status === "loading" ? (
        <>
          <p className="designer-hint">Loading model…</p>
          <div className="designer-bar">
            <div className="designer-bar-fill" style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
          <p className="designer-sub">{progressText}</p>
        </>
      ) : status === "error" ? (
        <>
          <p className="designer-hint">Couldn&apos;t start the in-browser model.</p>
          <button className="primary" onClick={designer.load}>
            Try again
          </button>
        </>
      ) : (
        <>
          <textarea
            ref={textareaRef}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={EXAMPLE}
            rows={3}
            disabled={running}
          />
          <button className="primary" onClick={() => runStages(0)} disabled={running || !prompt.trim()}>
            {running ? "Designing…" : stages ? "Design again" : "Design network"}
          </button>

          {stages && (
            <ol className="designer-stages">
              {stages.map((s, i) => (
                <li key={s.id} className={`stage ${s.phase}`}>
                  <span className="stage-icon">{PHASE_ICON[s.phase]}</span>
                  <span className="stage-label">{s.label}</span>
                  {s.detail && <span className="stage-detail">{s.detail}</span>}
                  {s.phase === "failed" && !running && (
                    <button className="ghost stage-retry" onClick={() => runStages(i)}>
                      Retry
                    </button>
                  )}
                </li>
              ))}
            </ol>
          )}

          <p className="designer-sub">
            Builds tiers, then agents, then call edges — each appears on the canvas
            as it&apos;s generated. Resolve and validation fill and check the rest.
          </p>
        </>
      )}

      {error && <p className="msg err">{error}</p>}
      {notice && <p className="msg">{notice}</p>}
    </div>
  );
}
