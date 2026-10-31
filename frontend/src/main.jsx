import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { postEvents } from "./lib/api.js";
import { installAudioUnlock } from "./lib/fx.js";
import { startTelemetry } from "./lib/telemetry.js";
import "./styles/shieldmate.css";

// UI events go to the server's event log (POST /api/events). If EVENT_LOG is off there, the
// first batch answers not_enabled and telemetry stops for this page load.
startTelemetry(postEvents);
installAudioUnlock();

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
