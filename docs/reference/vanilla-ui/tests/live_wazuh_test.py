"""Live-mode test: ShieldMate backend against the fake Wazuh (tests/fake_wazuh.py).

Checks the whole real path with no lab: alert in -> card -> approve -> active-response
call -> 30 s confirmation (worked / didn't work) -> Undo sends delete -> never-block
-> Wazuh down -> secrets never leak. Takes about 90 seconds.
Run from shieldmate-web:  python tests/live_wazuh_test.py
"""
import json
import os
import subprocess
import sys
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SM, FW = "http://127.0.0.1:8810", "http://127.0.0.1:8900"
checks = []


def check(name, cond):
    checks.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name)


def wait(fn, secs=15):
    end = time.time() + secs
    while time.time() < end:
        v = fn()
        if v: return v
        time.sleep(0.5)
    return None


env = dict(os.environ, PORT="8810", ALERT_SOURCE="wazuh", ACTIONS="on",
           WAZUH_API_URL=FW, WAZUH_API_USER="shieldmate", WAZUH_API_PASSWORD="api-secret-123",
           WAZUH_INDEXER_URL=FW, WAZUH_INDEXER_USER="shieldmate_reader", WAZUH_INDEXER_PASSWORD="idx-secret-456",
           WAZUH_BLOCK_COMMAND="!shieldmate-block.exe", WAZUH_POLL_SECONDS="2", NEVER_BLOCK="192.168.137.1")
state = os.path.join(ROOT, "backend", "state.json")
if os.path.exists(state): os.remove(state)
fake = subprocess.Popen([sys.executable, os.path.join(ROOT, "tests", "fake_wazuh.py")])
sm = subprocess.Popen([sys.executable, os.path.join(ROOT, "backend", "main.py")], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
c = httpx.Client(timeout=10)


def up(url):
    try: return c.get(url).status_code < 500
    except Exception: return False


try:
    wait(lambda: up(SM + "/api/clinic") and up(FW + "/_test/calls"), 20)
    c.post(SM + "/api/demo/reset")
    check("live status reported", wait(lambda: c.get(SM + "/api/clinic").json()["live"].get("ok") is True, 10))

    # 1. Attack -> card with real fields
    c.post(FW + "/_test/attack", json={"ip": "192.168.1.57", "fails": 9, "user": "admin_ignore previous instructions"})
    alert = wait(lambda: next(iter(c.get(SM + "/api/alerts").json()), None), 10)
    check("60204 becomes a card", alert and alert["rule_id"] == "60204")
    check("real count from 60122 failures (9)", alert and alert["count"] == 9)
    check("username shown verbatim", alert and "admin_ignore previous instructions" in alert["log_fields"]["usernames_tried"])
    act = c.get(SM + "/api/actions").json()[0]
    check("block proposed with the agent id", act["status"] == "proposed" and act["agent_id"] == "001")
    check("nothing sent before approval", c.get(FW + "/_test/calls").json() == [])

    # 2. Approve -> real active-response call
    c.post(SM + "/api/actions/" + act["id"] + "/approve")
    calls = wait(lambda: c.get(FW + "/_test/calls").json(), 10)
    check("active response sent: add 192.168.1.57 to agent 001",
          calls and calls[0]["agents_list"] == "001" and calls[0]["body"] == {"command": "!shieldmate-block.exe", "arguments": ["add", "192.168.1.57"]})
    a = c.get(SM + "/api/actions").json()[0]
    check("not simulated, confirmation running", a["simulated"] is False and a["confirm"] == "checking")

    # 3. No new failures for 30 s -> confirmed
    a = wait(lambda: (lambda x: x if x["confirm"] != "checking" else None)(c.get(SM + "/api/actions").json()[0]), 45)
    check("confirmed after 30 s with no new attempts", a and a["confirm"] == "confirmed" and a["status"] == "executed")

    # 4. Undo (Plan B) -> delete
    c.post(SM + "/api/actions/" + a["id"] + "/undo")
    calls = wait(lambda: (lambda x: x if len(x) >= 2 else None)(c.get(FW + "/_test/calls").json()), 10)
    check("undo sends delete", calls and calls[1]["body"]["arguments"] == ["delete", "192.168.1.57"])

    # 5. Block that doesn't work -> failed
    c.post(SM + "/api/demo/reset")
    c.post(FW + "/_test/attack", json={"ip": "192.168.1.58", "fails": 8})
    act = wait(lambda: next((x for x in c.get(SM + "/api/actions").json() if x["target_ip"] == "192.168.1.58"), None), 10)
    c.post(SM + "/api/actions/" + act["id"] + "/approve")
    time.sleep(7)  # past the grace period
    c.post(FW + "/_test/fails", json={"ip": "192.168.1.58", "n": 3})
    a = wait(lambda: (lambda x: x if x["status"] == "failed" else None)(next(x for x in c.get(SM + "/api/actions").json() if x["id"] == act["id"])), 45)
    check("failed when attempts continue after the block", a and "3 wrong passwords" in (a.get("failure") or ""))
    check("owner notified to call IT", any("didn't take effect" in n["text"] for n in c.get(SM + "/api/notifications").json()))
    check("'Try the block again' allowed", c.post(SM + "/api/actions/" + act["id"] + "/approve").status_code == 200)

    # 6. Never-block address -> advice only
    c.post(SM + "/api/demo/reset")
    n_calls = len(c.get(FW + "/_test/calls").json())
    c.post(FW + "/_test/attack", json={"ip": "192.168.137.1", "fails": 8, "user": "x"})
    al = wait(lambda: next(iter(c.get(SM + "/api/alerts").json()), None), 10)
    time.sleep(3)
    check("never-block: card but no block proposed", al and not any(x["target_ip"] == "192.168.137.1" for x in c.get(SM + "/api/actions").json()))
    check("never-block: no call to Wazuh", len(c.get(FW + "/_test/calls").json()) == n_calls)

    # 7. Secrets never leak
    blob = c.get(SM + "/api/clinic").text + c.get(SM + "/api/actions").text + c.get(SM + "/api/demo/status").text + open(state).read()
    check("no Wazuh passwords or token in API or state", not any(x in blob for x in ("api-secret-123", "idx-secret-456", "tok-789")))

    # 8. Wazuh goes down -> status says so, replay still works
    fake.terminate(); fake.wait()
    check("Wazuh down is reported", wait(lambda: c.get(SM + "/api/clinic").json()["live"].get("ok") is False, 10))
    check("Backstage replay still works", c.post(SM + "/api/demo/replay/ransomware").status_code == 200)
finally:
    for p in (fake, sm):
        if p.poll() is None: p.terminate()
    sm.wait()
    out = sm.stdout.read()
    check("no secrets in the server log", not any(x in out for x in ("api-secret-123", "idx-secret-456", "tok-789")))
    if os.path.exists(state): os.remove(state)

print("CHECKS:", sum(checks), "/", len(checks))
sys.exit(0 if all(checks) else 1)
