import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwind from "@tailwindcss/vite";
export default defineConfig({
  plugins: [react(), tailwind()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          charts: ["echarts"],

          query: ["@tanstack/react-query", "@tanstack/react-virtual"],
        },
      },
    },
    chunkSizeWarningLimit: 800,
  },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
