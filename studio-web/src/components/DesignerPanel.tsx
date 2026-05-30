// Floating "design with AI" panel. Runs a small language model entirely in the
// browser (WebGPU) to turn a sentence into a starter agent network, then drops
// the proposal onto the canvas. The backend Resolver/Validate then take over —
// the model drafts structure, the human refines, the contract stays the judge.

import { useState } from "react";
import { useDesigner } from "../designer/useDesigner";
import { useGraph } from "../state/graphStore";

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

  const { status, progress, progressText, error } = designer;

  async function onDesign() {
    const text = prompt.trim();
    if (!text) return;
    const s = useGraph.getState();
    const proposal = await designer.propose(text, {
      layers: s.layers,
      agentIds: s.nodes.map((n) => n.id),
    });
    if (proposal) loadProposal(proposal);
  }

  if (!open) return null;

  return (
    <div className="designer-panel">
      <div className="designer-head">
        <span>✦ Design with AI</span>
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
            no key. First use downloads it once (~1&nbsp;GB, then cached).
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
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={EXAMPLE}
            rows={3}
            disabled={status === "thinking"}
          />
          <button
            className="primary"
            onClick={onDesign}
            disabled={status === "thinking" || !prompt.trim()}
          >
            {status === "thinking" ? "Designing…" : "Design network"}
          </button>
          <p className="designer-sub">
            Drafts tiers, agents, and call edges onto the canvas. Resolve and
            validation fill and check the rest.
          </p>
        </>
      )}

      {error && <p className="msg err">{error}</p>}
    </div>
  );
}
