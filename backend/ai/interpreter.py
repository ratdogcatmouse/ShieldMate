"""The AI interpreter: proxy a stuck user's question to the n8n agent.

Mirrors actions/wazuh_client.py: one Protocol, a Real client (server-side, talks to the n8n
webhook via stdlib urllib) and a Fake (record + canned answer for demos and tests). The webhook
URL is a server-side secret - it is never sent to the browser, exactly like the Wazuh creds.

``get_interpreter`` picks real-or-fake once from config, and a broken config falls back to the
fake (T5.09): a dead n8n or a half-set-up URL must never take the app down.
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol

from config import Config

MAX_BODY_BYTES = 8 * 1024 * 1024     # same cap as the Wazuh client; an agent answer must fit
MAX_TEXT_BYTES = 2000                # the response model's answer cap


class InterpreterClient(Protocol):
    def ask(self, question: str, context: dict, role: str, lang: str) -> str:
        """Return the agent's plain-language answer for this question + sanitized context."""
        ...


class RealInterpreterClient:
    """POST the question + sanitized context to the n8n webhook over https."""

    def __init__(self, config: Config):
        url = (config.ai_interpreter_url or "").strip()
        parsed = urllib.parse.urlsplit(url)
        # https only, no credentials in the URL - the webhook is a plain public endpoint.
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError(f"AI_INTERPRETER_URL must be an https URL, not {url!r}")
        self._url = url
        self._timeout = config.ai_interpreter_timeout_seconds
        if self._timeout <= 0:
            raise ValueError("AI_INTERPRETER_TIMEOUT_SECONDS must be positive")
        # Verify certificates (never disable, like the Wazuh client).
        self._tls = ssl.create_default_context()
        self.calls: list[dict] = []      # test hook

    def ask(self, question: str, context: dict, role: str, lang: str) -> str:
        payload = json.dumps({"question": question, "context": context,
                              "role": role, "lang": lang}).encode("utf-8")
        # Reject redirects so the request never follows another origin.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                return None
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=self._tls),
                                              NoRedirect())
        request = urllib.request.Request(self._url, data=payload,
                                          headers={"Content-Type": "application/json"}, method="POST")
        with opener.open(request, timeout=self._timeout) as response:
            body = response.read(MAX_BODY_BYTES)
        return self._extract(body)

    @staticmethod
    def _extract(body: bytes) -> str:
        """n8n may answer {"text": ...}, {"answer": ...} or a bare string - parse defensively."""
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            data = None
        if isinstance(data, dict):
            for key in ("text", "answer", "reply", "output"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            raise ValueError("n8n answer had no text field")
        if isinstance(data, str) and data.strip():
            return data
        raise ValueError("n8n answer was not text")


class FakeInterpreterClient:
    """Canned answer; records calls. Returned when the flag is off or the URL is missing."""

    def __init__(self, answer: str = "A security check found something that needs attention. "
                                     "Follow the step shown on your screen, then tap Done."):
        self.answer = answer
        self.calls: list[dict] = []

    def ask(self, question: str, context: dict, role: str, lang: str) -> str:
        self.calls.append({"question": question, "context": context,
                           "role": role, "lang": lang})
        return self.answer


def get_interpreter(config: Config) -> InterpreterClient | None:
    """Real client when AI_INTERPRETER is on and the URL is set; otherwise None (feature off).

    The caller (main.build_context) catches a misconfigured URL and keeps None, so the route
    answers ``not_enabled`` instead of the app crashing at start-up.
    """
    if not config.ai_interpreter:
        return None
    if not config.ai_interpreter_url:
        return None
    return RealInterpreterClient(config)
