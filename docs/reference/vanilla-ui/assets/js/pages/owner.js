/* Owner: Right now. Live approval card, ransomware incident, computers, activity.
   Laptop: side menu. Phone (under 900 px): bottom tabs. */
(function () {
  "use strict";
  const U = window.SM_UI, API = window.SM_API;
  const esc = U.esc;
  const main = document.getElementById("main");
  document.getElementById("mode").innerHTML = U.modeBanner();
  let restoreBusy = false;
  let sendBackFor = null, sendBackDraft = ""; // "Not fixed yet": optional reason for IT
  let freshAct = null; // approval card that just arrived: slides in once, phone buzzes once

  // Say exactly where alerts come from: judges may ask, and "live" must mean real Wazuh alerts.
  function liveBadge(c) {
    const lv = c && c.live;
    if (window.SM_CONFIG.mode === "mock") return '<span class="pill pill-blue">Demo data · replay mode</span>';
    if (!lv || lv.source !== "wazuh") return '<span class="pill pill-blue">Recorded alerts · replay mode</span>';
    return lv.ok === false ? '<span class="pill pill-red">Wazuh not reachable</span>' : '<span class="pill pill-blue">Live · Wazuh connected</span>';
  }

  function approvalCard(act, alert, clinic) {
    const rule = clinic.standing_rule.on;
    const decideAt = U.time(act.decide_by);
    const cd = '<span class="mono bold" data-countdown="' + Number(act.decide_by) + '">' + U.mmss(act.seconds_left) + "</span>";
    const timer = act.status === "proposed"
      ? (rule ? "Your rule blocks it at <strong>" + esc(decideAt) + "</strong> if you don't answer · " + cd
              : "If you don't answer by <strong>" + esc(decideAt) + "</strong>, we'll ask your backup person · " + cd)
      : "Nobody answered in time, and there's no backup person, so nothing was blocked.";
    return '<article class="card outlined' + (freshAct === act.id ? " slide-in" : "") + '">' +
      '<span class="pill pill-red">' + (act.status === "escalated" ? "Still needs your decision" : "Your decision needed") + "</span>" +
      "<h1>Block the attacker on the reception computer for 1 hour?</h1>" +
      '<p class="ink-2">' + esc(alert ? alert.count + " wrong passwords from " : "Attacks from ") + '<span class="mono">' + esc(act.target_ip) + "</span>" + esc(alert ? " in " + alert.window_minutes + " minutes." : ".") + (alert && alert.status === "done" ? " " + esc(alert.reported_by) + " has already stopped using that computer." : "") + "</p>" +
      '<div class="facts">' +
      '<div class="fact"><span class="k">What it does</span><span class="v">Stops only that address</span></div>' +
      '<div class="fact"><span class="k">How long</span><span class="v">1 hour, or undo sooner</span></div>' +
      '<div class="fact"><span class="k">If you don\'t answer</span><span class="v">' + (rule ? "Your rule blocks it" : "Backup person is asked") + "</span></div></div>" +
      '<div class="tinted row nowrap" style="gap:8px">' + U.ICONS.clock + "<span>" + timer + "</span></div>" +
      '<div class="btn-group"><button type="button" class="btn btn-primary btn-lg" data-act="approve" data-id="' + esc(act.id) + '">Approve block</button>' +
      '<button type="button" class="btn btn-soft btn-lg" data-act="decline" data-id="' + esc(act.id) + '">Decline</button></div>' +
      '<span class="small muted">Proposed by ShieldMate\'s fixed rules, not by AI.' + (act.simulated ? " In demo mode the block is simulated." : "") + "</span></article>";
  }
  function blockedCard(act) {
    const how = act.decided_via === "standing_rule" ? "by your standing rule" : "by you";
    return '<article class="card" role="status"><span class="pill pill-green">Blocked · approved ' + esc(how) + " at " + esc(U.time(act.decided_at)) + "</span>" +
      "<h1>The attacker can't reach the reception computer.</h1>" +
      '<p class="ink-2"><strong>' + (act.attempts_since || 0) + (act.attempts_since === 1 ? " attempt" : " attempts") + "</strong> " + (act.attempts_since === 1 ? "has" : "have") + " got through since the block. It lifts by itself at " + esc(U.time(act.expires_at)) + ".</p>" +
      (act.confirm === "checking" ? '<span class="small muted">Checking the block worked: watching for new attempts for 30 seconds…</span>' : act.confirm === "confirmed" ? '<span class="small" style="color:var(--green-ink)">Confirmed by Wazuh: no new attempts from ' + esc(act.target_ip) + ".</span>" : "") +
      '<div class="row"><button type="button" class="btn btn-soft" data-act="undo" data-id="' + esc(act.id) + '">Undo block</button>' +
      '<span class="small ink-2">Next: ask your IT contact to change the reception password.</span></div>' +
      (act.simulated ? '<span class="pill pill-sim">Simulated action</span>' : "") + "</article>";
  }
  function failedCard(act) {
    return '<article class="card urgent" role="alert"><span class="pill pill-red">The block didn\'t take effect</span>' +
      "<h1>The attack on the reception computer is still going.</h1>" +
      '<p class="ink-2">' + esc(act.failure || "Wrong passwords from that address are still arriving.") + " Call your IT contact now, and keep staff off that computer.</p>" +
      '<div class="row"><button type="button" class="btn btn-primary" data-act="approve" data-id="' + esc(act.id) + '">Try the block again</button></div></article>';
  }
  function declinedCard(act) {
    return '<article class="card" role="status"><span class="pill pill-grey no-dot">Declined · no action taken</span>' +
      "<h1>The attack on the reception computer is still going.</h1>" +
      '<p class="ink-2">Call your IT contact now, and keep staff off that computer.</p>' +
      '<div class="row"><button type="button" class="btn btn-primary" data-act="approve" data-id="' + esc(act.id) + '">Block it after all</button></div></article>';
  }
  function mineCard(a) {
    return '<article class="card tight"><span class="pill pill-blue no-dot">Paused · "That was me"</span>' +
      '<span class="bold">' + esc(a.mine_by) + " says the wrong passwords on the reception computer were their own typing.</span>" +
      '<span class="small muted">' + esc(U.time(a.mine_at)) + ". The alert comes back if it happens again within an hour.</span></article>";
  }

  function incident(a, restore) {
    const ov = a.owner_view;
    const done = ov.checklist.filter(c => c.done).length;
    const items = ov.checklist.map(c => {
      let extra = "";
      if (c.done && c.done_by) extra = '<span class="small muted">' + esc(c.done_by) + ", " + esc(U.time(c.done_at)) + "</span>";
      if (c.button === "restore") {
        if (restore && restore.result !== "NOT_TESTED" && c.done) extra = '<span class="small" style="color:var(--red-ink)"><strong>Not safe:</strong> ' + Math.round(restore.backup_age_hours / 24) + " days old · " + restore.files_ok + " of " + restore.files_total + " files intact · always plugged in. <a href=\"owner-readiness.html\">See fixes</a></span>";
        else extra = '<button type="button" class="btn btn-primary" style="align-self:flex-start" data-act="restore"' + (restoreBusy ? " disabled" : "") + ">" + (restoreBusy ? "Testing the backup…" : "Test backup now") + "</button>";
      }
      const box = c.manual
        ? '<button type="button" class="check" style="cursor:pointer;background:' + (c.done ? "var(--green)" : "transparent") + ";border-color:" + (c.done ? "var(--green)" : "#8A97A8") + ';color:#fff" data-act="ownertick" data-n="' + c.index + '" data-done="' + c.done + '" aria-pressed="' + c.done + '" aria-label="Mark done: ' + esc(c.text) + '">' + (c.done ? U.ICONS.check : "") + "</button>"
        : '<span class="check" style="background:' + (c.done ? "var(--green)" : "transparent") + ";border-color:" + (c.done ? "var(--green)" : "#8A97A8") + ';color:#fff" aria-hidden="true">' + (c.done ? U.ICONS.check : "") + "</span>";
      return '<div class="list-row" style="justify-content:flex-start;align-items:flex-start;gap:14px;padding:12px 0">' + box +
        '<span class="stack-sm grow" style="gap:6px"><span>' + esc(c.text) + "</span>" + extra + "</span></div>";
    }).join("");
    return {
      head: '<article class="card"><div class="row"><span class="pill pill-red">Needs you now</span><span class="small muted">Started ' + esc(U.time(a.first_seen)) + " · " + esc(U.ago(a.first_seen)) + "</span></div>" +
        "<h1>" + esc(ov.headline) + '</h1><p class="ink-2">' + esc(ov.known) + "</p></article>",
      checklist: '<section class="card" aria-label="What has to happen"><div class="row-between"><h2>What has to happen</h2><span class="small muted">' + done + " of " + ov.checklist.length + ' done</span></div><div>' + items + "</div></section>",
      certin: '<section class="card dark"><span class="small on-dark-muted">Report to CERT-In by</span><span class="big">' + esc(U.time(a.certin_due_at)) + '</span><span class="on-dark-muted"><span data-left="' + Number(a.certin_due_at) + '">' + esc(U.left(a.certin_due_at)) + "</span> · 6 hours from " + esc(U.time(a.first_seen)) + "</span>" +
        '<span class="small on-dark-muted">Next step after the demo: a report drafted from this timeline, for you to check and send.</span></section>'
    };
  }

  // IT support: Called → Picked up → Resolved → You confirmed. The owner verifies, IT doesn't close.
  function itCard(a) {
    const it = a.it, who = it.contact;
    const steps = [["Called", it.called_at, it.called_by], ["Picked up", it.received_at], ["Resolved", it.resolved_at], ["You confirmed", it.closed_at]];
    const lastOn = steps.reduce((n, x, i) => (x[1] ? i : n), -1);
    const strip = '<div class="stages" role="img" aria-label="IT progress: ' + esc(steps.filter(x => x[1]).map(x => x[0]).join(", ") || "not called yet") + '">' + steps.map((x, i) =>
      '<span class="stage' + (x[1] ? " on" : i === lastOn + 1 && lastOn >= 0 ? " wait" : "") + '"><i></i>' + esc(x[0]) + (x[1] ? '<span class="small muted" style="font-weight:400">' + esc(U.time(x[1])) + "</span>" : "") + "</span>").join("") + "</div>";
    const notes = it.log.filter(l => l.by === who && !/^(Picked up|Picked it up|Marked resolved)/.test(l.text));
    const latest = notes.length ? '<span class="small"><strong>Latest note:</strong> ' + esc(notes[notes.length - 1].text) + "</span>" : "";
    const waitMin = it.called_at ? Math.floor((U.nowMs() - it.called_at) / 60000) : 0;
    let pill, body = "";
    if (it.status === "none") {
      pill = '<span class="pill pill-grey no-dot">Not called yet</span>';
      body = '<p class="ink-2">Nobody has called ' + esc(who) + " yet. Staff are asked to call from their alert card.</p>" +
        '<a class="btn btn-soft" style="align-self:flex-start" href="tel:' + esc(it.phone) + '">' + U.ICONS.phone + " Call " + esc(who) + "</a>";
    } else if (it.status === "called") {
      pill = waitMin >= 10 ? '<span class="pill pill-red">No answer for ' + waitMin + " min</span>" : '<span class="pill pill-amber">Waiting for IT</span>';
      body = '<p class="ink-2">' + esc(it.called_by) + " called at " + esc(U.time(it.called_at)) + ". " + esc(who) + " hasn't picked it up on ShieldMate yet.</p>" +
        (waitMin >= 10 ? '<a class="btn btn-primary" style="align-self:flex-start" href="tel:' + esc(it.phone) + '">' + U.ICONS.phone + " Call " + esc(who) + " yourself</a>" : "");
    } else if (it.status === "received") {
      pill = '<span class="pill pill-amber">IT is on it</span>';
      body = '<p class="ink-2">' + esc(who) + " has been on it since " + esc(U.time(it.received_at)) + "." + (it.sent_back_at ? " You sent it back at " + esc(U.time(it.sent_back_at)) + "." : "") + "</p>" + latest;
    } else if (it.status === "resolved") {
      pill = '<span class="pill pill-blue">Check and close</span>';
      body = '<div class="callout blue" style="display:block"><span>' + esc(who) + " says it's fixed:</span><p style=\"font-weight:400;margin:6px 0 0\">\u201C" + esc(it.resolved_note) + "\u201D</p></div>" +
        '<span class="small ink-2">Before you confirm: ask the staff member whether the computer works normally, and check the steps above are done.</span>' +
        (sendBackFor === a.id
          ? '<label class="field-label" for="sb-' + esc(a.id) + '">What\'s still wrong? (optional, ' + esc(who) + " sees this)</label>" +
            '<input class="it-note" style="min-height:52px" id="sb-' + esc(a.id) + '" maxlength="200" autocomplete="off" placeholder="e.g. Reception still can\'t open appointments" value="' + esc(sendBackDraft) + '">' +
            '<div class="row"><button type="button" class="btn btn-primary" data-act="sendbackgo" data-id="' + esc(a.id) + '">Send back to ' + esc(who) + "</button>" +
            '<button type="button" class="btn btn-ghost" data-act="sendbackcancel">Cancel</button></div>'
          : '<div class="row"><button type="button" class="btn btn-primary" data-act="confirmfix" data-id="' + esc(a.id) + '">Confirm it\'s fixed and close</button>' +
            '<button type="button" class="btn btn-soft" data-act="sendback" data-id="' + esc(a.id) + '">Not fixed yet</button></div>');
    }
    return '<section class="card" aria-label="IT support for: ' + esc(a.owner_view.headline) + '"><div class="row-between"><div class="stack-sm" style="gap:2px"><h2>IT support · ' + esc(who) + '</h2><span class="small muted">For: ' + esc(a.owner_view.headline.replace(/\.$/, "")) + "</span></div>" + pill + "</div>" + strip + body + "</section>";
  }
  function closedCard(closed) {
    if (!closed.length) return "";
    return '<section class="card tight"><span class="section-label">Closed today</span>' + closed.slice(0, 3).map(a => {
      const fix = (a.it.log.filter(l => l.text.indexOf("Marked resolved: ") === 0).pop() || { text: "" }).text.replace("Marked resolved: ", "");
      return '<div class="list-row" style="align-items:flex-start;flex-direction:column;gap:4px"><span class="row" style="gap:8px">' + U.statusPill("green", "Closed") + '<span class="bold">' + esc(a.owner_view.headline.replace(/\.$/, "")) + "</span></span>" +
        '<span class="small ink-2">Fixed by ' + esc(a.it.contact) + ": " + esc(fix) + " · you confirmed at " + esc(U.time(a.it.closed_at)) + "</span>" +
        '<a class="btn btn-ghost" style="padding-left:0" href="owner-drill.html?scenario=' + esc(a.drill_scenario) + '">Practise this with the team</a></div>';
    }).join("") + "</section>";
  }

  function devicesHTML(devices) {
    return '<section class="list" aria-label="Computers"><h2 style="font-size:18px;margin:12px 0 4px">Computers</h2>' +
      devices.map(d => '<div class="list-row"><span>' + esc(d.short) + "</span>" + U.statusPill(d.tone, d.status_label) + "</div>").join("") + "</section>";
  }
  function activityHTML(events) {
    if (!events.length) return "";
    return '<section class="card"><h2 style="font-size:18px">What happened</h2><div class="timeline">' +
      events.slice(0, 7).map(e => '<div class="ev"><time>' + esc(U.time(e.at)) + "</time><span>" + esc(e.text) + "</span></div>").join("") + "</div></section>";
  }

  main.addEventListener("input", (e) => { if (e.target.id && e.target.id.indexOf("sb-") === 0) sendBackDraft = e.target.value; });

  async function render() {
    if (document.activeElement && document.activeElement.id && document.activeElement.id.indexOf("sb-") === 0) return; // don't disturb typing
    const [c, all, actions, events, restore] = await Promise.all([API.clinic(), API.alerts("owner", true), API.actions(), API.activity(), API.restoreLatest()]);
    const alerts = all.filter(a => !a.closed);
    const closed = all.filter(a => a.closed);
    const clinic = c.clinic;
    const pw = alerts.find(a => a.rule_id === "60204");
    const rw = alerts.find(a => a.rule_id === "100201" && a.status !== "mine");
    const act = pw ? actions.find(x => x.alert_id === pw.id) : null;
    let mainCol = "", side = "";
    let urgent = false;

    if (rw) {
      const inc = incident(rw, restore);
      // Phone: deadline right under the incident. Laptop: deadline in the side column.
      mainCol += inc.head + inc.certin.replace('class="card dark"', 'class="card dark phone-only"') + inc.checklist + itCard(rw);
      side += inc.certin.replace('class="card dark"', 'class="card dark laptop-only"');
      urgent = true;
    }
    // Order: decisions needed first, then the ransomware incident, then things already handled.
    if (pw && pw.status === "mine") mainCol += mineCard(pw);
    else if (act && (act.status === "proposed" || act.status === "escalated")) {
      const key = "sm-seen-owner-" + act.id;
      freshAct = U.session(key) ? null : act.id;
      if (freshAct) { U.session(key, "1"); U.alertFx(); }
      mainCol = approvalCard(act, pw, clinic) + mainCol; urgent = true;
    }
    else if (act && act.status === "executed") mainCol += blockedCard(act);
    else if (act && act.status === "declined") { mainCol = declinedCard(act) + mainCol; urgent = true; }
    else if (act && act.status === "failed") { mainCol = failedCard(act) + mainCol; urgent = true; }
    else if (pw && pw.status === "new" && !act) { mainCol = '<article class="card"><span class="pill pill-red">Needs you now</span><h1>' + esc(pw.owner_view.headline) + '</h1><p class="ink-2">' + esc(pw.owner_view.known) + "</p></article>" + mainCol; urgent = true; }

    if (pw && pw.status !== "mine") mainCol += itCard(pw);
    // IT says it's fixed: that's a decision for the owner, so the nav shows it as needing attention.
    [rw, pw].forEach(a => { if (a && a.it.status === "resolved") urgent = true; });

    if (!mainCol) {
      mainCol = '<section class="card"><span class="ok-icon">' + U.ICONS.shield + '</span><h1>All clear</h1><p class="ink-2">Nothing needs you right now. ShieldMate is watching ' + c.devices.length + " computers" + (c.hidden_count ? " and has hidden " + c.hidden_count + " routine events today" : "") + ".</p>" +
        '<span class="small muted">Use Backstage to replay an attack for the demo.</span></section>';
    }
    const handled = alerts.filter(a => (a.status === "done" || (a.rule_id === "60204" && act && ["executed", "expired", "undone"].includes(act.status))));
    if (handled.length) {
      mainCol += '<section class="card tight"><span class="section-label">Practise what just happened</span>' + handled.slice(0, 2).map(a =>
        '<div class="row-between"><span>' + esc(a.owner_view.headline.replace(/\.$/, "")) + '</span><a class="btn btn-ghost" href="owner-drill.html?scenario=' + esc(a.drill_scenario) + '">Practise this with the team</a></div>').join("") + "</section>";
    }
    mainCol += closedCard(closed);
    side += devicesHTML(c.devices) + activityHTML(events);

    U.mountOwnerNav("now", { urgent });
    U.paint(main,
      '<div class="owner-head"><div><span class="owner-mobile-head">Sunrise Family Clinic</span><h1>Right now</h1></div>' + liveBadge(c) + "</div>" +
      '<div class="cols"><div class="col-main">' + mainCol + '</div><aside class="col-side">' + side + "</aside></div>");
  }

  const refresh = U.live(render);
  U.onAct({
    approve: async (el) => { await API.approve(el.dataset.id); await refresh(); },
    decline: async (el) => { await API.decline(el.dataset.id); await refresh(); },
    undo: async (el) => { await API.undo(el.dataset.id); await refresh(); },
    confirmfix: async (el) => { await API.closeIncident(el.dataset.id, true); U.toast("Incident closed"); await refresh(); },
    sendback: async (el) => { sendBackFor = el.dataset.id; sendBackDraft = ""; main.__html = null; await refresh(); const box = document.getElementById("sb-" + el.dataset.id); if (box) box.focus(); },
    sendbackcancel: async () => { sendBackFor = null; main.__html = null; await refresh(); },
    sendbackgo: async (el) => {
      await API.closeIncident(el.dataset.id, false, sendBackDraft.trim());
      sendBackFor = null; sendBackDraft = ""; U.toast("Sent back to IT"); main.__html = null; await refresh();
    },
    ownertick: async (el) => {
      const alerts = await API.alerts("owner");
      const rw = alerts.find(a => a.rule_id === "100201");
      await API.tickStep(rw.id, Number(el.dataset.n), "rao", el.dataset.done !== "true", "owner");
      await refresh();
    },
    restore: async () => {
      restoreBusy = true; main.__html = null; await refresh();
      await new Promise(r => setTimeout(r, 1500));
      await API.runRestore();
      restoreBusy = false; main.__html = null; await refresh();
    }
  });
})();
