import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { API_MODE, postEvents } from "./api.js";
import { startTelemetry } from "./telemetry.js";
import "./styles/tokens.css";

// Mock mode has no server to tell, so it sends nothing.
startTelemetry(API_MODE === "http" ? postEvents : null);

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
