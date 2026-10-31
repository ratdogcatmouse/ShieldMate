/* Shared UI helpers: escaping, time, icons, polling, navigation, toasts. */
(function () {
  "use strict";
  const C = window.SM_CONFIG;

  // Every value from data goes through esc() before it touches innerHTML.
  // Log text (like the poisoned username) is shown exactly, never run.
  function esc(v) {
    return String(v === null || v === undefined ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function nowMs() { return C.mode === "mock" && window.SM_MOCK ? window.SM_MOCK.now() : Date.now(); }
  function time(ms) {
    if (!ms) return "";
    return new Date(ms).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }).replace(/\s?(am|pm)$/i, m => " " + m.trim().toUpperCase());
  }
  function ago(ms) {
    const m = Math.max(0, Math.round((nowMs() - ms) / 60000));
    if (m < 1) return "just now";
    if (m < 60) return m + " min ago";
    const h = Math.floor(m / 60);
    return h + " h " + (m % 60) + " min ago";
  }
  function left(ms) {
    const m = Math.max(0, Math.round((ms - nowMs()) / 60000));
    return Math.floor(m / 60) + " h " + (m % 60) + " min left";
  }
  function mmss(sec) { sec = Math.max(0, sec | 0); return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0"); }
  function param(name) { return new URLSearchParams(location.search).get(name); }
  function session(key, value) {
    try {
      if (value === undefined) return sessionStorage.getItem(key);
      if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, value);
    } catch (e) { session.mem = session.mem || {}; if (value === undefined) return session.mem[key] || null; session.mem[key] = value; }
    return null;
  }

  const ICONS = {
    shield: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/></svg>',
    shieldPlain: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/></svg>',
    check: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>',
    cross: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    phone: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"/></svg>',
    clock: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    info: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></svg>',
    chevron: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>',
    back: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>',
    calendar: '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></svg>',
    home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/></svg>',
    target: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/></svg>',
    history: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    menu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>',
    bars: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
    team: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4-6"/></svg>',
    shieldNav: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/></svg>'
  };

  function toast(msg) {
    const t = document.createElement("div");
    t.className = "toast"; t.setAttribute("role", "status"); t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3200);
  }

  // Re-render every pollMs, when another tab changes the mock data, and when
  // the page becomes visible. Keeps the last good screen if a request fails.
  function live(render) {
    let busy = false;
    async function run() {
      if (busy || document.hidden) return;
      busy = true;
      try { await render(); } catch (e) { console.warn(e); } finally { busy = false; }
    }
    run();
    setInterval(run, C.pollMs);
    window.addEventListener("storage", run);
    document.addEventListener("visibilitychange", run);
    return run;
  }
  // Replace an element's HTML only when it changed, so focus and open
  // disclosures survive the 2-second refresh.
  function paint(el, html) {
    if (el.__html === html) return false;
    el.__html = html; el.innerHTML = html;
    tick(); // fill countdowns straight away instead of after a second
    return true;
  }
  // One click handler per page: <button data-act="name" data-x="...">.
  function onAct(handlers) {
    document.addEventListener("click", async (e) => {
      const el = e.target.closest("[data-act]");
      if (!el || !handlers[el.dataset.act]) return;
      e.preventDefault();
      if (el.disabled) return;
      el.disabled = true;
      try { await handlers[el.dataset.act](el); }
      catch (err) { toast(err.message || "Something went wrong."); }
      finally { el.disabled = false; }
    });
  }

  function staffTabs(active, staffId) {
    const q = "?staff=" + encodeURIComponent(staffId || "");
    const tab = (key, href, icon, label) => '<a href="' + href + '"' + (active === key ? ' aria-current="page"' : "") + ">" + ICONS[icon] + label + "</a>";
    return '<nav class="tabbar" aria-label="Main">' +
      tab("today", "staff.html" + q, "home", "Today") +
      tab("drills", "drill.html" + q, "target", "Drills") +
      tab("history", "staff.html" + q + "&view=history", "history", "History") +
      tab("more", "index.html", "menu", "Switch") + "</nav>";
  }
  function ownerNav(active, opts) {
    opts = opts || {};
    const items = [
      ["now", "owner.html", "Right now"],
      ["readiness", "owner-readiness.html", "Readiness"],
      ["drills", "owner-drill.html", "Drills"],
      ["notify", "owner-notify.html", "Phone alert preview"],
      ["mission", "mission.html", "Mission control (projector)"]
    ];
    const side = '<div class="brand"><span style="color:var(--blue);display:flex">' + ICONS.shield + '</span><span class="stack-sm" style="gap:0"><span class="brand-name">ShieldMate</span><span class="tiny muted">Sunrise Family Clinic</span></span></div>' +
      items.map(i => '<a class="nav" href="' + i[1] + '"' + (active === i[0] ? ' aria-current="page"' : "") + ">" + esc(i[2]) + (i[0] === "now" && opts.urgent ? '<span class="dot" aria-label="Needs you"></span>' : "") + "</a>").join("") +
      '<div class="foot"><span>Dr. Rao · owner</span><a href="index.html">Switch person</a><a href="backstage.html">Backstage</a></div>';
    const tab = (key, href, icon, label) => '<a href="' + href + '"' + (active === key ? ' aria-current="page"' : "") + ">" + ICONS[icon] + label + "</a>";
    const tabs = tab("now", "owner.html", "shieldNav", "Right now") + tab("readiness", "owner-readiness.html", "bars", "Readiness") +
      tab("drills", "owner-drill.html", "target", "Drills") + tab("more", "index.html", "menu", "Switch");
    return { side, tabs };
  }
  function mountOwnerNav(active, opts) {
    const n = ownerNav(active, opts);
    const s = document.querySelector("[data-owner-side]"); if (s) paint(s, n.side);
    const t = document.querySelector("[data-owner-tabs]"); if (t) paint(t, n.tabs);
  }
  function modeBanner() {
    if (C.mode !== "mock") return "";
    return '<div class="mode-banner">Demo data in this browser. Open other people in new tabs to see them update.</div>';
  }
  function statusPill(tone, label) { return '<span class="pill pill-sm pill-' + esc(tone) + '">' + esc(label) + "</span>"; }

  // ---------- Alert effects: buzz + chime ----------
  // Browsers only allow sound after the person has tapped the page once, so the
  // first tap anywhere unlocks audio.
  let audioCtx = null;
  function unlockAudio() {
    if (audioCtx) return;
    try { const AC = window.AudioContext || window.webkitAudioContext; if (AC) audioCtx = new AC(); } catch (e) { audioCtx = null; }
  }
  document.addEventListener("pointerdown", unlockAudio, { once: true });
  function soundReady() { return !!audioCtx; }
  function chime() {
    if (!audioCtx) return;
    try {
      const t = audioCtx.currentTime;
      [[880, 0], [1320, 0.16]].forEach(([f, d]) => {
        const o = audioCtx.createOscillator(), g = audioCtx.createGain();
        o.type = "sine"; o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, t + d); g.gain.exponentialRampToValueAtTime(0.25, t + d + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + d + 0.45);
        o.connect(g); g.connect(audioCtx.destination); o.start(t + d); o.stop(t + d + 0.5);
      });
    } catch (e) { /* ignore */ }
  }
  function alertFx() {
    if (C.sound === false) return;
    try { if (navigator.vibrate && (!navigator.userActivation || navigator.userActivation.hasBeenActive)) navigator.vibrate([220, 120, 220]); } catch (e) { /* ignore */ }
    chime();
  }

  // ---------- Per-second tickers ----------
  // <span data-countdown="ms">  -> m:ss until that time
  // <span data-left="ms">       -> "5 h 38 min left"
  // <span data-stopwatch="ms">  -> mm:ss since that time (stops if data-stop is set)
  function tick() {
    const n = nowMs();
    document.querySelectorAll("[data-countdown]").forEach(el => { el.textContent = mmss(Math.round((Number(el.dataset.countdown) - n) / 1000)); });
    document.querySelectorAll("[data-left]").forEach(el => { el.textContent = left(Number(el.dataset.left)); });
    document.querySelectorAll("[data-stopwatch]").forEach(el => {
      const end = el.dataset.stop ? Number(el.dataset.stop) : n;
      const sec = Math.max(0, Math.round((end - Number(el.dataset.stopwatch)) / 1000));
      el.textContent = String(Math.floor(sec / 60)).padStart(2, "0") + ":" + String(sec % 60).padStart(2, "0");
    });
  }
  setInterval(tick, 1000);
  function theme() { return document.documentElement.getAttribute("data-theme") || "calm"; }

  // Last drill vs today, as two bars. prev.seeded => labelled as sample data.
  function retestHTML(prev, right, total) {
    if (!prev) return "";
    const h = (r, t) => Math.max(8, Math.round(100 * (t ? r / t : 0)));
    const diff = right - prev.team_right;
    return '<div class="stack-sm"><span class="section-label">' + esc(prev.label) + " vs today</span>" +
      '<div class="bars"><div class="bar"><span>' + prev.team_right + "/" + prev.team_total + '</span><i style="height:' + h(prev.team_right, prev.team_total) + 'px"></i></div>' +
      '<div class="bar now"><span style="color:var(--blue)">' + right + "/" + total + '</span><i style="height:' + h(right, total) + 'px"></i></div></div>' +
      '<div class="row-between small muted" style="justify-content:space-around"><span>' + esc(prev.label) + (prev.seeded ? " (sample data)" : "") + "</span><span>Today</span></div>" +
      '<span class="bold">' + (diff > 0 ? diff + " more right calls than " + esc(prev.label.toLowerCase()) : diff === 0 ? "Same as " + esc(prev.label.toLowerCase()) : "Fewer right calls than " + esc(prev.label.toLowerCase())) + "</span></div>";
  }

  window.SM_UI = { retestHTML, esc, time, ago, left, mmss, nowMs, param, session, ICONS, toast, live, paint, onAct, staffTabs, mountOwnerNav, modeBanner, statusPill, alertFx, soundReady, unlockAudio, tick, theme };
})();
