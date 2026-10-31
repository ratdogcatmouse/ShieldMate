"""The AI interpreter (roadmap): client seam, sanitized context, and the /interpreter/chat route."""
from __future__ import annotations

import json

from ai import context as ictx
from ai.interpreter import FakeInterpreterClient, RealInterpreterClient, get_interpreter
from config import Config


class _Resp:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n: int) -> bytes:
        return self._body[:n]


def test_get_interpreter_off_returns_none():
    assert get_interpreter(Config()) is None                      # flag off
    assert get_interpreter(Config(ai_interpreter=True)) is None   # on but no URL


def test_get_interpreter_on_builds_real_client():
    config = Config(ai_interpreter=True, ai_interpreter_url="https://n8n.example/webhook")
    assert isinstance(get_interpreter(config), RealInterpreterClient)


def test_real_client_rejects_bad_url():
    config = Config(ai_interpreter=True, ai_interpreter_url="http://insecure.example")
    import pytest
    with pytest.raises(ValueError):
        RealInterpreterClient(config)


def test_real_client_reads_response_field():
    # The live n8n workflow answers {"response": "..."} - it must not read as "no text field".
    assert RealInterpreterClient._extract(b'{"response": "do the step"}') == "do the step"


def test_real_client_sends_query_field():
    client = RealInterpreterClient(Config(ai_interpreter=True, ai_interpreter_url="https://n8n.example/webhook"))

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return b'{"response": "ok"}'

    captured = {}

    class _Opener:
        def open(self, request, timeout=None):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _Resp()

    import ai.interpreter as interp
    orig = interp.urllib.request.build_opener
    interp.urllib.request.build_opener = lambda *a: _Opener()
    try:
        assert client.ask("why?", {}, "owner", "en") == "ok"
    finally:
        interp.urllib.request.build_opener = orig
    # The workflow reads ``query``; sending ``question`` makes n8n reply 500.
    assert captured["payload"]["query"] == "why?"
    assert "question" not in captured["payload"]


def test_fake_client_records_and_answers():
    client = FakeInterpreterClient(answer="the plain answer")
    assert client.ask("why?", {}, "owner", "en") == "the plain answer"
    assert client.calls[0]["question"] == "why?"


def test_context_omits_unknown_ids(tmp_path):
    # A bare Config points the DB at a temp file; connect a real db for the lookups.
    import db as database
    config = Config(db_path=tmp_path / "t.db", schema_path=Config().schema_path)
    db = database.connect(config)
    try:
        ctx = ictx.build_context(db, alert_id=99999, drill_code="9999", device_id=99999,
                                 role="owner", lang="en")
        assert "alert" not in ctx and "drill" not in ctx and "device" not in ctx
        assert ctx["role"] == "owner" and ctx["lang"] == "en"
    finally:
        db.close()


def test_context_never_contains_log_fields(tmp_path):
    """The agent gets ids/labels only - the untrusted log text stays out (T3.01)."""
    import db as database
    config = Config(db_path=tmp_path / "t.db", schema_path=Config().schema_path)
    db = database.connect(config)
    try:
        db.reset(config)
        db.execute(
            "INSERT INTO alerts (id, source, rule_id, level, agent_name, group_key, status,"
            " log_fields, raw, first_seen, last_seen, closed_at) VALUES "
            "(1, 'replay', '102', 5, 'RECEPTION-PC', '102:RECEPTION-PC', 'new',"
            " '{''attacker'':''EVE_SENTINEL_9f1''}', '{}', 't0', 't0', NULL)")
        ctx = ictx.build_context(db, alert_id=1, drill_code=None, device_id=None,
                                 role="owner", lang="en")
        text = json.dumps(ctx)
        # The untrusted log text must not reach the agent: its sentinel value is absent, and the
        # alert block carries only the allowed id/label fields (never log_fields / raw).
        assert "EVE_SENTINEL_9f1" not in text
        assert "attacker" not in text
        assert set(ctx["alert"]) == {"id", "rule_id", "level", "status"}
        assert ctx["alert"]["rule_id"] == "102"
    finally:
        db.close()


# --- the route ---------------------------------------------------------------
BODY = {"question": "what do I do?", "role": "owner", "lang": "en"}


def test_route_flag_off_is_not_enabled(make_app):
    h = make_app()
    assert h.post("/interpreter/chat", json=BODY).status_code == 404


def test_route_flag_on_fake_client_answers(make_app):
    h = make_app(ai_interpreter=True, interpreter=FakeInterpreterClient(answer="do the step."))
    r = h.post("/interpreter/chat", json=BODY)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "ai" and "do the step." in body["answer"]
    # The query is logged with ids/enums only.
    events = [e for e in h.events("interpreter.query") if e["type"] == "interpreter.query"]
    assert len(events) == 1
    assert events[0]["data"]["role"] == "owner"


def test_route_falls_back_when_agent_unreachable(make_app):
    import urllib.error
    # A real client pointed at nothing raises; the route must answer fallback, not 500.
    config_overrides = dict(ai_interpreter=True, ai_interpreter_url="https://nope.invalid")
    h = make_app(interpreter=RealInterpreterClient(
        Config(ai_interpreter=True, ai_interpreter_url="https://nope.invalid",
               ai_interpreter_timeout_seconds=1)), **config_overrides)
    r = h.post("/interpreter/chat", json=BODY)
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "fallback"


def test_route_flag_on_but_no_client_falls_back(make_app):
    # Flag on but get_interpreter returned None (e.g. no URL) -> fallback, still 200.
    h = make_app(ai_interpreter=True)          # ai_interpreter_url left empty -> no client
    assert h.ctx.interpreter is None
    assert h.post("/interpreter/chat", json=BODY).json()["source"] == "fallback"
