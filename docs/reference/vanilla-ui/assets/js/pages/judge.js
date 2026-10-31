/* Judges' mini-drill: two questions on the judge's own phone. Off unless SM_CONFIG.judgeDrill. */
(function () {
  "use strict";
  const U = window.SM_UI, API = window.SM_API, esc = U.esc;
  const Q = window.SM_DATA.JUDGE_QUESTIONS;
  const main = document.getElementById("main");
  let jid = U.session("sm-judge-id");
  if (!jid) { jid = "j" + Math.random().toString(36).slice(2, 10); U.session("sm-judge-id", jid); }
  let stage = Number(U.session("sm-judge-stage") || 0); // 0 intro, 1..n question, n+1 done
  let picked = null; // {q, id} after answering, before moving on
  const setStage = (n) => { stage = n; picked = null; U.session("sm-judge-stage", String(n)); draw(); };

  function draw() {
    const inner = (h) => U.paint(main, '<div class="inner">' + h + "</div>");
    if (!window.SM_CONFIG.judgeDrill) {
      inner('<span class="game-badge" style="align-self:flex-start">PRACTICE</span><h1 style="color:#fff">The judges\' drill is switched off</h1><p style="color:var(--game-ink)">Turn on <code>judgeDrill</code> in config.js to use it.</p>');
      return;
    }
    if (stage === 0) {
      inner('<span class="game-badge" style="align-self:flex-start">PRACTICE · 30 SECONDS</span>' +
        '<h1 style="color:#fff;font-size:30px">You\'re the front desk now</h1>' +
        '<p style="color:var(--game-ink);font-size:18px">Two quick moments from a real ransomware morning. Pick what you\'d do. Your answers show up on the big screen, with no names.</p>' +
        '<button type="button" class="btn btn-lg btn-block" style="background:var(--gold);color:var(--game)" data-act="start">Start</button>');
      return;
    }
    if (stage > Q.length) {
      inner('<span class="game-badge" style="align-self:flex-start">DONE</span><h1 style="color:#fff">Thanks! Look up at the big screen.</h1>' +
        '<p style="color:var(--game-ink)">That\'s what ShieldMate does for clinic staff: short practice before the real thing.</p>');
      return;
    }
    const q = Q[stage - 1];
    let h = '<div class="row-between" style="color:var(--game-ink)"><span class="game-badge">MOMENT ' + stage + " / " + Q.length + "</span><span>no timer</span></div>" +
      '<h1 style="color:#fff;font-size:26px;line-height:1.3">' + esc(q.text) + "</h1>";
    if (!picked) {
      h += q.options.map((o, i) => '<button type="button" class="choice" data-act="pick" data-opt="' + esc(o.id) + '"><strong>' + "ABC"[i] + ".</strong> " + esc(o.text) + "</button>").join("");
    } else {
      const mine = q.options.find(o => o.id === picked);
      h += q.options.map((o, i) => '<div class="choice" style="cursor:default;' + (o.correct ? "background:var(--green-soft);outline:3px solid var(--green)" : o.id === picked ? "background:var(--red-soft);outline:3px solid var(--red)" : "opacity:.55") + '"><strong>' + "ABC"[i] + ".</strong> " + esc(o.text) + (o.correct ? " ✓" : "") + "</div>").join("") +
        '<section class="verdict slide-in" style="background:rgba(255,255,255,.08)" role="status"><span class="bold" style="font-size:18px">' + (mine.correct ? "Right call!" : "Not quite.") + '</span><span class="fb">' + esc(q.why || "") + "</span></section>" +
        '<button type="button" class="btn btn-lg btn-block" style="background:var(--gold);color:var(--game)" data-act="next">' + (stage < Q.length ? "Next moment" : "Finish") + "</button>";
    }
    inner(h);
  }

  U.onAct({
    start: () => setStage(1),
    pick: async (el) => {
      const q = Q[stage - 1];
      try { await API.judgeAnswer(jid, q.q, el.dataset.opt); picked = el.dataset.opt; draw(); }
      catch (e) { U.toast(e.message); }
    },
    next: () => setStage(stage + 1)
  });
  draw();
})();
