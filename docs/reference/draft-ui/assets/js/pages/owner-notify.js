/* Owner phone: what an approval request looks like as a notification.
   A preview page: real push notifications come after the demo. */
(function () {
  "use strict";
  const U = window.SM_UI, API = window.SM_API;
  const esc = U.esc;
  const main = document.getElementById("main");

  function clock() {
    const d = new Date(U.nowMs());
    return '<div class="clock"><div style="color:#C9D6E8">' + esc(d.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })) + '</div><div class="t">' +
      esc(d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true }).replace(/\s?(am|pm)/i, "")) + "</div></div>";
  }
  function appRow(when) {
    return '<div class="row" style="gap:8px"><span class="app-icon">' + U.ICONS.shieldPlain.replace('class="icon"', 'class="icon" style="width:16px;height:16px"') + '</span><span class="small bold">ShieldMate</span><span class="tiny muted" style="margin-left:auto">' + esc(when) + "</span></div>";
  }

  async function render() {
    const [actions, alerts, notes] = await Promise.all([API.actions(), API.alerts("owner"), API.notifications()]);
    const act = actions.find(a => a.status === "proposed" || a.status === "escalated");
    const done = actions.find(a => a.status === "executed");
    let html = clock();
    if (act) {
      const alert = alerts.find(a => a.id === act.alert_id);
      html += '<article class="notif" aria-label="ShieldMate notification">' + appRow("now") +
        '<span class="bold" style="font-size:18px;line-height:1.3">Block an attacker on the reception computer?</span>' +
        '<span class="ink-2">Someone has tried ' + esc(alert ? alert.count : "several") + " wrong passwords. " +
        (act.standing_rule_on ? "Your standing rule blocks them at " + esc(U.time(act.decide_by)) + " if you don't answer." : "Answer by " + esc(U.time(act.decide_by)) + ".") + "</span>" +
        '<div class="btn-group"><button type="button" class="btn btn-primary" data-act="approve" data-id="' + esc(act.id) + '">Approve</button><a class="btn btn-soft" href="owner.html">Open</a></div>' +
        '<span class="tiny muted">After the demo, Approve will ask for your fingerprint or PIN.</span></article>';
    } else if (done) {
      html += '<article class="notif">' + appRow(U.time(done.decided_at)) + '<span class="bold">Blocked ' + esc(done.target_ip) + "</span>" +
        '<span class="ink-2">The reception computer is protected until ' + esc(U.time(done.expires_at)) + ".</span>" +
        '<a class="btn btn-soft" href="owner.html">Open ShieldMate</a></article>';
    } else {
      html += '<article class="notif faded"><span class="bold">No requests right now</span><span class="small" style="color:#C9D6E8">In Backstage, replay the password attack to see the approval request arrive here.</span>' +
        '<a class="btn btn-light" href="backstage.html">Open Backstage</a></article>';
    }
    notes.slice(0, 2).forEach(n => {
      html += '<article class="notif faded"><div class="row tiny" style="color:#C9D6E8"><span class="bold">ShieldMate</span><span style="margin-left:auto">' + esc(U.ago(n.at)) + "</span></div><span>" + esc(n.text) + "</span></article>";
    });
    html += '<a href="owner.html" style="color:#C9D6E8;text-align:center;margin-top:8px">Back to the owner screens</a>';
    U.paint(main, html);
  }

  const refresh = U.live(render);
  U.onAct({ approve: async (el) => { await API.approve(el.dataset.id); await refresh(); } });
})();
