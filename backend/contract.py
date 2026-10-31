"""The frozen API contract: Pydantic models for every route, plus the route index.

Source of truth: docs/ShieldMate - Build Spec (finalise before H0).pdf, as amended by
docs/DECISIONS.md. Changing anything here needs all four owners to agree, and the contract
tests (tests/contract) change in the same merge.

Conventions: every field is always present (empty means None, never missing);
extra fields are rejected so drift shows up in tests; lists are wrapped in objects.
The one exception is RestoreCheck.failed_files, which the spec says appears on the
integrity check only, so it defaults to None.
"""
from __future__ import annotations

from typing import Literal, NamedTuple

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- enums ---------------------------------------------------------------

Role = Literal["front_desk", "billing", "owner"]
Lang = Literal["en", "kn", "hi"]
ActionId = Literal[
    "DONT_USE_DEVICE", "ISOLATE_NETWORK", "CALL_SAVED_IT", "NOTIFY_OWNER",
    "PRESERVE_EVIDENCE", "VERIFY_BACKUP", "REPORT_CERTIN", "START_DPDP_NOTE", "BLOCK_IP",
]
Severity = Literal["needs_you_now", "heads_up"]
AlertStatus = Literal["new", "done", "filtered"]
AlertSource = Literal["replay", "wazuh"]
DrillStatus = Literal["lobby", "open", "review", "finished"]
Phase = Literal["detect", "contain", "recover", "report"]
ScenarioDeviceState = Literal["ok", "infected", "isolated", "encrypting", "encrypted"]
ServiceStatus = Literal["ok", "moved", "down", "unavailable"]
DeviceStatus = Literal["ok", "under_attack", "protected"]
RestoreResult = Literal["PASS", "FAIL", "NOT_TESTED"]
RestoreCheckName = Literal["freshness", "integrity", "exposure"]
ActionStatus = Literal[
    "proposed", "approved", "declined", "executed", "failed", "expired", "undone", "refused",
]
DecidedVia = Literal["tap", "standing_rule"]
OnTimeout = Literal["block_under_standing_rule", "ask_backup_approver"]
RewordSource = Literal["ai", "fallback"]
ReplayType = Literal["password_guessing", "ransomware"]
ErrorCode = Literal[
    "invalid_request", "invalid_option", "pin_required", "pin_invalid", "not_host",
    "not_found", "not_enabled", "drill_not_found", "player_not_in_drill", "step_closed",
    "already_answered", "drill_finished", "action_not_pending", "target_refused",
    "undo_not_supported", "replay_exhausted", "wazuh_unavailable", "internal_error",
]


# --- errors --------------------------------------------------------------

class ErrorBody(Model):
    error: ErrorCode
    message: str


# --- GET /clinic, PUT /clinic/standing-rule ------------------------------

class ClinicOut(Model):
    id: int
    name: str
    backup_age_limit_hours: int
    it_contact_name: str
    it_contact_phone: str
    standing_rule_block_ip: bool
    standing_rule_set_by: int | None
    standing_rule_set_at: str | None
    approval_timeout_minutes: int
    block_minutes: int


class StaffOut(Model):
    id: int
    name: str
    role: Role
    can_restore_backups: bool
    can_approve_downtime: bool
    is_backup_approver: bool


class ClinicDevice(Model):
    id: int
    agent_name: str
    location: str
    services: list[str]


class SinglePointOfFailure(Model):
    capability: Literal["can_restore_backups", "can_approve_downtime"]
    label: str
    only: str


class ClinicResponse(Model):
    clinic: ClinicOut
    staff: list[StaffOut]
    devices: list[ClinicDevice]
    single_point_of_failure: list[SinglePointOfFailure]


class StandingRuleRequest(Model):
    enabled: bool
    staff_id: int


# --- GET /status ---------------------------------------------------------

class Flags(Model):
    AI_REWORD: bool
    ACTIONS: bool


class WazuhHealth(Model):
    api_ok: bool | None
    indexer_ok: bool | None
    agent_active: bool | None
    last_alert_at: str | None


class StatusResponse(Model):
    alert_source: AlertSource
    flags: Flags
    undo_supported: bool
    server_time: str
    wazuh: WazuhHealth


# --- alerts --------------------------------------------------------------

class CardStep(Model):
    action: ActionId
    text: str


class Card(Model):
    lang: Lang
    headline: str
    what_we_know: str
    why: str
    steps: list[CardStep]
    log_fields: dict[str, str]          # verbatim; render as text only, never HTML
    drill_scenario: str | None


class AlertActionRef(Model):
    id: int
    status: ActionStatus
    simulated: bool


class AlertOut(Model):
    id: int
    source: AlertSource
    rule_id: str
    level: int
    agent_name: str
    lesson_id: str
    severity: Severity
    status: AlertStatus
    count: int
    first_seen: str
    last_seen: str
    done_by: int | None
    card: Card
    action: AlertActionRef | None


class AlertsResponse(Model):
    hidden_count: int
    alerts: list[AlertOut]


class DoneRequest(Model):
    staff_id: int


class RewordRequest(Model):
    role: Role
    lang: Lang


class RewordResponse(Model):
    headline: str
    why: str
    source: RewordSource


# --- notifications -------------------------------------------------------

class StaffRef(Model):
    id: int
    name: str


class NotificationOut(Model):
    id: int
    alert_id: int | None
    action_row_id: int | None
    from_staff: StaffRef | None
    to_role: Role | None
    to_staff_id: int | None
    text: str
    created_at: str


class NotificationsResponse(Model):
    notifications: list[NotificationOut]
    last_id: int


# --- drills --------------------------------------------------------------

class DrillCreateRequest(Model):
    scenario_id: str
    host_staff_id: int
    source_alert_id: int | None


class DrillCreateResponse(Model):
    code: str
    player_id: int
    status: DrillStatus


class JoinRequest(Model):
    staff_id: int


class JoinResponse(Model):
    player_id: int
    code: str
    status: DrillStatus


class DrillMe(Model):
    player_id: int
    staff_id: int
    name: str
    role: Role
    is_host: bool


class DrillStep(Model):
    step_id: str
    phase: Phase
    game_time: str
    situation: str
    opened_at: str | None


class DrillOption(Model):
    option_id: str
    text: str


class MyAnswer(Model):
    option_id: str
    correct: bool
    feedback: str
    actions: list[ActionId]


class TeamPlayer(Model):
    player_id: int
    name: str
    role: Role
    has_options: bool
    answered: bool


class Team(Model):
    answered: int
    total: int
    players: list[TeamPlayer]


class ReviewAnswer(Model):
    name: str
    option_text: str | None             # None = no answer
    correct: bool


class Review(Model):
    answers: list[ReviewAnswer]


class ImpactService(Model):
    name: str
    status: ServiceStatus
    note: str | None = None             # only on "moved" services


class ImpactDevice(Model):
    device: str
    state: ScenarioDeviceState
    services: list[ImpactService]


class PhaseScore(Model):
    correct: int
    total: int


class PlayerResult(Model):
    name: str
    by_phase: dict[Phase, PhaseScore]
    missed_actions: list[ActionId]


class TeamScore(Model):
    correct: int
    total: int


class RestoreSummary(Model):
    result: RestoreResult


class DrillResults(Model):
    phases: list[Phase]
    players: list[PlayerResult]
    team: TeamScore
    restore: RestoreSummary | None


class DrillView(Model):
    code: str
    scenario_id: str
    title: str
    status: DrillStatus
    step_index: int
    step_count: int
    me: DrillMe
    step: DrillStep | None              # None in lobby and when finished
    options: list[DrillOption]
    waiting_message: str | None
    my_answer: MyAnswer | None
    team: Team
    review: Review | None
    impact: list[ImpactDevice]
    restore_check_available: bool
    can_advance: bool
    results: DrillResults | None


class AnswerRequest(Model):
    player_id: int
    step_id: str
    option_id: str


class AdvanceRequest(Model):
    player_id: int


# --- restore check -------------------------------------------------------

class RestoreCheck(Model):
    check: RestoreCheckName
    passed: bool
    detail: str
    fix: str
    failed_files: list[str] | None = None   # integrity check only


class RestoreRun(Model):
    id: int | None
    started_at: str | None
    result: RestoreResult
    simulated_backup: bool
    backup_age_hours: float | None
    files_total: int | None
    files_ok: int | None
    exposed: bool | None
    checks: list[RestoreCheck]


# --- devices and actions (flag ACTIONS) ----------------------------------

class DeviceBlock(Model):
    action_row_id: int
    target_ip: str
    expires_at: str | None


class DeviceOut(Model):
    id: int
    agent_name: str
    location: str
    status: DeviceStatus
    status_changed_at: str | None
    block: DeviceBlock | None


class DevicesResponse(Model):
    devices: list[DeviceOut]


class ActionOut(Model):
    id: int
    alert_id: int
    action_id: Literal["BLOCK_IP"]
    label: str
    target_ip: str | None
    agent_name: str
    simulated: bool
    status: ActionStatus
    refused_reason: str | None
    decided_by: int | None
    decided_via: DecidedVia | None
    proposed_at: str
    decided_at: str | None
    expires_at: str | None
    seconds_left: int | None
    on_timeout: OnTimeout
    undo_available: bool
    # wazuh_response is stored but never returned.


class ActionsResponse(Model):
    actions: list[ActionOut]


class ActionDecisionRequest(Model):
    staff_id: int


# --- demo ----------------------------------------------------------------

class ReplayResult(Model):
    alert_type: ReplayType
    click: int
    injected: int
    cards_created: int
    grouped: int
    filtered: int
    clicks_left: int


class ResetResult(Model):
    ok: bool
    reset_at: str


# --- route index ---------------------------------------------------------

class Route(NamedTuple):
    """One contract route. `fixture` is the stub body served in Increment 0 and the
    body the contract tests validate against `response`. `flag` is the env flag that
    must be on (else not_enabled, 404); `who` is any | owner | backstage."""
    method: str
    path: str
    request: type[BaseModel] | None
    response: type[BaseModel]
    fixture: str
    who: str = "any"
    flag: str | None = None


ROUTES: list[Route] = [
    Route("GET", "/clinic", None, ClinicResponse, "clinic.json"),
    Route("GET", "/status", None, StatusResponse, "status.json"),
    Route("GET", "/alerts", None, AlertsResponse, "alerts.json"),
    Route("POST", "/alerts/{id}/done", DoneRequest, AlertOut, "alert_done.json"),
    Route("POST", "/alerts/{id}/reword", RewordRequest, RewordResponse, "reword.json", flag="AI_REWORD"),
    Route("GET", "/notifications", None, NotificationsResponse, "notifications.json"),
    Route("POST", "/drills", DrillCreateRequest, DrillCreateResponse, "drill_create.json", who="owner"),
    Route("POST", "/drills/{code}/join", JoinRequest, JoinResponse, "drill_join.json"),
    Route("GET", "/drills/{code}", None, DrillView, "drill_view.json"),
    Route("POST", "/drills/{code}/answers", AnswerRequest, MyAnswer, "drill_answer.json"),
    Route("POST", "/drills/{code}/advance", AdvanceRequest, DrillView, "drill_view_review.json", who="owner"),
    Route("POST", "/restore/run", None, RestoreRun, "restore_run.json", who="owner"),
    Route("GET", "/restore/latest", None, RestoreRun, "restore_latest.json"),
    Route("GET", "/devices", None, DevicesResponse, "devices.json", flag="ACTIONS"),
    Route("GET", "/actions", None, ActionsResponse, "actions.json", flag="ACTIONS"),
    Route("POST", "/actions/{id}/approve", ActionDecisionRequest, ActionOut, "action_executed.json", who="owner", flag="ACTIONS"),
    Route("POST", "/actions/{id}/decline", ActionDecisionRequest, ActionOut, "action_declined.json", who="owner", flag="ACTIONS"),
    Route("POST", "/actions/{id}/undo", ActionDecisionRequest, ActionOut, "action_undone.json", who="owner", flag="ACTIONS"),
    Route("PUT", "/clinic/standing-rule", StandingRuleRequest, ClinicOut, "standing_rule.json", who="owner", flag="ACTIONS"),
    Route("POST", "/demo/replay/{alert_type}", None, ReplayResult, "demo_replay.json", who="backstage"),
    Route("POST", "/demo/reset", None, ResetResult, "demo_reset.json", who="backstage"),
]

# Extra fixtures that are valid bodies of the models above (used by tests only).
EXTRA_FIXTURES: dict[str, type[BaseModel]] = {
    "drill_view_finished.json": DrillView,
    "restore_latest_untested.json": RestoreRun,
    "action_proposed.json": ActionOut,
    "action_refused.json": ActionOut,
    "error.json": ErrorBody,
}
