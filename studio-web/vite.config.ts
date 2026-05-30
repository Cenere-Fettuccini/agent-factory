import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API base URL is read at runtime from VITE_API_BASE (see src/api/client.ts),
// defaulting to the local AgentComposer dev server.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
