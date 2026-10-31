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

  function stepHTML(v) {
    const st = v.step;
    let html = progress(v) +
      '<article class="card"><p style="font-size:19px;font-weight:700;line-height:1.45">' + esc(st.situation) + "</p>" +
      (st.impact.length ? '<div class="row" style="gap:6px">' + st.impact.map(i => '<span class="pill pill-sm ' + (i.state === "down" ? "pill-red" : "pill-amber") + ' no-dot">' + esc(i.label) + "</span>").join("") + "</div>" : "") + "</article>";
    if (!st.role_has_options) {
      html += '<section class="card tight"><span class="bold">Dr. Rao is deciding this one</span><span class="small muted">This is the owner\'s call. Watch what happens; you\'ll see the answer when everyone has chosen.</span></section>';
    } else {
      const answered = !!st.my_answer;
      html += '<h2 style="font-size:18px;padding:0 4px">What do you do?</h2><div class="options" role="group" aria-label="Answers">' +
        st.my_options.map((o, i) => {
          const letter = "ABCD"[i];
          if (!answered && v.status === "open") return '<button type="button" class="option" data-act="answer" data-opt="' + esc(o.option_id) + '"><span class="mark">' + letter + "</span><span>" + esc(o.text) + "</span></button>";
          const mine = st.my_answer && st.my_answer.option_id === o.option_id;
          const right = st.correct_option_id === o.option_id;
          if (right) return '<div class="option right"><span class="mark">' + U.ICONS.check + "</span><span>" + esc(o.text) + '<span class="tag">' + (mine ? "Your answer · right" : "Best answer") + "</span></span></div>";
          if (mine) return '<div class="option wrong"><span class="mark">' + U.ICONS.cross + "</span><span>" + esc(o.text) + '<span class="tag">Your answer</span></span></div>';
          return '<div class="option dim"><span class="mark">' + letter + "</span><span>" + esc(o.text) + "</span></div>";
        }).join("") + "</div>";
      if (answered) html += '<section class="card tight" role="status"><span class="bold">' + (st.my_answer.correct ? "Right." : "Not quite.") + "</span><span>" + esc(st.my_answer.feedback) + "</span></section>";
      else if (v.status === "review") html += '<section class="card tight"><span class="bold">This moment closed before you answered.</span></section>';
    }
    const line = v.status === "review" ? "Everyone has chosen · Dr. Rao moves you on" : v.answered_count + " of " + v.expected_count + " answered · take your time";
    html += '<div class="card tight" style="flex-direction:row;justify-content:space-between;align-items:center"><span class="small">' + esc(line) + "</span></div>";
    return html;
  }

  function resultsHTML(v) {
    const me = v.results.rows.find(r => v.me && r.player_id === v.me.player_id);
    if (!me) return '<section class="card"><h1>Drill finished</h1></section>';
    return '<div class="stack-sm"><span class="small muted">' + esc(v.title) + " · " + esc(me.name) + "</span>" +
      '<h1 style="font-size:26px">You got ' + me.right + " of " + me.total + " right</h1>" +
      '<p class="ink-2">' + (me.right === me.total ? "Every call right. Well done." : "The first minutes are the hardest. That's exactly what practice is for.") + "</p></div>" +
      '<section class="list" aria-label="Your answers">' + me.per_step.map(s =>
        '<div class="list-row" style="justify-content:flex-start;gap:12px"><span class="check" style="width:26px;height:26px;border:0;background:' + (s.correct ? "var(--green)" : "var(--red)") + ';color:#fff">' + (s.correct ? U.ICONS.check : U.ICONS.cross) + "</span>" +
        '<span class="stack-sm" style="gap:0"><span class="bold">' + esc(s.game_time.replace(" AM", "")) + " · " + esc(s.short) + '</span><span class="small muted">' + esc(s.correct ? s.best_text : "You chose: " + s.chosen_text) + "</span></span></div>").join("") + "</section>" +
      (me.missed.length ? '<section class="card dark"><span class="section-label on-dark-muted">Remember these</span>' + me.missed.map((m, i) => '<span class="bold" style="font-size:18px">' + (i + 1) + ". " + esc(m) + "</span>").join("") + "</section>" : "") +
      '<section class="card tight"><span class="bold">Team result: ' + v.results.team_right + " of " + v.results.team_total + '</span><span class="small muted">Dr. Rao sees everyone\'s answers. Practise again in 30 days to check these stick.</span></section>' +
      '<a class="btn btn-dark btn-lg btn-block" href="staff.html?staff=' + esc(staffId) + '" data-act="leave">Back to Today</a>';
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
    catch (e) { U.session(playerKey(code), null); code = null; return render(); }
    document.title = "ShieldMate · " + v.title;
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
