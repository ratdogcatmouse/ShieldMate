"""Live mode: real Wazuh alerts in, real blocks out (Wazuh Integration Guide).

Off unless ALERT_SOURCE=wazuh in backend/.env (copy .env.example). With it off,
ShieldMate runs on Backstage replays exactly as before.

What it does
- Polls the Wazuh indexer every WAZUH_POLL_SECONDS for rule 60204 (password
  guessing, becomes the alert card) and 60122 (each failed logon, used for the
  real count and to confirm a block worked). Only agents that are ShieldMate devices.
- Sends the block through the Wazuh API's active response (Plan A or Plan B),
  only after Dr. Rao approves or his standing rule acts. Nothing in an alert can trigger it.
- Confirms the block: if new failed logons from that address arrive in the 30 s
  after sending, the block is marked "failed" and the owner is told to call IT.
- Plan B only: lifts the block (delete) on Undo, on expiry, and on startup for any
  block that expired while ShieldMate was off.

Secrets come from .env and stay in this process: never returned by the API or logged.
"""
import ipaddress
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIRM_SECONDS = 30
GRACE_SECONDS = 5      # failed logons already in flight when the block lands don't count against it


def load_env(path=os.path.join(HERE, ".env")):
    """Tiny .env reader (KEY=value, # comments). Real environment variables win."""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line: continue
                k, v = line.split("=", 1)
                v = v.split(" #")[0].strip().strip('"').strip("'")
                out[k.strip()] = v
    except FileNotFoundError:
        pass
    out.update({k: v for k, v in os.environ.items() if k.startswith(("ALERT_", "ACTIONS", "WAZUH_", "NEVER_BLOCK", "SM_"))})
    return out


class Settings:
    def __init__(self, env):
        self.source = env.get("ALERT_SOURCE", "replay").lower()
        self.actions_on = env.get("ACTIONS", "on").lower() == "on"
        self.api_url = env.get("WAZUH_API_URL", "").rstrip("/")
        self.api_user = env.get("WAZUH_API_USER", "")
        self.api_password = env.get("WAZUH_API_PASSWORD", "")
        self.indexer_url = env.get("WAZUH_INDEXER_URL", "").rstrip("/")
        self.indexer_user = env.get("WAZUH_INDEXER_USER", "")
        self.indexer_password = env.get("WAZUH_INDEXER_PASSWORD", "")
        self.verify_tls = env.get("WAZUH_VERIFY_TLS", "true").lower() != "false"
        self.block_command = env.get("WAZUH_BLOCK_COMMAND", "!shieldmate-block.exe")
        self.poll_seconds = max(2, int(env.get("WAZUH_POLL_SECONDS", "5")))
        self.never_block = [x.strip() for x in env.get("NEVER_BLOCK", "").split(",") if x.strip()]
        # 60204 fires after `frequency` failures within `timeframe` seconds (your Wazuh rule file).
        self.freq_60204 = int(env.get("WAZUH_60204_FREQUENCY", "8"))
        self.window_min_60204 = max(1, round(int(env.get("WAZUH_60204_TIMEFRAME", "240")) / 60))

    @property
    def live(self): return self.source == "wazuh"

    @property
    def plan_b(self): return self.block_command != "!netsh.exe"


def parse_ts(ts):
    """Wazuh timestamps look like 2026-10-31T10:12:13.123+0000. Returns ms since 1970."""
    ts = ts.replace("Z", "+0000")
    if len(ts) > 5 and ts[-3] == ":": ts = ts[:-3] + ts[-2:]
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try: return int(datetime.strptime(ts, fmt).timestamp() * 1000)
        except ValueError: pass
    raise ValueError("bad timestamp " + ts)


def iso(ms): return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0000"


class WazuhClient:
    """The guide's client, unchanged in behaviour (two IP checks, token refresh on 401)."""

    def __init__(self, st):
        import httpx  # only needed in live mode: pip install httpx
        self.st = st
        self._token = None
        self._http = httpx.Client(verify=st.verify_tls, timeout=10)

    def search(self, since_ms, agent_names):
        body = {"size": 500, "sort": [{"timestamp": {"order": "asc"}}],
                "query": {"bool": {"filter": [
                    {"range": {"timestamp": {"gte": iso(since_ms)}}},   # gte + seen ids: same-timestamp alerts aren't skipped
                    {"terms": {"rule.id": ["60204", "60122"]}},
                    {"terms": {"agent.name": agent_names}}]}}}
        r = self._http.post(self.st.indexer_url + "/wazuh-alerts-4.x-*/_search", json=body,
                            auth=(self.st.indexer_user, self.st.indexer_password))
        r.raise_for_status()
        return [{"_id": h["_id"], **h["_source"]} for h in r.json()["hits"]["hits"]]

    def block_ip(self, agent_id, ip): self._run(agent_id, "add", ip)
    def unblock_ip(self, agent_id, ip): self._run(agent_id, "delete", ip)

    def agent_active(self, agent_id):
        r = self._api("GET", "/agents", params={"agents_list": agent_id})
        items = r.json()["data"]["affected_items"]
        return bool(items) and items[0]["status"] == "active"

    def _run(self, agent_id, action, ip):
        ip = str(ipaddress.IPv4Address(ip))                 # second check; the proposer checked first
        if ip in self.st.never_block: raise ValueError("refused: never-block address")
        if not str(agent_id).isdigit(): raise ValueError("refused: bad agent id")
        if self.st.plan_b:
            body = {"command": self.st.block_command, "arguments": [action, ip]}
        else:                                               # Plan A: netsh, add only (no early delete)
            if action != "add": return
            body = {"command": self.st.block_command, "arguments": [], "alert": {"data": {"srcip": ip}}}
        self._api("PUT", "/active-response", params={"agents_list": agent_id}, json=body)

    def _api(self, method, path, **kw):
        for attempt in (1, 2):
            if not self._token:
                r = self._http.post(self.st.api_url + "/security/user/authenticate?raw=true", auth=(self.st.api_user, self.st.api_password))
                r.raise_for_status()
                self._token = r.text.strip()
            r = self._http.request(method, self.st.api_url + path, headers={"Authorization": "Bearer " + self._token}, **kw)
            if r.status_code == 401 and attempt == 1:
                self._token = None
                continue
            r.raise_for_status()
            return r


class Live:
    """Glue between Wazuh and ShieldMate's state. `core` is backend.main (state, lock, add_alert, event, notify)."""

    def __init__(self, core, st):
        self.core, self.st = core, st
        self.client = WazuhClient(st) if st.live else None
        self.status = {"source": st.source, "ok": None, "last_poll": None, "error": None, "plan": ("B" if st.plan_b else "A") if st.live else None}
        self.seen = deque(maxlen=5000)
        self.seen_set = set()
        self.fails = deque(maxlen=5000)        # (ms, ip) of each 60122 failed logon
        self.since = int(time.time() * 1000)   # start from now: old lab alerts don't flood the demo

    # ----- called by main.py (inside the state lock: must not do network I/O) -----
    def on_block(self, s, a):
        if not (self.st.live and self.st.actions_on): return      # simulated, as before
        a.update(simulated=False, confirm="checking", sent_at=int(time.time() * 1000), attempts_since=0, failure=None)
        self._background(self._send, a["id"], "add")

    def on_unblock(self, s, a):
        if self.st.live and self.st.actions_on and not a.get("simulated") and self.st.plan_b:
            self._background(self._send, a["id"], "delete")

    def startup(self):
        """Plan B: lift blocks that expired while ShieldMate was off. Then start polling."""
        if not self.st.live: return
        with self.core.LOCK:
            stale = [dict(a) for a in self.core.STATE["actions"] if a["status"] == "expired" and not a.get("simulated") and not a.get("lifted")]
        for a in stale: self._background(self._send, a["id"], "delete")
        threading.Thread(target=self._poll_loop, daemon=True, name="wazuh-poller").start()

    # ----- background work (outside the lock) -----
    def _background(self, fn, *args): threading.Thread(target=fn, args=args, daemon=True).start()

    def _find_action(self, aid): return next((x for x in self.core.STATE["actions"] if x["id"] == aid), None)

    def _send(self, action_id, verb):
        with self.core.LOCK:
            a = self._find_action(action_id)
            if not a: return
            agent_id, ip = a.get("agent_id"), a["target_ip"]
        try:
            if not agent_id: raise ValueError("no Wazuh agent id on this alert")
            (self.client.block_ip if verb == "add" else self.client.unblock_ip)(agent_id, ip)
            err = None
        except Exception as e:
            err = type(e).__name__ + (": " + str(e)[:160] if str(e) else "")
        with self.core.LOCK:
            s = self.core.STATE
            a = self._find_action(action_id)
            if not a: return
            log = a.setdefault("calls", [])
            log.append({"at": int(time.time() * 1000), "verb": verb, "command": self.st.block_command, "ok": err is None, "error": err})  # no secrets
            if verb == "add" and err:
                a.update(status="failed", confirm="failed", failure="Wazuh couldn't send the block (" + err + ").")
                self.core.event(s, "Block on " + ip + " failed: " + err, "action")
                self.core.notify(s, "The block on " + ip + " didn't take effect. Call " + s["clinic"]["it_contact"]["name"] + ".")
            if verb == "delete" and not err: a["lifted"] = True
            self.core.save_state(s)

    def _poll_loop(self):
        while True:
            try:
                self.poll_once()
                self.status.update(ok=True, error=None, last_poll=int(time.time() * 1000))
            except Exception as e:
                self.status.update(ok=False, error=type(e).__name__, last_poll=int(time.time() * 1000))
            time.sleep(self.st.poll_seconds)

    def poll_once(self):
        with self.core.LOCK:
            agents = [d["agent"] for d in self.core.STATE["devices"]]
            ids = {d["agent"]: d["id"] for d in self.core.STATE["devices"]}
        hits = self.client.search(self.since, agents)
        new = [h for h in hits if h["_id"] not in self.seen_set]
        for h in new:
            self.seen.append(h["_id"]); self.seen_set.add(h["_id"])
        if len(self.seen_set) > 6000: self.seen_set = set(self.seen)
        if hits: self.since = max(self.since, max(parse_ts(h["timestamp"]) for h in hits))
        with self.core.LOCK:
            s = self.core.STATE
            changed = False
            for h in new:
                changed |= self._handle(s, h, ids)
            changed |= self._confirm(s)
            if changed: self.core.save_state(s)

    def _handle(self, s, h, ids):
        rule = str(h.get("rule", {}).get("id", ""))
        agent = h.get("agent", {}) or {}
        ev = ((h.get("data") or {}).get("win") or {}).get("eventdata") or {}
        ip = ev.get("ipAddress")
        ip = ip if ip and ip != "-" else None
        ts = parse_ts(h["timestamp"])
        if rule == "60122":
            if ip: self.fails.append((ts, ip))
            changed = False
            for a in s["actions"]:   # failed logons after a live block = the block isn't working
                if ip and a.get("target_ip") == ip and a["status"] == "executed" and not a.get("simulated") and ts > a.get("sent_at", 0) + GRACE_SECONDS * 1000:
                    a["attempts_since"] = a.get("attempts_since", 0) + 1
                    changed = True
            return changed
        if rule == "60204" and agent.get("name") in ids:
            window_ms = self.st.window_min_60204 * 60 * 1000
            count = sum(1 for t, x in self.fails if x == ip and ts - window_ms <= t <= ts) if ip else 0
            rec = {"rule_id": "60204", "agent_name": agent.get("name"), "agent_id": str(agent.get("id", "")),
                   "count": max(count, self.st.freq_60204), "window_minutes": self.st.window_min_60204, "live": True}
            if ip: rec["source_ip"] = ip
            if ev.get("targetUserName"): rec["username"] = str(ev["targetUserName"])[:200]   # shown verbatim, escaped; never sent to AI
            self.core.add_alert(s, rec)
            return True
        return False

    def _confirm(self, s):
        changed, t = False, int(time.time() * 1000)
        for a in s["actions"]:
            if a.get("confirm") != "checking" or a["status"] != "executed": continue
            if t < a["sent_at"] + CONFIRM_SECONDS * 1000: continue
            if a.get("attempts_since", 0) == 0:
                a["confirm"] = "confirmed"
                self.core.event(s, "Wazuh confirms: no new attempts from " + a["target_ip"] + " since the block", "action")
            else:
                n = a["attempts_since"]
                a.update(status="failed", confirm="failed",
                         failure=str(n) + (" wrong password" if n == 1 else " wrong passwords") + " from " + a["target_ip"] + " arrived after the block.")
                self.core.event(s, "Block on " + a["target_ip"] + " didn't take effect", "action")
                self.core.notify(s, "The block on " + a["target_ip"] + " didn't take effect. Call " + s["clinic"]["it_contact"]["name"] + ".")
            changed = True
        return changed
