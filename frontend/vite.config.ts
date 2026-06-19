import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  base: "./",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api/ws": { target: "http://127.0.0.1:8001", ws: true },
      "/api": { target: "http://127.0.0.1:8001" },
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
      },
    },
  },
});

