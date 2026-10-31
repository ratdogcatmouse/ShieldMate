/* Backstage: demo controls. Not shown to judges. */
(function () {
  "use strict";
  const U = window.SM_UI, API = window.SM_API;
  const esc = U.esc;
  const main = document.getElementById("main");
  let confirmReset = false;
  const mock = window.SM_CONFIG.mode === "mock";

  const NEXT = {
    password_guessing: ["Password guessing", n => n === 0 ? "Next: click 1 · card on Meena's phone, approval request for Dr. Rao" : n === 1 ? "Next: click 2 · count goes from 8+ to 12+ (same card)" : "Next: more attempts on the same card"],
    ransomware: ["Ransomware file changes", n => n === 0 ? "Next: click 1 · ransomware card for staff and owner" : "Already replayed · Reset to run again"]
  };

  async function render() {
    let st = { replay: {}, log: [], offset_min: 0 };
    try { st = await API.demoStatus(); } catch (e) { /* real backend may not have this route */ }
    let html = '<header class="stack-sm" style="gap:4px"><span class="tiny bold" style="letter-spacing:0.08em;color:#9DB4D3">BACKSTAGE · NOT SHOWN TO JUDGES</span><h1 style="font-size:24px">Demo controls</h1>' +
      '<span class="small" style="color:#B7C6DA">' + (mock ? "Demo data in this browser: open the other screens as tabs in this same browser." : "Talking to the ShieldMate server.") + "</span></header>";
    Object.keys(NEXT).forEach(type => {
      const n = st.replay[type] || 0;
      html += '<div class="bs-card"><div class="stack-sm" style="gap:2px"><span class="bold">' + esc(NEXT[type][0]) + '</span><span class="sub">' + esc(NEXT[type][1](n)) + "</span></div>" +
        '<button type="button" class="btn btn-bs" data-act="replay" data-type="' + type + '"' + (type === "ransomware" && n > 0 ? " disabled" : "") + ">Replay next</button></div>";
    });
    if (mock) {
      html += '<div class="bs-card"><div class="stack-sm" style="gap:2px"><span class="bold">Skip ahead 5 minutes</span><span class="sub">Shows the standing rule acting when nobody answers' + (st.offset_min ? " · clock is " + st.offset_min + " min ahead" : "") + "</span></div>" +
        '<button type="button" class="btn btn-bs" data-act="skip">Skip 5 min</button></div>';
    }
    html += '<section class="bs-card" style="display:block"><span class="tiny bold" style="letter-spacing:0.06em;color:#9DB4D3">LAST INJECTIONS</span><div class="bs-log">' +
      (st.log.length ? st.log.map(l => esc(U.time(l.at)) + "  " + esc(l.text)).join("<br>") : "Nothing yet") + "</div></section>";
    html += '<div class="row-between" style="border-top:1px solid #2E4566;padding-top:16px"><span class="small" style="color:#B7C6DA">Clears alerts, drills and backup tests. Run before every rehearsal.</span>' +
      '<button type="button" class="btn btn-bs-danger" data-act="reset">' + (confirmReset ? "Tap again to reset" : "Reset demo") + "</button></div>" +
      '<div class="row"><a class="btn btn-soft" href="index.html">Start screen</a><a class="btn btn-soft" href="owner.html">Owner</a><a class="btn btn-soft" href="staff.html?staff=meena">Meena</a><a class="btn btn-soft" href="drill.html?staff=ravi">Ravi\'s drill</a></div>';
    U.paint(main, html);
  }

  const refresh = U.live(render);
  U.onAct({
    replay: async (el) => { const r = await API.replay(el.dataset.type); U.toast("Injected: " + r.summary); await refresh(); },
    skip: async () => { await API.skip(5); U.toast("Clock moved 5 minutes ahead"); await refresh(); },
    reset: async () => {
      if (!confirmReset) { confirmReset = true; await refresh(); setTimeout(() => { confirmReset = false; refresh(); }, 4000); return; }
      confirmReset = false;
      await API.reset();
      try { Object.keys(sessionStorage).filter(k => k.startsWith("sm-")).forEach(k => sessionStorage.removeItem(k)); } catch (e) { /* ignore */ }
      U.toast("Demo reset"); await refresh();
    }
  });
})();
