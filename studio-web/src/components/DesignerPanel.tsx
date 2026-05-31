// Floating "design with AI" panel. Runs a small language model entirely in the
// browser (WebGPU) to turn a sentence into a starter agent network, then drops
// the proposal onto the canvas. The backend Resolver/Validate then take over —
// the model drafts structure, the human refines, the contract stays the judge.

import { useEffect, useRef, useState } from "react";
import { useDesigner } from "../designer/useDesigner";
import { useGraph } from "../state/graphStore";

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

  async function onDesign() {
    const text = prompt.trim();
    if (!text) return;
    setNotice(null);
    const s = useGraph.getState();
    const proposal = await designer.propose(text, {
      layers: s.layers,
      agents: s.nodes.map((n) => ({
        id: n.id,
        description: n.description,
        module: n.module,
        layer: n.layer,
        trigger: n.trigger,
      })),
      edges: s.edges,
    });
    // proposal === null means a parse/transport error (already shown via `error`).
    // A non-null proposal that changes nothing means the model returned an empty
    // design — say so rather than leaving the canvas looking broken.
    if (proposal && !loadProposal(proposal)) {
      setNotice(
        "The model returned an empty design. Try rephrasing your prompt or adding more detail."
      );
    }
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
      {notice && <p className="msg">{notice}</p>}
    </div>
  );
}
