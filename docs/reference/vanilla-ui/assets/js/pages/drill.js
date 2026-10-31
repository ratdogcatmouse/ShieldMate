/* Staff phone: join a drill, wait in the lobby, answer each moment, see results. */
(function () {
  "use strict";
  const U = window.SM_UI, API = window.SM_API;
  const esc = U.esc;
  const staffId = U.param("staff");
  if (!staffId) { location.replace("index.html"); return; }
  let code = U.param("code");
  const main = document.getElementById("main");
  document.getElementById("tabs").innerHTML = U.staffTabs("drills", staffId);
  let person = null, typedCode = null;

  const playerKey = (c) => "sm-player-" + c + "-" + staffId;
  const playerId = () => (code ? U.session(playerKey(code)) : null);

  function joinHTML(suggested) {
    const value = typedCode !== null ? typedCode : (code || (suggested ? suggested.code : ""));
    return '<div class="stack-sm"><h1 style="font-size:26px">Join the team drill</h1>' +
      '<p class="ink-2">Type the 4-digit code shown on Dr. Rao\'s screen.</p></div>' +
      '<form id="join" class="stack-sm" novalidate>' +
      '<label class="field-label" for="code">Drill code</label>' +
      '<input id="code" class="code-input" inputmode="numeric" pattern="[0-9]*" maxlength="4" autocomplete="off" value="' + esc(value) + '">' +
      '<button class="btn btn-primary btn-lg btn-block" type="submit">Join as ' + esc(person.name) + "</button></form>" +
      (suggested ? '<p class="small muted">A drill is running now: ' + esc(suggested.title) + "</p>" : '<p class="small muted">No drill is running yet. Dr. Rao starts one from the laptop.</p>') +
      '<a class="btn btn-ghost" href="index.html">Not ' + esc(person.name) + "? Switch person</a>";
  }

  function lobbyHTML(v) {
    return '<div class="stack-sm"><span class="small bold" style="color:var(--green-ink)">You\'re in · code ' + esc(v.code) + "</span>" +
      '<h1 style="font-size:26px">' + esc(v.title) + "</h1>" +
      '<p class="ink-2">Waiting for Dr. Rao to start. Keep this screen open.</p></div>' +
      '<section class="list" aria-label="Who has joined">' + v.players.map(p =>
        '<div class="list-row"><span' + (v.me && p.player_id === v.me.player_id ? ' class="bold"' : "") + ">" + esc(p.name) + " · " + esc(p.is_host ? "host" : p.role_label.toLowerCase()) + (v.me && p.player_id === v.me.player_id ? " (you)" : "") + '</span><span class="small bold" style="color:var(--green-ink)">Ready</span></div>').join("") + "</section>" +
      '<section class="card tight"><span class="section-label">What to expect</span><ul style="margin:0;padding-left:20px" class="stack-sm">' +
      "<li>" + v.steps_total + " moments in one morning at the clinic</li><li>Pick what you would do; you'll see why straight away</li><li>No timer. Nobody else sees your answer until everyone has chosen</li></ul></section>";
  }

  function progress(v) {
    let segs = "";
    for (let i = 0; i < v.steps_total; i++) segs += "<span" + (i <= v.step_index ? ' class="on"' : "") + "></span>";
    return '<div class="stack-sm"><div class="row-between small"><span class="bold">Moment ' + (v.step_index + 1) + " of " + v.steps_total + " · " + esc(v.step.phase_label) + '</span><span class="muted">' + esc(v.step.game_time) + ' at the clinic</span></div>' +
      '<div class="progress-segs" role="img" aria-label="Moment ' + (v.step_index + 1) + " of " + v.steps_total + '" style="grid-template-columns:repeat(' + v.steps_total + ',minmax(0,1fr))">' + segs + "</div></div>";
  }

  // ---------- Game-style moment ----------
  function teamChips(v) {
    return '<div class="chips"><span class="small muted">Team</span>' + v.team.map(t => {
      const cls = t.answered ? (t.correct === true ? "ok" : t.correct === false ? "no" : "done") : "wait";
      const me = v.me && t.name === v.me.name;
      return '<span class="chip"><span class="av ' + cls + '">' + esc(t.name.charAt(0)) + "</span>" + esc(me ? "you" : t.name) + (t.answered ? "" : " …") + "</span>";
    }).join("") + "</div>";
  }

  function stepHTML(v) {
    const st = v.step;
    let segs = "";
    for (let i = 0; i < v.steps_total; i++) segs += "<span" + (i <= v.step_index ? ' class="on"' : "") + "></span>";
    const ts = v.team_score || { right: 0, total: 0 };
    let html = '<div class="game-top">' +
      '<div class="row-between"><span class="game-badge">MOMENT ' + (v.step_index + 1) + " / " + v.steps_total + "</span><span>Team score <strong style=\"color:#fff;font-size:18px\">" + ts.right + " / " + ts.total + "</strong></span></div>" +
      '<div class="progress-segs" role="img" aria-label="Moment ' + (v.step_index + 1) + " of " + v.steps_total + '" style="grid-template-columns:repeat(' + v.steps_total + ',minmax(0,1fr))">' + segs + "</div>" +
      '<span>' + esc(st.game_time) + " at the clinic · " + esc(st.phase_label) + "</span></div>" +
      ((window.SM_SCENES && window.SM_SCENES[st.step_id]) || "") +
      '<div class="game-sheet">' +
      '<p style="font-size:19px;font-weight:700;line-height:1.4">' + esc(st.situation) + "</p>" +
      (st.impact.length ? '<div class="row" style="gap:6px">' + st.impact.map(i => '<span class="pill pill-sm ' + (i.state === "down" ? "pill-red" : "pill-amber") + ' no-dot">' + esc(i.label) + "</span>").join("") + "</div>" : "");
    if (!st.role_has_options) {
      html += '<section class="verdict"><span class="bold">Dr. Rao is deciding this one</span><span class="fb">It\'s the owner\'s call. Watch the big screen; you\'ll see the answer when everyone has chosen.</span></section>';
    } else {
      const answered = !!st.my_answer;
      html += '<div class="options game-options" role="group" aria-label="Answers">' +
        st.my_options.map((o, i) => {
          const letter = "ABCD"[i];
          if (!answered && v.status === "open") return '<button type="button" class="option" data-act="answer" data-opt="' + esc(o.option_id) + '"><span class="mark">' + letter + "</span><span>" + esc(o.text) + "</span></button>";
          const mine = st.my_answer && st.my_answer.option_id === o.option_id;
          const right = st.correct_option_id === o.option_id;
          if (right) return '<div class="option right"><span class="mark">' + U.ICONS.check + "</span><span>" + esc(o.text) + '<span class="tag">' + (mine ? "Your answer · right" : "Best answer") + "</span></span></div>";
          if (mine) return '<div class="option wrong"><span class="mark">' + U.ICONS.cross + "</span><span>" + esc(o.text) + '<span class="tag">Your answer</span></span></div>';
          return '<div class="option dim"><span class="mark">' + letter + "</span><span>" + esc(o.text) + "</span></div>";
        }).join("") + "</div>";
      if (answered) html += '<section class="verdict slide-in" role="status"><span class="bold" style="font-size:18px">' + (st.my_answer.correct ? "Nice call! +1 for the team" : "Close, but not quite.") + '</span><span class="fb">' + esc(st.my_answer.feedback) + "</span></section>";
      else if (v.status === "review") html += '<section class="verdict"><span class="bold">This moment closed before you answered.</span></section>';
    }
    html += teamChips(v) + '<span class="small muted">' + esc(v.status === "review" ? "Everyone has chosen · Dr. Rao moves you on" : v.answered_count + " of " + v.expected_count + " answered · no timer, take your time") + "</span></div>";
    return html;
  }

  // ---------- Game-style results: ring + retest reveal ----------
  function ring(right, total, label) {
    const len = 415, frac = total ? right / total : 0;
    return '<svg class="ring" viewBox="0 0 160 160" width="170" height="170" role="img" aria-label="' + esc(label) + '">' +
      '<circle cx="80" cy="80" r="66" fill="none" stroke="var(--game-2)" stroke-width="16"/>' +
      '<circle class="arc" cx="80" cy="80" r="66" fill="none" stroke="var(--gold)" stroke-width="16" stroke-linecap="round" stroke-dasharray="' + len + '" stroke-dashoffset="' + Math.round(len * (1 - frac)) + '" transform="rotate(-90 80 80)"/>' +
      '<text x="80" y="82" text-anchor="middle" fill="#fff" font-size="38" font-weight="700" font-family="var(--display)">' + right + "/" + total + "</text>" +
      '<text x="80" y="106" text-anchor="middle" fill="var(--game-ink)" font-size="13">you</text></svg>';
  }
  function resultsHTML(v) {
    const me = v.results.rows.find(r => v.me && r.player_id === v.me.player_id);
    if (!me) return '<div class="game-sheet"><h1>Drill finished</h1></div>';
    const prev = v.previous, team = v.results;
    const prevMine = prev && prev.people[me.staff_id];
    const better = prev ? team.team_right - prev.team_right : 0;
    const maxH = 100, h = (r, t) => Math.max(8, Math.round(maxH * (t ? r / t : 0)));
    return '<div class="game-top" style="align-items:center;text-align:center;padding-bottom:18px">' + ring(me.right, me.total, "You got " + me.right + " of " + me.total) +
      '<span style="font-family:var(--display);font-size:26px;font-weight:700">' + (prev && better > 0 ? "Your team got better" : me.right === me.total ? "Every call right" : "Practice done") + "</span>" +
      '<span style="color:var(--game-ink)">' + (prev && better > 0 ? better + " more right calls than " + esc(prev.label.toLowerCase()) : "Team " + team.team_right + " of " + team.team_total) + "</span></div>" +
      '<div class="game-sheet">' +
      (prev ? '<section class="card tight"><span class="section-label">' + esc(prev.label) + ' vs today · team</span>' +
        '<div class="bars"><div class="bar"><span>' + prev.team_right + "/" + prev.team_total + '</span><i style="height:' + h(prev.team_right, prev.team_total) + 'px"></i></div>' +
        '<div class="bar now"><span style="color:var(--blue)">' + team.team_right + "/" + team.team_total + '</span><i style="height:' + h(team.team_right, team.team_total) + 'px"></i></div></div>' +
        '<div class="row-between small muted" style="justify-content:space-around"><span>' + esc(prev.label) + (prev.seeded ? " (sample data)" : "") + "</span><span>Today</span></div>" +
        (prevMine ? '<span class="small">You: ' + prevMine[0] + "/" + prevMine[1] + " → " + me.right + "/" + me.total + "</span>" : "") + "</section>" : "") +
      '<section class="list" aria-label="Your answers">' + me.per_step.map(s =>
        '<div class="list-row" style="justify-content:flex-start;gap:12px"><span class="check" style="width:26px;height:26px;border:0;background:' + (s.correct ? "var(--green)" : "var(--red)") + ';color:#fff">' + (s.correct ? U.ICONS.check : U.ICONS.cross) + "</span>" +
        '<span class="stack-sm" style="gap:0"><span class="bold">' + esc(s.game_time.replace(" AM", "")) + " · " + esc(s.short) + '</span><span class="small muted">' + esc(s.correct ? s.best_text : "You chose: " + s.chosen_text) + "</span></span></div>").join("") + "</section>" +
      (me.missed.length ? '<section class="verdict"><span class="section-label" style="color:var(--game-ink)">Remember these</span>' + me.missed.map((m, i) => '<span class="bold" style="font-size:18px">' + (i + 1) + ". " + esc(m) + "</span>").join("") + "</section>" : "") +
      '<a class="btn btn-dark btn-lg btn-block" href="staff.html?staff=' + esc(staffId) + '" data-act="leave">Back to Today</a></div>';
  }

  async function render() {
    if (!person) { const c = await API.clinic(); person = c.staff.find(p => p.id === staffId); if (!person) { location.replace("index.html"); return; } }
    const pid = playerId();
    if (!code || !pid) {
      const cur = await API.currentDrill();
      if (document.activeElement && document.activeElement.id === "code") return; // don't disturb typing
      U.paint(main, joinHTML(cur));
      return;
    }
    let v;
    try { v = await API.drill(code, pid); }
    catch (e) {
      if (e.status !== 404) throw e; // Wi-Fi blip: keep the screen, try again on the next poll
      U.session(playerKey(code), null); code = null; history.replaceState(null, "", "drill.html?staff=" + encodeURIComponent(staffId));
      document.body.classList.remove("game-mode"); document.getElementById("banner").textContent = "PRACTICE · not a real attack";
      return render();
    }
    document.title = "ShieldMate · " + v.title;
    const gameMode = v.status !== "lobby";
    document.body.classList.toggle("game-mode", gameMode);
    if (v.status === "lobby") U.paint(main, lobbyHTML(v));
    else if (v.status === "finished") { document.getElementById("banner").textContent = "PRACTICE · finished"; U.paint(main, resultsHTML(v)); }
    else U.paint(main, stepHTML(v));
  }

  main.addEventListener("input", (e) => { if (e.target.id === "code") typedCode = e.target.value.replace(/\D/g, "").slice(0, 4); });
  main.addEventListener("submit", async (e) => {
    if (e.target.id !== "join") return;
    e.preventDefault();
    const c = (document.getElementById("code").value || "").replace(/\D/g, "");
    if (c.length !== 4) { U.toast("The code has 4 digits."); return; }
    try {
      const r = await API.joinDrill(c, staffId);
      code = c; U.session(playerKey(c), r.player_id); typedCode = null;
      history.replaceState(null, "", "drill.html?staff=" + encodeURIComponent(staffId) + "&code=" + c);
      document.activeElement.blur(); main.__html = null; await refresh();
    } catch (err) { U.toast(err.message); }
  });

  const refresh = U.live(render);
  U.onAct({
    answer: async (el) => {
      const v = await API.drill(code, playerId());
      await API.answer(code, playerId(), v.step.step_id, el.dataset.opt);
      await refresh();
    },
    leave: async () => { location.href = "staff.html?staff=" + encodeURIComponent(staffId); }
  });
})();
