/* Where ShieldMate's data comes from.
   mode "mock": everything runs in the browser with demo data (no backend needed).
   mode "http": every call goes to the FastAPI backend at apiBase + /api/...
   Override for one visit with ?api=http or ?api=mock in the address bar. */
window.SM_CONFIG = {
  mode: "mock",
  apiBase: "",          // "" = same server that serves these pages
  pollMs: 2000          // how often screens refresh (matches the design: 2 s)
};
(function () {
  try {
    const p = new URLSearchParams(location.search).get("api");
    if (p === "http" || p === "mock") sessionStorage.setItem("sm-api-mode", p);
    const saved = sessionStorage.getItem("sm-api-mode");
    if (saved) window.SM_CONFIG.mode = saved;
  } catch (e) { /* storage blocked: keep default */ }
})();
