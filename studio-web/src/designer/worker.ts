// Web Worker host for the in-browser SLM. The MLC engine runs entirely here so
// model download and token generation never block React render or the canvas.
// `useDesigner` drives it via the main-thread `CreateWebWorkerMLCEngine` proxy.

import { WebWorkerMLCEngineHandler } from "@mlc-ai/web-llm";

const handler = new WebWorkerMLCEngineHandler();

self.onmessage = (msg: MessageEvent) => {
  handler.onmessage(msg);
};
