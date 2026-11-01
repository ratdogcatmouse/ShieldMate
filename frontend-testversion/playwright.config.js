// End-to-end tests against a running backend that serves the built app:
//   npm run build && (cd ../backend && ACTIONS=1 .venv/bin/uvicorn main:app --port 8000)
//   npm run e2e                          # or SM_BASE=http://<laptop-ip>:8000 npm run e2e
// The tests press Backstage Reset, so never point them at a live demo.
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,                 // one shared server: the stories run one after another
  timeout: 60_000,
  use: {
    baseURL: process.env.SM_BASE || "http://localhost:8000",
    trace: "retain-on-failure",
  },
});
