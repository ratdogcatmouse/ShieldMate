/* Judges' results for the projector: live bars, correct answer hidden until "Reveal". */
(function () {
  "use strict";
  const U = window.SM_UI, API = window.SM_API, esc = U.esc;
  const main = document.getElementById("main");
  let revealed = U.session("sm-judge-reveal") === "1";
  const joinUrl = location.href.replace(/judge-tally\.html.*$/, "judge.html");

  async function render() {
    if (!window.SM_CONFIG.judgeDrill) { U.paint(main, '<h1 style="color:#fff">The judges\' drill is switched off</h1><p style="color:var(--game-ink)">Turn on <code>judgeDrill</code> in config.js.</p>'); return; }
    const t = await API.judgeTally();
    U.paint(main,
      '<div class="row-between" style="align-items:flex-end;gap:16px;flex-wrap:wrap"><div class="stack-sm"><span class="game-badge" style="align-self:flex-start">JUDGES\' DRILL</span>' +
      '<h1 style="color:#fff;font-size:34px;font-family:var(--display)">You\'re the front desk now</h1>' +
      '<span style="color:var(--game-ink);font-size:18px">Open on your phone: <strong style="color:#fff;font-family:var(--mono)">' + esc(joinUrl) + "</strong></span></div>" +
      '<div class="stack-sm" style="align-items:flex-end"><span style="font-size:44px;font-weight:700;font-family:var(--display)">' + t.joined + '</span><span style="color:var(--game-ink)">judges answered</span></div></div>' +
      t.questions.map((q, qi) => {
        const total = q.options.reduce((n, o) => n + o.count, 0) || 1;
        return '<section class="q"><span style="font-size:22px;font-weight:700">' + (qi + 1) + ". " + esc(q.text) + "</span>" +
          q.options.map((o, i) => {
            const pct = Math.round(100 * o.count / total);
            const col = revealed ? (o.correct ? "var(--green)" : "#8A97A8") : "var(--gold)";
            return '<div class="stack-sm" style="gap:4px"><div class="row-between" style="font-size:18px"><span>' + "ABC"[i] + ". " + esc(o.text) + (revealed && o.correct ? " ✓ best answer" : "") + "</span><strong>" + o.count + "</strong></div>" +
              '<div class="track"><div class="fill" style="width:' + pct + "%;background:" + col + '"></div></div></div>';
          }).join("") + "</section>";
      }).join("") +
      '<div class="row"><button type="button" class="btn btn-lg" style="background:var(--gold);color:var(--game)" data-act="reveal">' + (revealed ? "Hide answers" : "Reveal the right answers") + "</button>" +
      '<a class="btn btn-lg btn-soft" href="mission.html">Back to mission control</a></div>');
  }
  U.onAct({ reveal: () => { revealed = !revealed; U.session("sm-judge-reveal", revealed ? "1" : "0"); main.__html = null; render(); } });
  U.live(render);
})();
