"""Environment variables and flags (Build Spec, "Flags and environment variables").

Values come from backend/.env (a tiny KEY=VALUE parser, no dependency) with real
environment variables winning. Relative paths in .env are written from the repo root
(e.g. ``backend/shieldmate.db``), so they are resolved against the repo root no matter
which directory uvicorn is started from.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # only for type hints; avoids import cycles
    from actions.wazuh_client import WazuhClient
    from clock import Clock
    from db import Database
    from ingest.replay import ReplaySource
    from ingest.simulator import Simulator
    from ingest.source import AlertSource
    from lessons.engine import LessonBook
    from lessons.providers import RewordProvider
    from ai.interpreter import InterpreterClient

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines. Blank lines and '#' comments are skipped; quotes are stripped."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else REPO_ROOT / p


@dataclass(frozen=True)
class Config:
    alert_source: str = "replay"            # replay | wazuh
    ai_reword: bool = False
    actions: bool = False
    db_path: Path = REPO_ROOT / "backend" / "shieldmate.db"
    port: int = 8000
    owner_pin: str = ""                     # empty = PIN off (decision 3)
    backstage_token: str = ""
    restore_backup_dir: Path = REPO_ROOT / "backend" / "demo_backup" / "backup"
    restore_manifest: Path = REPO_ROOT / "backend" / "demo_backup" / "originals" / "manifest.json"
    restore_sandbox_dir: Path = REPO_ROOT / "backend" / "restore_sandbox"
    wazuh_api_url: str = ""
    wazuh_api_user: str = ""
    wazuh_api_password: str = ""
    wazuh_indexer_url: str = ""
    wazuh_indexer_user: str = ""
    wazuh_indexer_password: str = ""
    wazuh_ca_cert: str = ""
    wazuh_ar_command: str = "netsh3600"
    wazuh_timeout_seconds: float = 5.0
    ai_provider: str = "none"
    # AI interpreter (roadmap): proxy a stuck user's question to the n8n agent so they can
    # understand a task. Off by default; the URL is a server-side secret (like the Wazuh creds).
    ai_interpreter: bool = False
    ai_interpreter_url: str = ""
    ai_interpreter_timeout_seconds: float = 30.0
    # Attack simulation (roadmap T8): the in-app attacker that generates Wazuh-shaped
    # alerts from a script. Default off - the replay demo stays the stage fallback.
    simulate: bool = False
    sim_dir: Path = BACKEND_DIR / "replay" / "sim"
    sim_time_limit_ms: int = 600_000      # 10 sim-minutes; a run longer than this expires
    # Event log (eventlog/). On by default: it is the app's record of what happened, not a feature.
    event_log: bool = True
    events_db_path: Path | None = None      # None = next to db_path, e.g. backend/shieldmate-events.db
    event_log_reads: bool = False           # also log successful GETs (the 2 s polls; noisy)
    # Frozen data files. Kept on the config so tests can point at copies.
    seed_path: Path = BACKEND_DIR / "seed" / "clinic.json"
    lessons_path: Path = BACKEND_DIR / "lessons" / "lessons.json"
    replay_path: Path = BACKEND_DIR / "replay" / "alerts.json"
    schema_path: Path = BACKEND_DIR / "schema.sql"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"

    # Decision 9: Undo is off until lab test T5.07 passes.
    undo_supported: bool = False

    @classmethod
    def load(cls, env_file: Path | None = None, environ: dict[str, str] | None = None) -> "Config":
        """Build a Config from .env plus the environment (environment wins)."""
        # .env first, then real environment variables on top (they win).
        env = parse_env_file(env_file or BACKEND_DIR / ".env")
        env.update(os.environ if environ is None else environ)
        d = cls()
        alert_source = env.get("ALERT_SOURCE") or d.alert_source
        if alert_source not in ("replay", "wazuh"):     # a typo would otherwise make GET /status fail later
            raise ValueError(f"ALERT_SOURCE must be 'replay' or 'wazuh', not {alert_source!r}")
        return cls(
            alert_source=alert_source,
            ai_reword=_flag(env.get("AI_REWORD")),
            actions=_flag(env.get("ACTIONS")),
            db_path=_path(env["DB_PATH"]) if env.get("DB_PATH") else d.db_path,
            port=int(env.get("PORT") or d.port),
            owner_pin=env.get("OWNER_PIN", ""),
            backstage_token=env.get("BACKSTAGE_TOKEN", ""),
            restore_backup_dir=_path(env["RESTORE_BACKUP_DIR"]) if env.get("RESTORE_BACKUP_DIR") else d.restore_backup_dir,
            restore_manifest=_path(env["RESTORE_MANIFEST"]) if env.get("RESTORE_MANIFEST") else d.restore_manifest,
            restore_sandbox_dir=_path(env["RESTORE_SANDBOX_DIR"]) if env.get("RESTORE_SANDBOX_DIR") else d.restore_sandbox_dir,
            wazuh_api_url=env.get("WAZUH_API_URL", ""),
            wazuh_api_user=env.get("WAZUH_API_USER", ""),
            wazuh_api_password=env.get("WAZUH_API_PASSWORD", ""),
            wazuh_indexer_url=env.get("WAZUH_INDEXER_URL", ""),
            wazuh_indexer_user=env.get("WAZUH_INDEXER_USER", ""),
            wazuh_indexer_password=env.get("WAZUH_INDEXER_PASSWORD", ""),
            wazuh_ca_cert=env.get("WAZUH_CA_CERT", ""),
            wazuh_ar_command=env.get("WAZUH_AR_COMMAND") or d.wazuh_ar_command,
            wazuh_timeout_seconds=float(env.get("WAZUH_TIMEOUT_SECONDS") or d.wazuh_timeout_seconds),
            ai_provider=env.get("AI_PROVIDER") or d.ai_provider,
            ai_interpreter=_flag(env.get("AI_INTERPRETER")),
            ai_interpreter_url=env.get("AI_INTERPRETER_URL", ""),
            ai_interpreter_timeout_seconds=float(env.get("AI_INTERPRETER_TIMEOUT_SECONDS")
                                                 or d.ai_interpreter_timeout_seconds),
            # Which clinic seed to load (e.g. backend/seed/clinic.lab.json for the Wazuh lab).
            seed_path=_path(env["SEED_PATH"]) if env.get("SEED_PATH") else d.seed_path,
            simulate=_flag(env.get("SIMULATE")),
            sim_dir=_path(env["SIM_DIR"]) if env.get("SIM_DIR") else d.sim_dir,
            sim_time_limit_ms=int(env.get("SIM_TIME_LIMIT_MS") or d.sim_time_limit_ms),
            event_log=_flag(env.get("EVENT_LOG") or "1"),
            events_db_path=_path(env["EVENTS_DB_PATH"]) if env.get("EVENTS_DB_PATH") else d.events_db_path,
            event_log_reads=_flag(env.get("EVENT_LOG_READS")),
        )

    @property
    def events_path(self) -> Path:
        """Where the event log lives. By default it sits beside the main DB, so each test's temp DB gets its own."""
        return self.events_db_path or self.db_path.with_name(f"{self.db_path.stem}-events.db")

    def with_(self, **changes) -> "Config":
        """Copy with some fields changed (used by tests)."""
        return replace(self, **changes)

    def flag(self, name: str) -> bool:
        """Look up a feature flag by its env-var name (``AI_REWORD``, ``ACTIONS``, ``SIMULATE`` or ``EVENT_LOG``)."""
        return {"AI_REWORD": self.ai_reword, "ACTIONS": self.actions, "SIMULATE": self.simulate,
                "AI_INTERPRETER": self.ai_interpreter, "EVENT_LOG": self.event_log}[name]


@dataclass
class Context:
    """Everything the routes need, built once in main.create_app and stored on app.state.

    The four seams (alert source, Wazuh client, reword provider, clock) are chosen here
    so tests can swap in fakes.
    """
    config: Config
    db: "Database"
    clock: "Clock"
    source: "AlertSource"          # live ingest source (the replay source in replay mode)
    replay: "ReplaySource"         # always present: /demo/replay works even in live mode
    wazuh: "WazuhClient"
    lessons: "LessonBook"
    reword_provider: "RewordProvider"
    sim: "Simulator | None" = None # the in-app attack simulator (SIMULATE flag; None when off)
    # AI interpreter client (AI_INTERPRETER flag). Fake when the flag is off / URL missing, so a
    # broken config never takes the app down (T5.09, like the Wazuh client).
    interpreter: "InterpreterClient | None" = None
    # Last Wazuh health snapshot for /status (all None in replay mode).
    wazuh_health: dict = field(default_factory=lambda: {
        "api_ok": None, "indexer_ok": None, "agent_active": None, "last_alert_at": None})
