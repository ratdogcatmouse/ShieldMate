/* IT support panel: the clinic's IT contact (Suresh, CareIT) sees open incidents,
   marks "Call received", leaves notes and marks it resolved with what was done.
   Dr. Rao then confirms the fix (or sends it back) on his own screen. */
(function () {
  "use strict";
  const U = window.SM_UI, API = window.SM_API;
  const esc = U.esc;
  const main = document.getElementById("main");
  document.getElementById("mode").innerHTML = U.modeBanner();
  const drafts = {};          // typed notes survive the 2-second refresh
  let showClosed = false;

  const STATUS = {
    none: ["pill-grey", "Open · nobody has called yet"],
    called: ["pill-red", "Incoming call"],
    received: ["pill-amber", "You're on it"],
    resolved: ["pill-blue", "Waiting for Dr. Rao to confirm"],
    closed: ["pill-green", "Closed"]
  };

  function blockLine(act) {
    if (!act) return "No block proposed";
    const how = act.simulated ? " (simulated)" : " (sent through Wazuh)";
    if (act.status === "executed") return "Blocked until " + U.time(act.expires_at) + how + (act.confirm === "confirmed" ? ", confirmed working" : "");
    if (act.status === "proposed") return "Waiting for Dr. Rao to approve";
    if (act.status === "failed") return "Block didn't take effect: " + (act.failure || "attempts continued");
    return "Block " + act.status;
  }

  // Every value is escaped where it is built; rows hold ready-made HTML only.
  function details(a, act) {
    const t = (x) => esc(x);
    const mono = (x) => '<span class="mono">' + esc(x) + "</span>";
    const rows = [
      ["Wazuh rule", t(a.rule_id + (a.rule_id === "60204" ? " · multiple failed Windows logons" : a.rule_id === "100201" ? " · mass file changes (ransomware pattern)" : ""))],
      ["Computer", mono(a.agent_name)],
      ["First seen", t(U.time(a.first_seen) + " · last " + U.time(a.last_seen))]
    ];
    if (a.source_ip) rows.push(["Attacking address", mono(a.source_ip)]);
    if (a.count) rows.push(["Failed logons", t(a.count + " in " + a.window_minutes + " min")]);
    if (a.files) rows.push(["Files changed", t(String(a.files))]);
    if (a.log_fields.usernames_tried.length) rows.push(["Usernames tried", a.log_fields.usernames_tried.map(mono).join("<br>")]);
    if (a.rule_id === "60204") rows.push(["Block", t(blockLine(act))]);
    const done = a.owner_view.checklist.filter(c => c.done).map(c => esc(c.text) + ' <span class="muted">(' + esc(c.done_by || "") + ", " + esc(U.time(c.done_at)) + ")</span>");
    rows.push(["Done at the clinic", done.length ? done.join("<br>") : '<span class="muted">Nothing yet</span>']);
    return '<dl class="kv">' + rows.map(r => "<dt>" + esc(r[0]) + "</dt><dd>" + r[1] + "</dd>").join("") + "</dl>";
  }

  function ticket(a, act) {
    const it = a.it;
    const sentBack = it.status === "received" && it.sent_back_at;
    const cls = sentBack ? "sentback" : it.status;
    const st = sentBack ? ["pill-red", "Sent back by Dr. Rao"] : STATUS[it.status];
    let top = "";
    if (it.status === "called") {
      top = '<div class="callout"><span>' + U.ICONS.phone + " " + esc(it.called_by) + " called you at " + esc(U.time(it.called_at)) + " · " + esc(U.ago(it.called_at)) + "</span>" +
        '<button type="button" class="btn btn-primary" data-act="received" data-id="' + esc(a.id) + '">Call received</button></div>';
    } else if (it.status === "none") {
      top = '<div class="callout amber"><span>Nobody at the clinic has called yet. You can see it because you\'re their IT contact.</span>' +
        '<button type="button" class="btn btn-soft" data-act="received" data-id="' + esc(a.id) + '">I\'m on it</button></div>';
    } else if (sentBack) {
      top = '<div class="callout"><span>Dr. Rao checked and sent it back at ' + esc(U.time(it.sent_back_at)) + ": \u201C" + esc(it.sent_back_note) + "\u201D</span></div>";
    } else if (it.status === "resolved") {
      top = '<div class="callout blue"><span>You marked it resolved at ' + esc(U.time(it.resolved_at)) + ". Dr. Rao is checking: \"" + esc(it.resolved_note) + "\"</span></div>";
    }
    let work = "";
    if (it.status === "received") {
      work = '<section class="stack-sm"><label class="field-label" for="note-' + esc(a.id) + '">Note for Dr. Rao</label>' +
        '<textarea class="it-note" id="note-' + esc(a.id) + '" data-note="' + esc(a.id) + '" maxlength="300" placeholder="What you checked or changed. To mark it resolved, say what fixed it.">' + esc(drafts[a.id] || "") + "</textarea>" +
        '<div class="row"><button type="button" class="btn btn-primary" data-act="resolved" data-id="' + esc(a.id) + '">Mark resolved</button>' +
        '<button type="button" class="btn btn-soft" data-act="note" data-id="' + esc(a.id) + '">Add note only</button></div></section>';
    }
    const log = it.log.length ? '<section class="stack-sm"><span class="section-label">History</span><div class="timeline">' +
      it.log.slice().reverse().map(l => '<div class="ev"><time>' + esc(U.time(l.at)) + "</time><span><strong>" + esc(l.by) + ":</strong> " + esc(l.text) + "</span></div>").join("") + "</div></section>" : "";
    return '<article class="card ticket ' + cls + (it.status === "called" ? " slide-in" : "") + '" aria-label="' + esc(a.owner_view.headline) + '">' +
      '<div class="row-between"><span class="pill ' + st[0] + '">' + esc(st[1]) + '</span><span class="small muted">Started ' + esc(U.time(a.first_seen)) + " · " + esc(U.ago(a.first_seen)) + "</span></div>" +
      '<h2 style="font-size:22px">' + esc(a.owner_view.headline) + "</h2>" + top +
      '<details class="log" open><summary>Technical details</summary><div class="body">' + details(a, act) + "</div></details>" +
      (a.it_playbook.length ? '<details class="log"><summary>Suggested fix</summary><div class="body"><ol class="playbook">' + a.it_playbook.map(x => "<li>" + esc(x) + "</li>").join("") + "</ol></div></details>" : "") +
      work + log + "</article>";
  }

  function closedList(closed) {
    if (!closed.length) return "";
    return '<section class="card tight"><button type="button" class="row-between" style="background:none;border:0;padding:0;font:inherit;cursor:pointer;width:100%" data-act="toggleclosed" aria-expanded="' + showClosed + '">' +
      '<span class="section-label" style="margin:0">Closed today (' + closed.length + ")</span><span>" + (showClosed ? "▴" : "▾") + "</span></button>" +
      (showClosed ? closed.map(a => '<div class="list-row" style="align-items:flex-start;flex-direction:column;gap:2px"><span class="bold">' + esc(a.owner_view.headline) + '</span><span class="small muted">Your fix: ' + esc((a.it.log.filter(l => l.text.indexOf("Marked resolved: ") === 0).pop() || { text: "" }).text.replace("Marked resolved: ", "")) + " · confirmed by " + esc(a.it.closed_by) + " at " + esc(U.time(a.it.closed_at)) + "</span></div>").join("") : "") + "</section>";
  }

  function sideHTML(c) {
    return '<section class="card tight"><span class="section-label">Clinic</span><span class="bold" style="font-size:18px">' + esc(c.clinic.name) + "</span>" +
      '<span class="small">Owner: Dr. Rao · signed in as ' + esc(c.clinic.it_contact.name) + "</span></section>" +
      '<section class="list" aria-label="Computers"><h2 style="font-size:18px;margin:12px 0 4px">Computers</h2>' +
      c.devices.map(d => '<div class="list-row"><span>' + esc(d.short) + ' <span class="small muted mono">' + esc(d.agent) + "</span></span>" + U.statusPill(d.tone, d.status_label) + "</div>").join("") + "</section>" +
      '<section class="card tight"><span class="section-label">How this works</span><ol class="playbook small"><li>Staff call you and tick it on their phone.</li><li>Tap <strong>Call received</strong> so Dr. Rao knows you\'re on it.</li><li>When it\'s fixed, <strong>Mark resolved</strong> and say what you did.</li><li>Dr. Rao confirms, or sends it back.</li></ol></section>';
  }

  async function render() {
    if (document.activeElement && document.activeElement.classList.contains("it-note")) return; // don't disturb typing
    const [c, alerts, actions] = await Promise.all([API.clinic(), API.alerts("it", true), API.actions()]);
    document.getElementById("who").textContent = c.clinic.it_contact.name + " · IT contact for " + c.clinic.name;
    const open = alerts.filter(a => !a.closed && a.status !== "mine");
    const order = { called: 0, received: 1, none: 2, resolved: 3 };
    open.sort((x, y) => order[x.it.status] - order[y.it.status] || y.first_seen - x.first_seen);
    const closed = alerts.filter(a => a.closed);
    const ringing = open.filter(a => a.it.status === "called");
    ringing.forEach(a => { const k = "sm-it-seen-" + a.id; if (!U.session(k)) { U.session(k, "1"); U.alertFx(); } });
    const countEl = document.getElementById("count");
    countEl.textContent = open.length ? open.length + " open" : "All quiet";
    countEl.style.color = "#C9C2F5";
    const list = open.length ? open.map(a => ticket(a, actions.find(x => x.alert_id === a.id))).join("") :
      '<section class="card"><span class="ok-icon">' + U.ICONS.shield + '</span><h1>Nothing open at ' + esc(c.clinic.name) + "</h1><p class=\"ink-2\">When staff call you about an alert, it appears here. Keep this page open.</p></section>";
    U.paint(main, '<div class="col">' + list + closedList(closed) + '</div><aside class="col">' + sideHTML(c) + "</aside>");
  }

  main.addEventListener("input", (e) => { if (e.target.dataset && e.target.dataset.note) drafts[e.target.dataset.note] = e.target.value; });
  main.addEventListener("focusout", (e) => { if (e.target.classList && e.target.classList.contains("it-note")) setTimeout(refresh, 0); });

  const refresh = U.live(render);
  async function send(el, action) {
    const id = el.dataset.id;
    await API.itAction(id, action, drafts[id] || "");
    if (action !== "received") drafts[id] = "";
    U.toast(action === "received" ? "Dr. Rao can see you're on it" : action === "note" ? "Note added" : "Sent to Dr. Rao to confirm");
    main.__html = null; if (document.activeElement) document.activeElement.blur(); await refresh();
  }
  U.onAct({
    received: (el) => send(el, "received"),
    note: (el) => send(el, "note"),
    resolved: (el) => {
      if ((drafts[el.dataset.id] || "").trim().length < 5) {   // same rule as the server, checked before sending
        U.toast("Say what you did, so Dr. Rao can check it");
        const box = document.getElementById("note-" + el.dataset.id); if (box) box.focus();
        return;
      }
      return send(el, "resolved");
    },
    toggleclosed: async () => { showClosed = !showClosed; main.__html = null; await refresh(); }
  });
})();
