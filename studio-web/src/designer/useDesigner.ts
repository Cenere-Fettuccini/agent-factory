// In-browser SLM designer. Gated behind an explicit load() because the model is
// a one-time ~1GB download (cached by the browser afterwards). Everything is
// client-side: no server hop, no API key. Behind a single `propose()` seam so a
// server fallback could slot in for WebGPU-less browsers without touching the UI.

import { useCallback, useRef, useState } from "react";
// Types only — erased at build. The ~6MB engine runtime is pulled via dynamic
// import inside load(), so users who never open the panel never download it.
import type { InitProgressReport, MLCEngineInterface } from "@mlc-ai/web-llm";
import {
  DESIGNER_SYSTEM_PROMPT,
  PROPOSAL_JSON_SCHEMA,
  describeCurrent,
  type DesignProposal,
} from "./proposalSchema";

// Small, instruction-tuned, strong at constrained JSON for its size. 4-bit,
// ~1.1GB. Bump to a 3B model here if proposal quality falls short.
const MODEL_ID = "Qwen2.5-1.5B-Instruct-q4f16_1-MLC";

export type DesignerStatus =
  | "idle" // not loaded yet
  | "unsupported" // no WebGPU in this browser
  | "loading" // downloading / compiling the model
  | "ready" // engine warm, waiting for a prompt
  | "thinking" // generating a proposal
  | "error";

export interface DesignerState {
  status: DesignerStatus;
  /** 0..1 download/compile progress while status === "loading". */
  progress: number;
  progressText: string;
  error: string | null;
  load: () => Promise<void>;
  propose: (
    prompt: string,
    current: { layers: string[]; agentIds: string[] }
  ) => Promise<DesignProposal | null>;
}

function webgpuAvailable(): boolean {
  return typeof navigator !== "undefined" && "gpu" in navigator;
}

export function useDesigner(): DesignerState {
  const engineRef = useRef<MLCEngineInterface | null>(null);
  const [status, setStatus] = useState<DesignerStatus>(
    webgpuAvailable() ? "idle" : "unsupported"
  );
  const [progress, setProgress] = useState(0);
  const [progressText, setProgressText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (engineRef.current || status === "loading") return;
    if (!webgpuAvailable()) {
      setStatus("unsupported");
      return;
    }
    setStatus("loading");
    setError(null);
    try {
      const { CreateWebWorkerMLCEngine } = await import("@mlc-ai/web-llm");
      const worker = new Worker(new URL("./worker.ts", import.meta.url), {
        type: "module",
      });
      const engine = await CreateWebWorkerMLCEngine(worker, MODEL_ID, {
        initProgressCallback: (r: InitProgressReport) => {
          setProgress(r.progress);
          setProgressText(r.text);
        },
      });
      engineRef.current = engine;
      setProgress(1);
      setStatus("ready");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("error");
    }
  }, [status]);

  const propose = useCallback<DesignerState["propose"]>(
    async (prompt, current) => {
      const engine = engineRef.current;
      if (!engine) {
        setError("Model not loaded yet.");
        return null;
      }
      setStatus("thinking");
      setError(null);
      try {
        const reply = await engine.chat.completions.create({
          temperature: 0.4,
          max_tokens: 1024,
          response_format: {
            type: "json_object",
            schema: JSON.stringify(PROPOSAL_JSON_SCHEMA),
          },
          messages: [
            { role: "system", content: DESIGNER_SYSTEM_PROMPT },
            {
              role: "user",
              content: `${describeCurrent(current.layers, current.agentIds)}\n\nTask: ${prompt}`,
            },
          ],
        });
        const text = reply.choices[0]?.message?.content ?? "";
        const parsed = JSON.parse(text) as DesignProposal;
        setStatus("ready");
        return parsed;
      } catch (e) {
        // Grammar makes malformed JSON unlikely, but a parse/transport slip is
        // recoverable — surface it and stay ready for another try.
        setError(e instanceof Error ? e.message : String(e));
        setStatus("ready");
        return null;
      }
    },
    []
  );

  return { status, progress, progressText, error, load, propose };
}
