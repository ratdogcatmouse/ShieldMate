import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,                                    // reachable from phones on the hotspot
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },    // the FastAPI backend (./start.sh or uvicorn)
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{js,jsx}"],     // e2e/ is Playwright's (npm run e2e)
    setupFiles: ["./src/test/setup.js"],
  },
});
