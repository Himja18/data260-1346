import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the FastAPI backend on PORT_BASE 8446.
// Same-origin requests mean the HTTP-only session cookie just works (no CORS).
// 127.0.0.1 (not "localhost") avoids Node resolving to IPv6 ::1, which uvicorn isn't bound to.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8446" },
    },
  },
});
