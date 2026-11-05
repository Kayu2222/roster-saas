import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs separately on :8000; Vite forwards /api to it,
// so the browser sees one origin (same as production, where FastAPI serves this app).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://localhost:8000", "/health": "http://localhost:8000" },
  },
  build: { outDir: "dist", sourcemap: false },
});
