import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Web UI ships as a static bundle served from the Cloud Backend host at the
// site root (see synapse_cloud/app.py — StaticFiles mount of settings.web_ui_dist).
// Same origin as the REST API, so no CORS and an absolute base of '/'.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: { outDir: "dist", sourcemap: true },
  server: { port: 5173, host: true },
});
