import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The UI never calls the API cross-origin: /api/* is proxied by the dev
// server, so the browser sees one origin and no CORS handling is needed.
// API_PROXY_TARGET points at the API service (compose sets http://api:8000;
// the default fits make serve on the same machine).
const apiTarget = process.env.API_PROXY_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 3000,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
