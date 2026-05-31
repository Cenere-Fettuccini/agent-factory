// In-browser SLM designer. Gated behind an explicit load() because the model is
// a one-time ~1.1GB download (cached by the browser afterwards). Everything is
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
  refineDesignerPrompt,
  normalizeProposal,
  type CurrentDesign,
  type DesignProposal,
} from "./proposalSchema";

// Instruction-tuned, strong at constrained JSON for its size. 4-bit, ~1.9GB.
// We stepped up from the 1.5B variant: on multi-stage briefs ("get a topic, then
// research it into a paper — two separate networks") the smaller model
// under-decomposed and emitted just a couple of agents. The 3B has the headroom
// to follow the decomposition rules and worked example in DESIGNER_SYSTEM_PROMPT
// and fill out a real multi-tier pipeline. Trade-off to keep in mind: on a
// machine with only an integrated GPU this can saturate shared VRAM, and because
// the Windows desktop compositor shares that GPU the whole machine can briefly
// stutter or freeze during inference — preflightWebGPU gates the worst cases.
const MODEL_ID = "Qwen2.5-3B-Instruct-q4f16_1-MLC";

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
  propose: (prompt: string, current: CurrentDesign) => Promise<DesignProposal | null>;
}

function webgpuAvailable(): boolean {
  return typeof navigator !== "undefined" && "gpu" in navigator;
}

// Minimal structural typing so we can probe WebGPU without pulling @webgpu/types.
interface MinimalAdapter {
  requestDevice(): Promise<{ destroy: () => void }>;
}
interface MinimalGPU {
  requestAdapter(): Promise<MinimalAdapter | null>;
}
function getGPU(): MinimalGPU | undefined {
  return (navigator as unknown as { gpu?: MinimalGPU }).gpu;
}

// `navigator.gpu` existing isn't enough: a browser can expose WebGPU yet fail to
// create a device (stale driver, or Chrome's dxil.dll shader compiler failing to
// load on Windows). We probe adapter+device up front so that surfaces as plain
// guidance instead of a raw C++ stack trace from deep inside the engine.
// Returns null on success, "no-webgpu" when absent, else a human-readable reason.
async function preflightWebGPU(): Promise<string | null> {
  const gpu = getGPU();
  if (!gpu) return "no-webgpu";
  let adapter: MinimalAdapter | null = null;
  try {
    adapter = await gpu.requestAdapter();
  } catch {
    adapter = null;
  }
  if (!adapter) {
    return "WebGPU is present but no GPU adapter is available. Update your GPU driver, or use desktop Chrome or Edge.";
  }
  try {
    const device = await adapter.requestDevice();
    device.destroy();
    return null;
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    return (
      "WebGPU is present but your browser couldn't create a GPU device — often a " +
      "Chrome/Edge or GPU-driver version issue (e.g. a dxil.dll load failure on " +
      "Windows). Update your browser and GPU driver, then reload.\n\n" +
      detail
    );
  }
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
    setError(null);
    const problem = await preflightWebGPU();
    if (problem === "no-webgpu") {
      setStatus("unsupported");
      return;
    }
    if (problem) {
      setError(problem);
      setStatus("error");
      return;
    }
    setStatus("loading");
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
        const refinedPrompt = refineDesignerPrompt(prompt);
        const reply = await engine.chat.completions.create({
          temperature: 0.4,
          // Headroom so a larger delta (agents + edges + a remove block) doesn't
          // get truncated mid-JSON, which would fail the parse below.
          max_tokens: 2048,
          response_format: {
            type: "json_object",
            schema: JSON.stringify(PROPOSAL_JSON_SCHEMA),
          },
          messages: [
            { role: "system", content: DESIGNER_SYSTEM_PROMPT },
            {
              role: "user",
              content: `${describeCurrent(current)}\n\nTask: ${refinedPrompt}`,
            },
          ],
        });
        const text = reply.choices[0]?.message?.content ?? "";
        // Leave a breadcrumb for diagnosing weak/empty generations from devtools.
        console.debug("[designer] raw model reply:", text);
        const parsed = JSON.parse(text) as DesignProposal;
        setStatus("ready");
        return normalizeProposal(parsed, current);
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
