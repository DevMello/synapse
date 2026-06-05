import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Web UI ships as a static bundle served from the Cloud Backend host at the
// site root (see synapse_cloud/app.py — StaticFiles mount of settings.web_ui_dist).
// Same origin as the REST API, so no CORS and an absolute base of '/'.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "dist",
    sourcemap: true,
    // Heavy, route-specific libraries (Recharts on the Analytics tab, CodeMirror on
    // the Editor tab) are lazy-loaded via React.lazy, so they fall out of the initial
    // chunk on their own. manualChunks groups the always-present vendors into
    // separately-cacheable files so an app-code change doesn't bust the vendor cache.
    // The `editor` chunk (CodeMirror) is intentionally large but lazy — only the
    // Editor tab pulls it — so it never weighs on first paint. Raise the warning
    // threshold above it so the build stays clean.
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (/recharts|d3-|victory-vendor|internmap/.test(id)) return "charts";
          if (/codemirror|@uiw|@lezer/.test(id)) return "editor";
          if (/@supabase|@tanstack|zustand/.test(id)) return "data";
          if (/react-router|@remix-run/.test(id)) return "router";
          if (/[\\/]react(-dom)?[\\/]|scheduler/.test(id)) return "react";
          return "vendor";
        },
      },
    },
  },
  server: { port: 5173, host: true },
});
