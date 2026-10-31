/* Owner: Right now. Live approval card, ransomware incident, computers, activity.
   Laptop: side menu. Phone (under 900 px): bottom tabs. */
(function () {
  "use strict";
  const U = window.SM_UI, API = window.SM_API;
  const esc = U.esc;
  const main = document.getElementById("main");
  document.getElementById("mode").innerHTML = U.modeBanner();
  let restoreBusy = false;

  function liveBadge() {
    return window.SM_CONFIG.mode === "mock"
      ? '<span class="pill pill-blue">Demo data · replay mode</span>'
      : '<span class="pill pill-blue">Live · connected</span>';
  }

  function approvalCard(act, alert, clinic) {
    const rule = clinic.standing_rule.on;
    const decideAt = U.time(act.decide_by);
    const timer = act.status === "proposed"
      ? (rule ? "Your rule blocks it at <strong>" + esc(decideAt) + "</strong> if you don't answer (" + U.mmss(act.seconds_left) + ")"
              : "If you don't answer by <strong>" + esc(decideAt) + "</strong>, we'll ask your backup person (" + U.mmss(act.seconds_left) + ")")
      : "Nobody answered in time, and there's no backup person, so nothing was blocked.";
    return '<article class="card outlined">' +
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
      '<p class="ink-2"><strong>0 attempts</strong> have got through since the block. It lifts by itself at ' + esc(U.time(act.expires_at)) + ".</p>" +
      '<div class="row"><button type="button" class="btn btn-soft" data-act="undo" data-id="' + esc(act.id) + '">Undo block</button>' +
      '<span class="small ink-2">Next: ask your IT contact to change the reception password.</span></div>' +
      (act.simulated ? '<span class="pill pill-sim">Simulated action</span>' : "") + "</article>";
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
      certin: '<section class="card dark"><span class="small on-dark-muted">Report to CERT-In by</span><span class="big">' + esc(U.time(a.certin_due_at)) + '</span><span class="on-dark-muted">' + esc(U.left(a.certin_due_at)) + " · 6 hours from " + esc(U.time(a.first_seen)) + "</span>" +
        '<span class="small on-dark-muted">Next step after the demo: a report drafted from this timeline, for you to check and send.</span></section>'
    };
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

  async function render() {
    const [c, alerts, actions, events, restore] = await Promise.all([API.clinic(), API.alerts("owner"), API.actions(), API.activity(), API.restoreLatest()]);
    const clinic = c.clinic;
    const pw = alerts.find(a => a.rule_id === "60204");
    const rw = alerts.find(a => a.rule_id === "100201" && a.status !== "mine");
    const act = pw ? actions.find(x => x.alert_id === pw.id) : null;
    let mainCol = "", side = "";
    let urgent = false;

    if (rw) {
      const inc = incident(rw, restore);
      // Phone: deadline right under the incident. Laptop: deadline in the side column.
      mainCol += inc.head + inc.certin.replace('class="card dark"', 'class="card dark phone-only"') + inc.checklist;
      side += inc.certin.replace('class="card dark"', 'class="card dark laptop-only"');
      urgent = true;
    }
    // Order: decisions needed first, then the ransomware incident, then things already handled.
    if (pw && pw.status === "mine") mainCol += mineCard(pw);
    else if (act && (act.status === "proposed" || act.status === "escalated")) { mainCol = approvalCard(act, pw, clinic) + mainCol; urgent = true; }
    else if (act && act.status === "executed") mainCol += blockedCard(act);
    else if (act && act.status === "declined") { mainCol = declinedCard(act) + mainCol; urgent = true; }
    else if (pw && pw.status === "new" && !act) { mainCol = '<article class="card"><span class="pill pill-red">Needs you now</span><h1>' + esc(pw.owner_view.headline) + '</h1><p class="ink-2">' + esc(pw.owner_view.known) + "</p></article>" + mainCol; urgent = true; }

    if (!mainCol) {
      mainCol = '<section class="card"><span class="ok-icon">' + U.ICONS.shield + '</span><h1>All clear</h1><p class="ink-2">Nothing needs you right now. ShieldMate is watching ' + c.devices.length + " computers" + (c.hidden_count ? " and has hidden " + c.hidden_count + " routine events today" : "") + ".</p>" +
        '<span class="small muted">Use Backstage to replay an attack for the demo.</span></section>';
    }
    const handled = alerts.filter(a => (a.status === "done" || (a.rule_id === "60204" && act && ["executed", "expired", "undone"].includes(act.status))));
    if (handled.length) {
      mainCol += '<section class="card tight"><span class="section-label">Practise what just happened</span>' + handled.slice(0, 2).map(a =>
        '<div class="row-between"><span>' + esc(a.owner_view.headline.replace(/\.$/, "")) + '</span><a class="btn btn-ghost" href="owner-drill.html?scenario=' + esc(a.drill_scenario) + '">Practise this with the team</a></div>').join("") + "</section>";
    }
    side += devicesHTML(c.devices) + activityHTML(events);

    U.mountOwnerNav("now", { urgent });
    U.paint(main,
      '<div class="owner-head"><div><span class="owner-mobile-head">Sunrise Family Clinic</span><h1>Right now</h1></div>' + liveBadge() + "</div>" +
      '<div class="cols"><div class="col-main">' + mainCol + '</div><aside class="col-side">' + side + "</aside></div>");
  }

  const refresh = U.live(render);
  U.onAct({
    approve: async (el) => { await API.approve(el.dataset.id); await refresh(); },
    decline: async (el) => { await API.decline(el.dataset.id); await refresh(); },
    undo: async (el) => { await API.undo(el.dataset.id); await refresh(); },
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
