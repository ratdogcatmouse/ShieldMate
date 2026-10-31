/* Owner: Readiness. Backup restore check, team practice, single point of failure. */
(function () {
  "use strict";
  const U = window.SM_UI, API = window.SM_API;
  const esc = U.esc;
  const main = document.getElementById("main");
  document.getElementById("mode").innerHTML = U.modeBanner();
  let testing = false;

  function summary(r) {
    const backupBad = r.restore.result === "FAIL";
    const untested = r.restore.result === "NOT_TESTED";
    const d = r.last_drill;
    const teamOk = d && d.team_total && d.team_right / d.team_total >= 0.7;
    let line, count = 0;
    if (untested) { line = "You haven't tested your backup yet. Start there."; count++; }
    else if (backupBad && d) line = teamOk ? "Your team knows most steps, but your backup wouldn't save you." : "Your team needs more practice, and your backup wouldn't save you.";
    else if (backupBad) line = "Your backup wouldn't save you. Fix it, then practise with the team.";
    else line = d ? "Your backup works and your team has practised." : "Your backup works. Next, practise with the team.";
    if (backupBad) count++;
    if (!d || !teamOk) count++;
    count++; // single point of failure in the seed data
    return '<section class="card dark" style="flex-direction:row;flex-wrap:wrap;align-items:center;justify-content:space-between"><div class="stack-sm grow" style="gap:4px;min-width:260px"><span class="on-dark-muted small">If ransomware hit today</span><span style="font-size:24px;font-weight:700;line-height:1.25">' + esc(line) + '</span></div><span class="on-dark-muted">' + count + " thing" + (count === 1 ? "" : "s") + " to fix</span></section>";
  }

  function backupCard(res) {
    const head = '<div class="row-between"><h2>Backup restore check</h2>' +
      (res.result === "FAIL" ? U.statusPill("red", "Not safe") : res.result === "PASS" ? U.statusPill("green", "Safe") : U.statusPill("grey", "Not tested")) + "</div>" +
      '<span class="pill pill-sim">Simulated backup</span>';
    let body;
    if (testing) body = '<p class="ink-2" role="status">Restoring 50 sample files into a separate folder and checking each one…</p>';
    else if (res.result === "NOT_TESTED") body = '<p class="ink-2">A green "backup succeeded" message isn\'t proof. This restores sample files and checks each one is intact.</p>';
    else {
      const days = Math.round(res.backup_age_hours / 24);
      const yn = (ok) => '<span class="bold" style="color:' + (ok ? "var(--green-ink)" : "var(--red-ink)") + '">' + (ok ? "Yes" : "No") + "</span>";
      const failed = res.failed_files || [];
      body = '<div class="list" style="padding:0;background:transparent">' +
        '<div class="list-row"><span><strong>Fresh?</strong> ' + days + " days old, limit " + Math.round(res.limit_hours / 24) + " day</span>" + yn(res.backup_age_hours <= res.limit_hours) + "</div>" +
        '<div class="list-row"><span><strong>Intact?</strong> ' + res.files_ok + " of " + res.files_total + " files match</span>" + yn(res.files_ok === res.files_total) + "</div>" +
        '<div class="list-row"><span><strong>Out of reach?</strong> ' + (res.exposed ? "Drive always plugged in" : "Kept unplugged") + "</span>" + yn(!res.exposed) + "</div></div>" +
        (failed.length ? '<details class="log"><summary>The ' + failed.length + " damaged files</summary><div class=\"body\">" + failed.map(f => '<div class="log-value">' + esc(f) + "</div>").join("") + "</div></details>" : "") +
        (res.fixes && res.fixes.length ? '<div class="tinted"><strong>Fix:</strong> ' + res.fixes.map(esc).join(" ") + "</div>" : "");
    }
    return '<section class="card" id="backup">' + head + body +
      '<div class="row"><button type="button" class="btn btn-primary" data-act="test"' + (testing ? " disabled" : "") + ">" + (testing ? "Testing…" : res.result === "NOT_TESTED" ? "Test the backup" : "Test again") + "</button>" +
      (res.finished_at && !testing ? '<span class="small muted">Last test ' + esc(U.time(res.finished_at)) + " · took " + res.duration_seconds + " s</span>" : "") + "</div></section>";
  }

  function teamCard(d) {
    if (!d) {
      return '<section class="card"><div class="row-between"><h2>Team practice</h2>' + U.statusPill("grey", "No drill yet") + '</div><p class="ink-2">Run a 6-minute ransomware drill with your team on their phones.</p>' +
        '<button type="button" class="btn btn-primary" style="align-self:flex-start" data-act="startdrill">Start a team drill</button></section>';
    }
    const ok = d.team_right / d.team_total >= 0.7;
    return '<section class="card span-2"><div class="row-between"><h2>Team practice</h2>' + U.statusPill(ok ? "amber" : "red", ok ? "Mostly ready" : "Needs practice") + "</div>" +
      '<span class="small muted">' + esc(d.title) + " · " + esc(U.time(d.finished_at)) + " · team " + d.team_right + " of " + d.team_total + "</span>" +
      '<div class="table-wrap"><table class="simple"><thead><tr><th scope="col">Person</th><th scope="col">Result</th><th scope="col">Still to learn</th></tr></thead><tbody>' +
      d.rows.map(r => '<tr><th scope="row">' + esc(r.name) + "</th><td>" + r.right + " of " + r.total + "</td><td" + (r.missed.length ? "" : ' class="muted"') + ">" + esc(r.missed.length ? r.missed.join("; ") : "Nothing") + "</td></tr>").join("") +
      "</tbody></table></div>" +
      '<button type="button" class="btn btn-primary" style="align-self:flex-start" data-act="startdrill">Start another drill</button></section>';
  }

  function awayCard(staff) {
    const restorers = staff.filter(p => p.can_restore).map(p => p.name);
    const gap = restorers.length < 2;
    return '<section class="card"><div class="row-between"><h2>If you\'re away</h2>' + U.statusPill(gap ? "amber" : "green", gap ? "Gap" : "Covered") + "</div>" +
      '<p class="ink-2">' + (gap ? "Only " + esc(restorers.join(", ") || "nobody") + " can restore backups or approve a block. If you're with a patient or on leave, nobody can." : "Two people can restore backups and approve blocks.") + "</p>" +
      (gap ? '<span class="small muted">Choosing a backup person is part of setup (after the demo).</span>' : "") + "</section>";
  }

  async function render() {
    const r = await API.readiness();
    U.mountOwnerNav("readiness");
    U.paint(main,
      '<div class="owner-head"><div><span class="owner-mobile-head">Sunrise Family Clinic</span><h1>Readiness</h1></div></div>' +
      summary(r) + '<div class="grid-auto">' + backupCard(r.restore) + teamCard(r.last_drill) + awayCard(r.staff) + "</div>");
  }

  const refresh = U.live(render);
  U.onAct({
    test: async () => {
      testing = true; main.__html = null; await refresh();
      await new Promise(res => setTimeout(res, 1500));
      await API.runRestore();
      testing = false; main.__html = null; await refresh();
    },
    startdrill: async () => {
      const r = await API.createDrill("ransomware_clinic");
      U.session("sm-host-" + r.code, r.player_id);
      location.href = "owner-drill.html?code=" + r.code;
    }
  });
})();
