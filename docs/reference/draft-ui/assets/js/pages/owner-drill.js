/* Owner: start and host a team drill. Lobby with join code, each moment,
   owner decisions, restore check at moment 3, and team results. */
(function () {
  "use strict";
  const U = window.SM_UI, API = window.SM_API;
  const esc = U.esc;
  const main = document.getElementById("main");
  document.getElementById("mode").innerHTML = U.modeBanner();
  let code = U.param("code");
  const suggested = U.param("scenario");
  let testing = false;
  const hostKey = (c) => "sm-host-" + c;

  async function ensureHost() {
    if (!code) return null;
    let pid = U.session(hostKey(code));
    if (!pid) { const r = await API.joinDrill(code, "rao"); pid = r.player_id; U.session(hostKey(code), pid); }
    return pid;
  }

  function startHTML() {
    const pwSuggested = suggested === "password_guessing";
    return '<div class="owner-head"><div><span class="owner-mobile-head">Sunrise Family Clinic</span><h1>Team drill</h1></div></div>' +
      '<div class="cols"><section class="card col-main"><h2>Practise with your team</h2>' +
      '<p class="ink-2">A guided drill on everyone\'s phone. About 6 minutes. Nothing real is touched.</p>' +
      '<label class="field-label" for="scenario">Scenario</label>' +
      '<select id="scenario" class="field"><option value="ransomware_clinic">Ransomware at the clinic</option>' +
      '<option value="password_guessing"' + (pwSuggested ? " selected" : "") + ">Password guessing (not playable yet)</option></select>" +
      (pwSuggested ? '<p class="small muted">Suggested from today\'s alert. The password drill isn\'t playable in this build; ransomware is.</p>' : "") +
      '<button type="button" class="btn btn-primary btn-lg" style="align-self:flex-start" data-act="start">Start team drill</button></section>' +
      '<aside class="col-side"><section class="card tight"><span class="section-label">How it works</span><span class="small">1. Start, and a 4-digit code appears.<br>2. Staff open ShieldMate, tap Drills and type the code.<br>3. You move everyone through 4 moments.</span></section></aside></div>';
  }

  function lobbyHTML(v) {
    return '<div class="owner-head"><div><span class="small muted">' + esc(v.title) + '</span><h1>Waiting for the team</h1></div></div>' +
      '<div class="cols"><div class="col-main"><section class="card"><span class="section-label">Join code</span><span class="mono" style="font-size:56px;letter-spacing:0.12em;line-height:1">' + esc(v.code) + "</span>" +
      '<span class="ink-2">On their phones: ShieldMate → Drills → type this code.</span></section>' +
      '<button type="button" class="btn btn-primary btn-lg" style="align-self:flex-start" data-act="advance"' + (v.players.length < 2 ? " disabled" : "") + ">Begin moment 1</button>" +
      (v.players.length < 2 ? '<span class="small muted">Waiting for at least one person to join.</span>' : "") + "</div>" +
      '<aside class="col-side"><section class="list" aria-label="Joined"><h2 style="font-size:18px;margin:12px 0 4px">' + v.players.length + " joined</h2>" +
      v.players.map(p => '<div class="list-row"><span>' + esc(p.name) + (p.is_host ? " · host" : " · " + esc(p.role_label.toLowerCase())) + "</span>" + U.statusPill("green", "Ready") + "</div>").join("") + "</section></aside></div>";
  }

  function stepHTML(v) {
    const st = v.step;
    let mine = "";
    if (st.role_has_options) {
      const answered = !!st.my_answer;
      mine = '<span class="section-label">Your answer (owner\'s decision)</span><div class="options">' + st.my_options.map((o, i) => {
        if (!answered && v.status === "open") return '<button type="button" class="option" data-act="answer" data-step="' + esc(st.step_id) + '" data-opt="' + esc(o.option_id) + '"><span class="mark">' + "ABC"[i] + "</span><span>" + esc(o.text) + "</span></button>";
        const isMine = st.my_answer && st.my_answer.option_id === o.option_id;
        if (o.option_id === st.correct_option_id) return '<div class="option right"><span class="mark">' + U.ICONS.check + "</span><span>" + esc(o.text) + '<span class="tag">' + (isMine ? "Your answer · right" : "Best answer") + "</span></span></div>";
        if (isMine) return '<div class="option wrong"><span class="mark">' + U.ICONS.cross + "</span><span>" + esc(o.text) + '<span class="tag">Your answer</span></span></div>';
        return '<div class="option dim"><span class="mark">' + "ABC"[i] + "</span><span>" + esc(o.text) + "</span></div>";
      }).join("") + "</div>" +
        (st.my_answer ? '<section class="card tight"><span class="bold">' + (st.my_answer.correct ? "Right." : "Not quite.") + "</span><span>" + esc(st.my_answer.feedback) + "</span></section>" : "");
    } else {
      mine = '<section class="card tight"><span class="bold">Staff decide this one.</span><span class="small muted">Watch their answers come in on the right, then talk it through before moving on.</span></section>';
    }
    if (v.restore_trigger) {
      const r = v.restore && v.restore.result !== "NOT_TESTED" ? v.restore : null;
      mine += '<section class="card" aria-label="Restore check"><div class="row-between"><div class="stack-sm" style="gap:2px"><h2>Would your backup actually work?</h2><span class="small muted">This runs a real restore test on the clinic\'s backup.</span></div><span class="pill pill-sim">Simulated backup</span></div>' +
        (r && !testing
          ? '<div class="tinted row" style="background:var(--red-soft)"><span class="pill pill-red no-dot" style="background:var(--red);color:#fff">FAIL</span><span class="bold">Restoring now would have lost data.</span></div>' +
            '<div class="facts"><div class="fact"><span class="k">Fresh?</span><span class="v">' + Math.round(r.backup_age_hours / 24) + ' days old</span><span class="small muted">limit 1 day</span></div>' +
            '<div class="fact"><span class="k">Intact?</span><span class="v">' + r.files_ok + " of " + r.files_total + ' files</span><span class="small muted">' + (r.files_total - r.files_ok) + ' damaged</span></div>' +
            '<div class="fact"><span class="k">Out of reach?</span><span class="v">Always plugged in</span><span class="small muted">an attack can reach it</span></div></div>'
          : '<button type="button" class="btn btn-primary btn-lg" style="align-self:flex-start" data-act="test"' + (testing ? " disabled" : "") + ">" + (testing ? "Testing the backup…" : "Test the backup now") + "</button>") + "</section>";
    }
    const team = '<section class="list" aria-label="Team"><h2 style="font-size:18px;margin:12px 0 4px">Team · ' + v.answered_count + " of " + v.expected_count + " answered</h2>" +
      v.team.map(t => '<div class="list-row"><span>' + esc(t.name) + "</span>" +
        (!t.answered ? '<span class="small muted">Thinking…</span>' : t.correct === null ? U.statusPill("blue", "Answered") : U.statusPill(t.correct ? "green" : "red", t.correct ? "Right" : "Not quite")) + "</div>").join("") + "</section>";
    const nextLabel = v.status === "open" ? "Close this moment" : (v.step_index < v.steps_total - 1 ? "Next moment" : "Finish drill");
    return '<div class="owner-head"><div><span class="small muted">' + esc(v.title) + " · Moment " + (v.step_index + 1) + " of " + v.steps_total + " · " + esc(st.game_time) + "</span>" +
      '<h1 style="font-size:24px;line-height:1.3">' + esc(st.situation) + "</h1></div>" +
      '<span class="pill pill-amber no-dot">Practice · code <span class="mono">' + esc(v.code) + "</span></span></div>" +
      (st.impact.length ? '<div class="row" style="gap:6px">' + st.impact.map(i => '<span class="pill pill-sm ' + (i.state === "down" ? "pill-red" : "pill-amber") + ' no-dot">' + esc(i.label) + "</span>").join("") + "</div>" : "") +
      '<div class="cols"><div class="col-main">' + mine + '</div><aside class="col-side">' + team +
      '<button type="button" class="btn btn-dark btn-lg btn-block" data-act="advance">' + nextLabel + "</button>" +
      '<button type="button" class="btn btn-ghost" data-act="end">End drill now</button></aside></div>';
  }

  function resultsHTML(v) {
    const r = v.results;
    return '<div class="owner-head"><div><span class="small muted">' + esc(v.title) + '</span><h1>Team result: ' + r.team_right + " of " + r.team_total + "</h1></div></div>" +
      '<section class="card"><div class="table-wrap"><table class="simple"><thead><tr><th scope="col">Person</th><th scope="col">Result</th><th scope="col">Still to learn</th></tr></thead><tbody>' +
      r.rows.map(x => '<tr><th scope="row">' + esc(x.name) + "</th><td>" + x.right + " of " + x.total + "</td><td>" + esc(x.missed.length ? x.missed.join("; ") : "Nothing") + "</td></tr>").join("") +
      "</tbody></table></div></section>" +
      '<div class="row"><a class="btn btn-primary" href="owner-readiness.html">See readiness</a><button type="button" class="btn btn-soft" data-act="new">Start another drill</button></div>';
  }

  async function render() {
    U.mountOwnerNav("drills");
    if (!code) {
      const cur = await API.currentDrill();
      if (cur) { code = cur.code; history.replaceState(null, "", "owner-drill.html?code=" + code); }
    }
    if (!code) { if (document.activeElement && document.activeElement.id === "scenario") return; U.paint(main, startHTML()); return; }
    const pid = await ensureHost();
    const v = await API.drill(code, pid);
    if (v.status === "lobby") U.paint(main, lobbyHTML(v));
    else if (v.status === "finished") U.paint(main, resultsHTML(v));
    else U.paint(main, stepHTML(v));
  }

  const refresh = U.live(render);
  U.onAct({
    start: async () => {
      const sid = document.getElementById("scenario").value;
      if (sid !== "ransomware_clinic") { U.toast("Only the ransomware drill is playable in this build."); return; }
      const r = await API.createDrill(sid);
      code = r.code; U.session(hostKey(code), r.player_id);
      history.replaceState(null, "", "owner-drill.html?code=" + code);
      await refresh();
    },
    advance: async () => { await API.advance(code); await refresh(); },
    answer: async (el) => { await API.answer(code, await ensureHost(), el.dataset.step, el.dataset.opt); await refresh(); },
    end: async () => { await API.endDrill(code); await refresh(); },
    new: async () => { code = null; history.replaceState(null, "", "owner-drill.html"); main.__html = null; await refresh(); },
    test: async () => {
      testing = true; main.__html = null; await refresh();
      await new Promise(r => setTimeout(r, 1500));
      await API.runRestore();
      testing = false; main.__html = null; await refresh();
    }
  });
})();
