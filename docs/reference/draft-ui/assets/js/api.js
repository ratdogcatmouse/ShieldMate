/* ShieldMate API client: the ONLY file that knows where data comes from.
   Each function maps to one route in the Software Design's API contract.
   Mock mode answers from mock-server.js; http mode calls FastAPI. */
(function () {
  "use strict";
  const C = window.SM_CONFIG;

  async function call(method, path, body) {
    if (C.mode === "mock") {
      await new Promise(r => setTimeout(r, 40));
      try { return window.SM_MOCK.handle(method, "/api" + path, body); }
      catch (e) { throw normalise(e.status || 500, e.body || { error: "mock_error", message: e.message }); }
    }
    const res = await fetch(C.apiBase + "/api" + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* empty body */ }
    if (!res.ok) throw normalise(res.status, data);
    return data;
  }
  function normalise(status, body) {
    const err = new Error((body && body.message) || "Something went wrong. Try again.");
    err.status = status; err.code = body && body.error;
    return err;
  }

  window.SM_API = {
    mode: () => C.mode,
    // setup
    clinic: () => call("GET", "/clinic"),
    devices: () => call("GET", "/devices"),
    setStandingRule: (on) => call("PUT", "/clinic/standing-rule", { on }),
    // alerts
    alerts: (role) => call("GET", "/alerts?role=" + encodeURIComponent(role || "")),
    tickStep: (alertId, n, staffId, done, list) => call("PUT", "/alerts/" + alertId + "/steps/" + n, { staff_id: staffId, done, list }),
    done: (alertId, staffId) => call("POST", "/alerts/" + alertId + "/done", { staff_id: staffId }),
    mine: (alertId, staffId) => call("POST", "/alerts/" + alertId + "/mine", { staff_id: staffId }),
    reopen: (alertId) => call("POST", "/alerts/" + alertId + "/reopen", {}),
    notifications: () => call("GET", "/notifications?role=owner"),
    activity: () => call("GET", "/activity"),
    // live actions
    actions: () => call("GET", "/actions"),
    approve: (id) => call("POST", "/actions/" + id + "/approve", { staff_id: "rao" }),
    decline: (id) => call("POST", "/actions/" + id + "/decline", { staff_id: "rao" }),
    undo: (id) => call("POST", "/actions/" + id + "/undo", { staff_id: "rao" }),
    // drills
    currentDrill: () => call("GET", "/drills/current"),
    createDrill: (scenarioId) => call("POST", "/drills", { scenario_id: scenarioId, host_staff_id: "rao" }),
    joinDrill: (code, staffId) => call("POST", "/drills/" + code + "/join", { staff_id: staffId }),
    drill: (code, playerId) => call("GET", "/drills/" + code + "?player_id=" + encodeURIComponent(playerId || "")),
    answer: (code, playerId, stepId, optionId) => call("POST", "/drills/" + code + "/answers", { player_id: playerId, step_id: stepId, option_id: optionId }),
    advance: (code) => call("POST", "/drills/" + code + "/advance", { staff_id: "rao" }),
    endDrill: (code) => call("POST", "/drills/" + code + "/end", { staff_id: "rao" }),
    // restore + readiness
    runRestore: () => call("POST", "/restore/run", {}),
    restoreLatest: () => call("GET", "/restore/latest"),
    readiness: () => call("GET", "/owner/readiness"),
    // demo controls (Backstage)
    replay: (type) => call("POST", "/demo/replay/" + type, {}),
    reset: () => call("POST", "/demo/reset", {}),
    skip: (minutes) => call("POST", "/demo/skip", { minutes }),
    demoStatus: () => call("GET", "/demo/status")
  };
})();
