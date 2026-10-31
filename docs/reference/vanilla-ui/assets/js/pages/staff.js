/* Staff phone: Today (all clear), the alert card, and History. */
(function () {
  "use strict";
  const U = window.SM_UI, API = window.SM_API, D = window.SM_DATA;
  const esc = U.esc;
  const staffId = U.param("staff");
  if (!staffId) { location.replace("index.html"); return; }
  const view = U.param("view") || "today";
  const main = document.getElementById("main");
  let lang = U.session("sm-lang") || "en";
  let logOpen = false;
  let person = null, clinic = null;

  document.getElementById("mode").innerHTML = U.modeBanner();
  document.getElementById("tabs").innerHTML = U.staffTabs(view === "history" ? "history" : "today", staffId);

  function header(alertCard) {
    const greet = person ? (view === "history" ? "History" : greeting() + ", " + person.name) : "";
    const langs = alertCard ? '<div class="lang-toggle" role="group" aria-label="Language">' +
      [["en", "EN"], ["kn", "ಕ"], ["hi", "हि"]].map(l => '<button type="button" data-act="lang" data-lang="' + l[0] + '" aria-pressed="' + (lang === l[0]) + '" aria-label="' + ({ en: "English", kn: "Kannada", hi: "Hindi" })[l[0]] + '">' + l[1] + "</button>").join("") + "</div>" : "";
    const left = alertCard && alertCard.status !== "new"
      ? '<a class="btn btn-ghost" href="staff.html?staff=' + esc(staffId) + '" data-act="back">' + U.ICONS.back + " Today</a>"
      : '<div class="who"><span class="small muted">' + esc(greet) + '</span><span class="app-name">ShieldMate</span></div>';
    const sound = !alertCard && window.SM_CONFIG.sound !== false && !U.soundReady()
      ? '<button type="button" class="sound-btn" data-act="sound">Turn on alert sound</button>' : "";
    U.paint(document.getElementById("top"), left + (langs || sound));
  }
  function greeting() { const h = new Date(U.nowMs()).getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; }
  function ackKey(id) { return "sm-ack-" + staffId + "-" + id; }

  // Which alert should this person see? An open one, or one they just acted on.
  function pickAlert(alerts) {
    const open = alerts.filter(a => a.status === "new");
    if (open.length) return open[0];
    return alerts.find(a => U.session(ackKey(a.id))) || null;
  }

  // A new alert animates once (slide in, shake) and buzzes + chimes once.
  function isFresh(a) {
    if (a.status !== "new") return false;
    const key = "sm-seen-" + staffId + "-" + a.id + "-" + (a.reopened ? "r" : "n");
    if (U.session(key)) return false;
    U.session(key, "1");
    return true;
  }

  function alertHTML(a, fresh) {
    const t = a.staff_view[lang] || a.staff_view.en;
    const ui = D.UI_TEXT[a.staff_view[lang] ? lang : "en"];
    const untranslated = !a.staff_view[lang];
    const doneCount = t.steps.filter(s => s.done).length;
    const isOpen = a.status === "new";
    const it = clinic.it_contact;
    const bold = U.theme() === "bold";
    const headCls = "card" + (bold ? " hero" : "") + (isOpen ? " breath" : "") + (fresh ? " slide-in shake" : "");
    let html = '<article class="' + headCls + '">' +
      (isOpen ? '<span class="pill pill-red">' + esc(ui.needs) + " · " + esc(U.ago(a.last_seen)) + "</span>"
              : '<span class="pill pill-green">' + esc(ui.handled) + " · " + esc(U.time(a.reported_at || a.mine_at)) + "</span>") +
      (a.reopened && isOpen ? '<span class="small bold" style="color:var(--red-ink)">It happened again after "That was me".</span>' : "") +
      "<h1>" + esc(t.headline) + "</h1>" +
      '<p class="ink-2">' + esc(t.known) + "</p>" +
      (untranslated ? '<p class="tiny muted">Not translated yet. Showing English.</p>' : "") +
      "</article>" +
      '<div class="row-between" style="padding:0 4px"><h2 style="font-size:18px">' + esc(ui.doThese) + '</h2><span class="small muted">' + doneCount + " " + esc(ui.of) + " " + t.steps.length + " " + esc(ui.done) + "</span></div>" +
      '<div class="progress-line" role="img" aria-label="' + doneCount + " of " + t.steps.length + ' steps done"><span style="width:' + Math.round(doneCount / t.steps.length * 100) + '%"></span></div>' +
      '<div class="steps' + (fresh ? " slide-in d2" : "") + '">' + t.steps.map(s =>
        '<div class="step"><button type="button" class="step-toggle" data-act="tick" data-n="' + s.index + '" data-done="' + s.done + '" aria-pressed="' + s.done + '">' +
        '<span class="check">' + (s.done ? U.ICONS.check : s.index + 1) + '</span><span class="text">' + esc(s.text) + "</span></button>" +
        (s.done && s.done_by && s.done_by !== person.name ? '<span class="by">Done by ' + esc(s.done_by) + "</span>" : "") +
        (s.call ? '<a class="btn btn-tint call" href="tel:' + esc(it.phone) + '">' + U.ICONS.phone + " " + esc(ui.call) + " " + esc(it.name) + "</a>" : "") +
        (s.call && s.done && a.it ? '<span class="by" role="status">' + esc(
          a.it.status === "received" ? it.name + " picked up at " + U.time(a.it.received_at) :
          a.it.status === "resolved" ? it.name + " says it's fixed. Dr. Rao is checking" :
          it.name + " hasn't picked up on ShieldMate yet") + "</span>" : "") +
        "</div>").join("") + "</div>" +
      '<p class="small ink-2" style="padding:0 4px"><strong>' + esc(ui.why) + "</strong> " + esc(t.why) + "</p>";
    const names = a.log_fields.usernames_tried;
    if (names.length) {
      html += '<details class="log" id="logbox"' + (logOpen ? " open" : "") + "><summary>" + esc(ui.details) + '</summary><div class="body">' +
        '<span class="tiny muted">Usernames tried, exactly as recorded</span>' +
        names.map(n => '<div class="log-value">' + esc(n) + "</div>").join("") +
        '<span class="tiny muted">ShieldMate never follows text found in logs. The steps above come from fixed rules.</span></div></details>';
    }
    if (isOpen) {
      html += '<div class="stack-sm" style="margin-top:6px">' +
        '<button type="button" class="btn btn-primary btn-lg btn-block" data-act="done">' + esc(ui.tell) + "</button>" +
        (a.rule_id === "60204" ? '<button type="button" class="btn btn-ghost btn-block" data-act="mine">' + esc(ui.mine) + "</button>" : "") + "</div>";
    } else if (a.status === "done") {
      html += '<div class="card tight" role="status" style="background:var(--green-soft)"><span class="bold" style="color:var(--green-ink)">Dr. Rao has been told</span>' +
        '<span class="small">He can see which steps you\'ve done. Follow the steps until he says otherwise.</span>' +
        '<button type="button" class="btn btn-soft" data-act="clear">Back to Today</button></div>';
    } else if (a.status === "mine") {
      html += '<div class="card tight" role="status" style="border:2px solid var(--blue)"><span class="bold">Thanks for telling us</span>' +
        '<span class="small">We\'ve told Dr. Rao it was you and paused this alert. If more wrong passwords appear within an hour, it comes straight back.</span>' +
        '<div class="row"><button type="button" class="btn btn-soft" data-act="clear">Back to Today</button><button type="button" class="btn btn-ghost" data-act="reopen">It wasn\'t all me: reopen</button></div></div>';
    }
    return html;
  }

  function todayHTML(alerts, drill, clinicData) {
    const handled = alerts.filter(a => a.status !== "new").slice(0, 3);
    let html = "";
    if (drill) {
      html += '<a class="card tight outlined" style="text-decoration:none;color:var(--ink)" href="drill.html?staff=' + esc(staffId) + "&code=" + esc(drill.code) + '">' +
        '<span class="pill pill-amber no-dot">Practice</span><span class="bold" style="font-size:18px">Team drill is on: ' + esc(drill.title) + "</span>" +
        '<span class="small muted">Tap to join with code ' + esc(drill.code) + "</span></a>";
    }
    html += '<section class="card"><span class="ok-icon">' + U.ICONS.shield.replace('class="icon"', 'class="icon" style="width:28px;height:28px"') + "</span>" +
      '<h1 style="font-size:26px">All clear</h1>' +
      '<p class="ink-2">Nothing needs you right now. ShieldMate is watching the clinic\'s ' + clinicData.devices.length + " computers.</p>" +
      '<span class="small muted">' + (clinicData.hidden_count ? clinicData.hidden_count + " routine events hidden today · " : "") + "Checked a few seconds ago</span></section>";
    if (!drill) {
      html += '<a class="card tight" style="flex-direction:row;align-items:center;gap:14px;text-decoration:none;color:var(--ink)" href="drill.html?staff=' + esc(staffId) + '">' +
        '<span style="width:44px;height:44px;border-radius:12px;background:var(--blue-soft);color:var(--blue);display:flex;align-items:center;justify-content:center;flex:none">' + U.ICONS.calendar + "</span>" +
        '<span class="grow stack-sm" style="gap:2px"><span class="bold">Team practice</span><span class="small muted">Ransomware drill · about 6 minutes · join when Dr. Rao starts it</span></span>' +
        '<span style="color:var(--blue)">' + U.ICONS.chevron + "</span></a>";
    }
    html += '<section class="card tight"><span class="section-label">Tip of the week</span><p>If a pop-up or note gives you a phone number for "IT support", don\'t call it. Only use the contact saved in ShieldMate.</p></section>';
    if (handled.length) {
      html += '<section class="stack-sm"><span class="section-label" style="padding:0 4px">Recently</span>' +
        handled.map(a => '<div class="card tight" style="flex-direction:row;justify-content:space-between"><span>' + esc(a.staff_view.en.headline.replace(/\.$/, "")) + '</span><span class="small muted" style="flex:none">' + esc(U.time(a.first_seen)) + "</span></div>").join("") + "</section>";
    }
    return html;
  }

  function historyHTML(alerts) {
    if (!alerts.length) return '<section class="card"><h1 style="font-size:22px">Nothing yet</h1><p class="muted">Alerts and drills you take part in will appear here.</p></section>';
    const label = { new: ["red", "Needs action"], done: ["green", "Handled"], mine: ["blue", "That was me"] };
    return '<div class="stack-sm">' + alerts.map(a => {
      const l = label[a.status] || ["grey", a.status];
      return '<div class="card tight"><div class="row-between"><span class="bold">' + esc(a.staff_view.en.headline) + "</span>" + U.statusPill(l[0], l[1]) + '</div><span class="small muted">' + esc(U.time(a.first_seen)) + "</span></div>";
    }).join("") + "</div>";
  }

  async function render() {
    const [c, alerts, drill] = await Promise.all([API.clinic(), API.alerts(person ? person.role : ""), API.currentDrill()]);
    clinic = c.clinic;
    person = c.staff.find(p => p.id === staffId);
    if (!person) { main.innerHTML = '<p class="card">Unknown person. <a href="index.html">Pick again</a>.</p>'; return; }
    document.title = "ShieldMate · " + person.name;
    if (view === "history") { header(false); U.paint(main, historyHTML(alerts)); return; }
    const a = pickAlert(alerts);
    current = a;
    header(a);
    const fresh = a ? isFresh(a) : false;
    U.paint(main, a ? alertHTML(a, fresh) : todayHTML(alerts, drill && drill.status !== "finished" ? drill : null, c));
    if (fresh) U.alertFx();
  }
  let current = null;

  document.addEventListener("toggle", (e) => { if (e.target.id === "logbox") logOpen = e.target.open; }, true);

  const refresh = U.live(render);
  U.onAct({
    sound: async () => { U.unlockAudio(); U.alertFx(); U.toast("Alert sound is on"); document.getElementById("top").__html = null; await refresh(); },
    lang: async (el) => { lang = el.dataset.lang; U.session("sm-lang", lang); main.__html = null; await refresh(); },
    tick: async (el) => { await API.tickStep(current.id, Number(el.dataset.n), staffId, el.dataset.done !== "true"); await refresh(); },
    done: async () => { U.session(ackKey(current.id), "1"); await API.done(current.id, staffId); await refresh(); },
    mine: async () => { U.session(ackKey(current.id), "1"); await API.mine(current.id, staffId); await refresh(); },
    reopen: async () => { await API.reopen(current.id); await refresh(); },
    clear: async () => { U.session(ackKey(current.id), null); await refresh(); },
    back: async () => { if (current) U.session(ackKey(current.id), null); location.href = "staff.html?staff=" + encodeURIComponent(staffId); }
  });
})();
