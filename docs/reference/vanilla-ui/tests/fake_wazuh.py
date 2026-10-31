"""A stand-in for the Wazuh indexer + API, for testing live mode without the lab.

Answers the three calls ShieldMate makes (indexer _search, API login, active response)
and records every active-response call. Test controls live under /_test/.
Run: python tests/fake_wazuh.py   (port 8900)
"""
import base64
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

app = FastAPI()
ALERTS, CALLS = [], []
SEQ = [0]
API_AUTH = ("shieldmate", "api-secret-123")
IDX_AUTH = ("shieldmate_reader", "idx-secret-456")
TOKEN = "tok-789"


def basic(req):
    h = req.headers.get("authorization", "")
    if not h.startswith("Basic "): return None
    u, _, p = base64.b64decode(h[6:]).decode().partition(":")
    return (u, p)


def ts(ms=None):
    ms = ms or int(time.time() * 1000)
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0000"


def add(rule, ip, user="administrator", agent=("001", "RECEPTION-PC")):
    SEQ[0] += 1
    ALERTS.append({"_id": "w%d" % SEQ[0], "timestamp": ts(), "rule": {"id": rule, "level": 10 if rule == "60204" else 5},
                   "agent": {"id": agent[0], "name": agent[1]},
                   "data": {"win": {"eventdata": {"ipAddress": ip, "targetUserName": user}}}})


@app.post("/{index}/_search")
async def search(index: str, req: Request):
    if basic(req) != IDX_AUTH: return JSONResponse({"error": "unauthorized"}, status_code=401)
    q = (await req.json())["query"]["bool"]["filter"]
    since = q[0]["range"]["timestamp"]["gte"]
    rules, agents = q[1]["terms"]["rule.id"], q[2]["terms"]["agent.name"]
    hits = [a for a in ALERTS if a["timestamp"] >= since and a["rule"]["id"] in rules and a["agent"]["name"] in agents]
    return {"hits": {"hits": [{"_id": a["_id"], "_source": {k: v for k, v in a.items() if k != "_id"}} for a in hits]}}


@app.post("/security/user/authenticate")
async def login(req: Request):
    if basic(req) != API_AUTH: return JSONResponse({"error": "unauthorized"}, status_code=401)
    return PlainTextResponse(TOKEN)


@app.put("/active-response")
async def active_response(req: Request):
    if req.headers.get("authorization") != "Bearer " + TOKEN: return JSONResponse({"error": "unauthorized"}, status_code=401)
    CALLS.append({"agents_list": req.query_params.get("agents_list"), "body": await req.json()})
    return {"data": {"affected_items": [req.query_params.get("agents_list")]}, "error": 0}


@app.get("/agents")
async def agents(req: Request):
    return {"data": {"affected_items": [{"id": "001", "status": "active"}]}}


# ----- test controls -----
@app.post("/_test/attack")
async def attack(req: Request):
    b = await req.json()
    for _ in range(b.get("fails", 9)): add("60122", b["ip"], b.get("user", "administrator"))
    add("60204", b["ip"], b.get("user", "administrator"))
    return {"ok": True}


@app.post("/_test/fails")
async def fails(req: Request):
    b = await req.json()
    for _ in range(b.get("n", 3)): add("60122", b["ip"])
    return {"ok": True}


@app.get("/_test/calls")
def calls(): return CALLS


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8900, log_level="warning")
