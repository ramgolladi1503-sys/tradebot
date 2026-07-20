"""Local worktree supervisor for agent-assisted Tradebot engineering.

The supervisor converts an approved agent work request into an auditable local
workflow:

    preflight -> claim -> verify -> independent review -> release

It never launches an AI agent, calls a broker, places an order, edits trading
runtime state, merges code, or grants live execution permission.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import posixpath
import re
from typing import Any, Iterable, Mapping


AGENT_SUPERVISOR_SCHEMA_VERSION = 1
_CLAIM_HOLDING_STATES = frozenset(
    {"ACTIVE", "VERIFIED", "REVIEW_NEEDS_HUMAN", "REVIEW_APPROVED", "REVIEW_REJECTED"}
)
_VERIFICATION_CLAIM_STATES = frozenset({"ACTIVE", "VERIFIED", "REVIEW_NEEDS_HUMAN"})
_ALLOWED_REVIEW_DECISIONS = frozenset({"APPROVE", "REWRITE", "REJECT", "NEEDS_HUMAN"})
_ALLOWED_EXECUTABLES = frozenset({"python", "python3", "pytest", "ruff", "mypy", "git"})
_READ_ONLY_GIT_COMMANDS = frozenset({"status", "diff", "rev-parse", "show", "log"})
_BLOCKED_SCRIPT_BASENAMES = frozenset(
    {
        "main.py",
        "run_live.sh",
        "approve_trade.py",
        "generate_kite_access_token.py",
        "start_depth_ws.py",
        "kill_switch.py",
    }
)
_BLOCKED_ORDER_ARGUMENTS = frozenset(
    f"{verb}_order" for verb in ("place", "modify", "cancel", "exit")
)
_BLOCKED_ARGUMENTS = frozenset(
    {
        "--live",
        "--enable-live",
        "enable_live",
        "disable_risk_gate",
        "disable_kill_switch",
        "disable_feed_freshness_gate",
    }
) | _BLOCKED_ORDER_ARGUMENTS
_SECRET_ENV_FRAGMENTS = (
    "KITE",
    "ZERODHA",
    "UPSTOX",
    "BROKER",
    "TELEGRAM",
    "SMTP",
    "API_SECRET",
    "ACCESS_TOKEN",
)
_TASK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")
_MAX_CAPTURE_CHARS = 8_000


class SupervisorState(str, Enum):
    PREFLIGHT_READY = "SUPERVISOR_PREFLIGHT_READY"
    PREFLIGHT_BLOCKED = "SUPERVISOR_PREFLIGHT_BLOCKED"
    CLAIMED = "SUPERVISOR_CLAIMED"
    CLAIM_BLOCKED = "SUPERVISOR_CLAIM_BLOCKED"
    VERIFIED = "SUPERVISOR_VERIFIED"
    VERIFICATION_FAILED = "SUPERVISOR_VERIFICATION_FAILED"
    REVIEW_APPROVED = "SUPERVISOR_REVIEW_APPROVED"
    REVIEW_REWRITE = "SUPERVISOR_REVIEW_REWRITE"
    REVIEW_REJECTED = "SUPERVISOR_REVIEW_REJECTED"
    REVIEW_NEEDS_HUMAN = "SUPERVISOR_REVIEW_NEEDS_HUMAN"
    REVIEW_BLOCKED = "SUPERVISOR_REVIEW_BLOCKED"
    RELEASED = "SUPERVISOR_RELEASED"
    RELEASE_BLOCKED = "SUPERVISOR_RELEASE_BLOCKED"
    STATUS = "SUPERVISOR_STATUS"


@dataclass(frozen=True)
class AcceptanceCommand:
    name: str
    argv: tuple[str, ...]
    timeout_seconds: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["argv"] = list(self.argv)
        return payload


@dataclass(frozen=True)
class SupervisorContract:
    schema_version: int
    task_id: str
    objective: str
    implementer: str
    reviewer: str
    worktree_path: str
    branch: str
    base_ref: str
    requested_paths: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    prohibited_paths: tuple[str, ...]
    ownership_paths: tuple[str, ...]
    frozen_paths: tuple[str, ...]
    acceptance_commands: tuple[AcceptanceCommand, ...]
    required_artifacts: tuple[str, ...]
    require_clean_worktree: bool
    require_committed_head: bool
    work_payload: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "requested_paths",
            "allowed_paths",
            "prohibited_paths",
            "ownership_paths",
            "frozen_paths",
            "required_artifacts",
        ):
            payload[key] = list(payload[key])
        payload["acceptance_commands"] = [command.to_dict() for command in self.acceptance_commands]
        payload["work_payload"] = dict(self.work_payload)
        payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class SupervisorResult:
    schema_version: int
    state: str
    accepted: bool
    task_id: str | None
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    details: dict[str, Any]
    safety: dict[str, bool]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["details"] = dict(self.details)
        payload["safety"] = dict(self.safety)
        payload["metadata"] = dict(self.metadata)
        return payload


def _safety() -> dict[str, bool]:
    return {
        "read_only_from_trading_runtime": True,
        "is_order_action": False,
        "broker_api_called": False,
        "live_mode_touched": False,
        "allowed_for_runtime_wiring": False,
        "allowed_for_live_execution": False,
        "auto_merge_enabled": False,
    }


def _result(
    *,
    state: SupervisorState,
    accepted: bool,
    task_id: str | None,
    blockers: Iterable[str] = (),
    warnings: Iterable[str] = (),
    details: Mapping[str, Any] | None = None,
) -> SupervisorResult:
    return SupervisorResult(
        schema_version=AGENT_SUPERVISOR_SCHEMA_VERSION,
        state=state.value,
        accepted=accepted,
        task_id=task_id,
        blockers=tuple(sorted({str(item).strip().upper() for item in blockers if str(item).strip()})),
        warnings=tuple(sorted({str(item).strip().upper() for item in warnings if str(item).strip()})),
        details=dict(details or {}),
        safety=_safety(),
        metadata={
            "contract": "tradebot_agent_supervisor_v1",
            "scope": "local_engineering_worktree_supervision_only",
        },
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _tuple_text(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = _text(value)
        return (text,) if text else ()
    if isinstance(value, Iterable):
        return tuple(_text(item) for item in value if _text(item))
    return ()


def _normalize_rel_path(value: str) -> str:
    raw = _text(value).replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    normalized = posixpath.normpath(raw) if raw else ""
    return "" if normalized == "." else normalized


def _unsafe_rel_path(value: str) -> bool:
    raw = _text(value).replace("\\", "/")
    if not raw or raw.startswith("/"):
        return True
    return any(part == ".." for part in raw.split("/") if part)


def _path_matches(path: str, prefix: str) -> bool:
    path_text = _normalize_rel_path(path)
    prefix_text = _normalize_rel_path(prefix).rstrip("/")
    if not path_text or not prefix_text:
        return False
    return path_text == prefix_text or path_text.startswith(f"{prefix_text}/")


def _paths_overlap(left: str, right: str) -> bool:
    return _path_matches(left, right) or _path_matches(right, left)


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
