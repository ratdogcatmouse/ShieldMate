/* Mission control: the projector screen judges watch while staff use their phones.
   Read-only. Shows the clinic floor plan, the attack, the "spotted → blocked" stopwatch,
   the CERT-In clock, the drill scoreboard, people and a live feed. */
(function () {
  "use strict";
  const U = window.SM_UI, API = window.SM_API;
  const esc = U.esc;
  const main = document.getElementById("main");
  const SHIELD = '<svg width="38" height="38" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5z" fill="var(--blue)"/><path d="m8.5 12 2.5 2.5 4.5-5" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const TONE = { green: "#22C55E", red: "#F04438", blue: "#38BDF8", amber: "#F5A524", grey: "#7C8BA5" };

  // Floor plan positions (viewBox 900 x 470)
  const ROOMS = [
    { id: "reception", label: "RECEPTION", x: 20, w: 280 },
    { id: "file-server", label: "SERVER CUPBOARD", x: 310, w: 280 },
    { id: "doctor", label: "DOCTOR'S ROOM", x: 600, w: 280 }
  ];
  const nodeAt = (id) => { const r = ROOMS.find(x => x.id === id); return { x: r.x + r.w / 2, y: 190 }; };

  function floorPlan(devices, attack) {
    let svg = '<svg viewBox="0 0 900 470" width="100%" role="img" aria-label="Clinic floor plan: ' +
      esc(devices.map(d => d.short + " " + d.status_label).join(", ")) + (attack ? ". " + attack.label : "") + '">';
    ROOMS.forEach(r => {
      svg += '<rect class="room" x="' + r.x + '" y="20" width="' + r.w + '" height="330" rx="18"/>' +
        '<text class="room-label" x="' + (r.x + 20) + '" y="52">' + r.label + "</text>";
    });
    // Attacker on the Wi-Fi, outside the rooms
    if (attack) {
      // Line comes in from the left edge of the target, clear of its labels
      const t = nodeAt(attack.target);
      const ax = 110, ay = 420, ex = t.x - 64, ey = t.y;
      const col = attack.blocked ? "#7C8BA5" : "#F04438";
      svg += '<path class="attack-line" d="M' + ax + " " + ay + " C 40 " + (ay - 40) + ", 30 " + ey + ", " + ex + " " + ey + '"' +
        (attack.blocked ? ' style="stroke:#7C8BA5;animation:none"' : "") + "/>" +
        '<circle cx="' + ax + '" cy="' + ay + '" r="22" fill="#3A1114" stroke="' + col + '" stroke-width="3"/>' +
        '<text x="' + ax + '" y="' + (ay + 6) + '" text-anchor="middle" fill="#FCA5A5" font-size="18" font-weight="700">?</text>' +
        '<text class="node-sub" x="' + (ax + 34) + '" y="' + (ay - 4) + '">Unknown device on Wi-Fi</text>' +
        '<text class="node-sub" x="' + (ax + 34) + '" y="' + (ay + 16) + '" style="font-family:var(--mono)">' + esc(attack.ip || "") + "</text>";
      if (attack.blocked) {
        svg += '<g transform="translate(22 300)"><path d="M22 0 4 7v14c0 12 8 21 18 25 10-4 18-13 18-25V7z" fill="#38BDF8" stroke="#0B1220" stroke-width="3"/><path d="m13 23 6 6 11-12" fill="none" stroke="#0B1220" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></g>' +
          '<text x="' + (ax + 34) + '" y="' + (ay + 40) + '" fill="#7DD3FC" font-size="18" font-weight="700" letter-spacing="1">BLOCKED · CAN\'T REACH THE CLINIC</text>';
      }
    }
    devices.forEach(d => {
      const p = nodeAt(d.id); if (!p) return;
      const hot = ["under_attack", "files_locked", "encrypted", "encrypting", "infected"].includes(d.status);
      if (hot) svg += '<circle class="pulse" cx="' + p.x + '" cy="' + p.y + '" r="56"/>';
      svg += '<rect class="node ' + esc(d.status) + '" x="' + (p.x - 62) + '" y="' + (p.y - 50) + '" width="124" height="100" rx="16"/>' +
        '<rect x="' + (p.x - 34) + '" y="' + (p.y - 30) + '" width="68" height="42" rx="5" fill="none" stroke="#E6EDF7" stroke-width="3"/>' +
        '<path d="M' + (p.x - 14) + " " + (p.y + 24) + "h28" + '" stroke="#E6EDF7" stroke-width="3" stroke-linecap="round"/>' +
        '<text class="node-label" x="' + p.x + '" y="' + (p.y + 86) + '" text-anchor="middle">' + esc(d.short) + "</text>" +
        '<text class="node-sub" x="' + p.x + '" y="' + (p.y + 108) + '" text-anchor="middle" style="fill:' + (TONE[d.tone] || "#A9B6CC") + '">' + esc(d.status_label) + "</text>";
    });
    return svg + "</svg>";
  }

  function stateOf(pw, act, rw, drill) {
    if (drill) return { cls: "drill", text: "PRACTICE DRILL RUNNING" };
    if (rw) return { cls: "attack", text: "RANSOMWARE ON THE FILE SERVER" };
    if (pw && act && act.status === "failed") return { cls: "attack", text: "BLOCK DIDN'T TAKE EFFECT" };
    if (pw && act && act.status === "executed") return { cls: "blocked", text: "ATTACK BLOCKED" };
    if (pw) return { cls: "attack", text: "ATTACK IN PROGRESS" };
    return { cls: "ok", text: "ALL QUIET" };
  }

  function clockPanel(pw, act, rw, devices) {
    if (rw && rw.certin_due_at) {
      return '<section class="mc-panel"><span class="mc-label">Report to CERT-In within 6 hours</span>' +
        '<span class="mc-big nowrap" style="color:#FCA5A5;font-size:52px" data-left="' + rw.certin_due_at + '"></span>' +
        '<span style="color:#A9B6CC">Spotted at ' + esc(U.time(rw.first_seen)) + " · the report is already drafted for Dr. Rao</span></section>";
    }
    if (pw) {
      const done = act && act.status === "executed";
      const how = !act ? "No block proposed" : done ? (act.decided_via === "standing_rule" || act.decided_via === "timeout" ? "Blocked by Dr. Rao's standing rule" : "Blocked: " + (act.decided_by || "Dr. Rao") + " tapped Approve") :
        act.status === "proposed" ? "Waiting for Dr. Rao to approve" : act.status === "failed" ? "The block didn't take effect: call IT" : "Block " + act.status;
      const failed = act && act.status === "failed";
      return '<section class="mc-panel"><span class="mc-label">' + (failed ? "Attack still going: block didn't take effect" : "Attack spotted → blocked") + "</span>" +
        '<span class="mc-big" style="color:' + (done ? "#7DD3FC" : "#FCA5A5") + '" data-stopwatch="' + pw.first_seen + '"' + (done && act.decided_at ? ' data-stop="' + act.decided_at + '"' : "") + "></span>" +
        '<span style="color:#A9B6CC">' + esc(how) + "</span>" +
        (act && act.status === "proposed" ? '<span style="color:#FCD34D">Auto-blocks in <strong data-countdown="' + act.decide_by + '"></strong> if nobody answers</span>' : "") + "</section>";
    }
    return '<section class="mc-panel"><span class="mc-label">Watching</span><span class="mc-big" style="color:#4ADE80">' + devices.filter(d => d.status === "ok").length + " / " + devices.length + '</span><span style="color:#A9B6CC">computers reporting · nothing needs anyone right now</span></section>';
  }

  function drillPanel(v) {
    const ts = v.team_score || { right: 0, total: 0 };
    let html = '<section class="mc-panel"><span class="mc-label">Drill · code ' + esc(v.code) + "</span>";
    if (v.status === "lobby") {
      html += '<span class="mc-big" style="color:#FCD34D;font-size:52px">Join: ' + esc(v.code) + "</span><span style=\"color:#A9B6CC\">" + v.players.length + " joined: " + esc(v.players.map(p => p.name).join(", ")) + "</span>";
    } else if (v.status === "finished") {
      const r = v.results;
      html += '<span class="mc-big" style="color:#FCD34D">' + r.team_right + " / " + r.team_total + "</span>" +
        (v.previous ? '<span style="color:#A9B6CC">' + esc(v.previous.label) + ": " + v.previous.team_right + " / " + v.previous.team_total + (v.previous.seeded ? " (sample data)" : "") + "</span>" : "");
    } else {
      html += '<span style="font-size:20px;font-weight:700">Moment ' + (v.step_index + 1) + " of " + v.steps_total + " · " + esc(v.step.game_time) + "</span>" +
        '<span style="color:#A9B6CC;font-size:17px">' + esc(v.step.short) + "</span>" +
        '<div class="score-row"><span>Answered</span><strong>' + v.answered_count + " / " + v.expected_count + "</strong></div>" +
        '<div class="score-row"><span>Team score so far</span><strong style="color:#FCD34D">' + ts.right + " / " + ts.total + "</strong></div>";
    }
    return html + "</section>";
  }

  function peoplePanel(staff, pw, act, drillView, itAlerts, itName) {
    let rows = staff.map(p => {
      let st = "All quiet", col = "#22C55E";
      if (drillView && drillView.status !== "finished") {
        const t = (drillView.team || []).find(x => x.name === p.name);
        if (drillView.status === "lobby") { const j = drillView.players.some(x => x.name === p.name); st = j ? "Joined" : "Not joined yet"; col = j ? "#22C55E" : "#7C8BA5"; }
        else if (!t) { st = "Not in this moment"; col = "#7C8BA5"; }
        else { st = t.answered ? "Answered" : "Choosing…"; col = t.answered ? "#22C55E" : "#FCD34D"; }
      } else if (pw) {
        if (p.role === "owner") { st = act ? (act.status === "proposed" ? "Deciding on the block" : act.status === "executed" ? "Block approved" : "Block " + act.status) : "Has the alert"; col = act && act.status === "executed" ? "#38BDF8" : "#FCD34D"; }
        else {
          const steps = (pw.staff_view.en || pw.staff_view[Object.keys(pw.staff_view)[0]]).steps;
          const d = steps.filter(x => x.done).length;
          st = d === steps.length ? "All " + steps.length + " steps done" : d + " of " + steps.length + " steps done"; col = d === steps.length ? "#22C55E" : "#FCD34D";
        }
      }
      return '<div class="mc-person"><span class="av">' + esc(p.name.replace("Dr. ", "").charAt(0)) + '</span><span class="stack-sm" style="gap:0"><strong>' + esc(p.name) + '</strong><span class="st">' + esc(p.role_label) + " · " + esc(st) + '</span></span><span class="dot" style="background:' + col + '"></span></div>';
    }).join("");
    // The clinic's IT contact, from whichever open incident they're handling
    const inc = [pw].concat(itAlerts || []).filter(Boolean).find(a => a.it && a.it.status !== "none");
    if (!drillView || drillView.status === "finished") {
      const it = inc ? inc.it : null;
      const st = !it ? ["Not needed right now", "#22C55E"] : it.status === "called" ? [it.called_by + " called · not picked up", "#F04438"] :
        it.status === "received" ? ["On it since " + U.time(it.received_at), "#FCD34D"] : ["Says it's fixed · Dr. Rao checking", "#38BDF8"];
      rows += '<div class="mc-person"><span class="av">IT</span><span class="stack-sm" style="gap:0"><strong>' + esc(itName) + '</strong><span class="st">IT support · ' + esc(st[0]) + '</span></span><span class="dot" style="background:' + st[1] + '"></span></div>';
    }
    return '<section class="mc-panel"><span class="mc-label">People</span>' + rows + "</section>";
  }

  function feedPanel(events) {
    return '<section class="mc-panel" style="flex:1;min-height:0"><span class="mc-label">Live feed</span><div class="mc-feed">' +
      (events.length ? events.slice(0, 5).map(e => '<div class="ev"><time>' + esc(U.time(e.at)) + "</time><span>" + esc(e.text) + "</span></div>").join("") : '<span style="color:#7C8BA5">Nothing yet.</span>') +
      "</div></section>";
  }

  async function render() {
    const [clinic, alerts, actions, events, cur] = await Promise.all([API.clinic(), API.alerts("owner"), API.actions(), API.activity(), API.currentDrill()]);
    const drillView = cur ? await API.drill(cur.code, "") : null;
    const pw = alerts.find(a => a.rule_id === "60204" && a.status !== "mine") || null;
    const rw = alerts.find(a => a.rule_id === "100201") || null;
    const act = pw ? actions.find(x => x.alert_id === pw.id) || null : null;
    let devices = clinic.devices;
    if (drillView && drillView.step && drillView.step.devices) {
      devices = devices.map(d => {
        const st = drillView.step.devices[d.id]; if (!st) return d;
        const meta = window.SM_DATA.DEVICE_STATUS[st];
        return Object.assign({}, d, { status: st, status_label: meta.label + " (practice)", tone: meta.tone });
      });
    }
    const attack = !drillView && pw ? { target: "reception", ip: pw.source_ip, blocked: !!(act && act.status === "executed"), label: (act && act.status === "executed") ? "Attack from " + pw.source_ip + " blocked" : "Attack from " + pw.source_ip } : null;
    const state = stateOf(pw, act, rw, drillView);

    U.paint(main,
      '<header class="mc-head"><div class="mc-title">' + SHIELD + '<div class="stack-sm" style="gap:0"><span class="name">ShieldMate</span><span class="sub">' + esc(clinic.clinic.name.toUpperCase()) + " · MISSION CONTROL</span></div></div>" +
      '<span class="mc-state ' + state.cls + '" role="status">' + esc(state.text) + "</span>" +
      '<span style="color:#7C8BA5;font-family:var(--mono)">' + esc(U.time(U.nowMs())) + (API.mode() === "mock" || !(clinic.live && clinic.live.source === "wazuh") ? " · recorded alerts" : clinic.live.ok === false ? " · Wazuh not reachable" : " · live from Wazuh") + "</span></header>" +
      '<div class="mc-grid"><section class="mc-panel"><span class="mc-label">' + (drillView ? "The clinic in the drill story" : "The clinic right now") + "</span>" + floorPlan(devices, attack) +
      '<div class="mc-tags"><span>' + (clinic.hidden_count || 0) + (clinic.hidden_count === 1 ? " routine event" : " routine events") + " filtered out</span><span>Plain-language cards in English · ಕನ್ನಡ · हिन्दी</span>" +
      (clinic.clinic.standing_rule && clinic.clinic.standing_rule.on ? "<span>Standing rule on: auto-block after " + clinic.clinic.approval_timeout_minutes + " min</span>" : "") + "</div></section>" +
      '<div class="mc-side">' + (drillView ? drillPanel(drillView) : clockPanel(pw, act, rw, devices)) + peoplePanel(clinic.staff, pw, act, drillView, alerts, clinic.clinic.it_contact.name) + feedPanel(events) + "</div></div>");
  }

  U.live(render);
})();
