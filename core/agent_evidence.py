"""Agent evidence writer.

Writes audit evidence for agent work requests, scope decisions, approval
decisions, and optional review-orchestration decisions. Evidence is read-only
from the trading system perspective: it records what happened, but it never
mutates trading state, calls brokers, or grants live execution permission.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping

from core.paths import ensure_dir, runtime_dir
from core.log_writer import get_jsonl_writer


AGENT_EVIDENCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AgentEvidenceWriteResult:
    schema_version: int
    latest_path: str
    journal_path: str
    read_only: bool
    is_order_action: bool
    broker_api_called: bool
    live_mode_touched: bool
    allowed_for_live_execution: bool
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metadata"] = dict(self.metadata)
        return payload


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe(value.to_dict())
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _root(root_dir: str | Path | None) -> Path:
    if root_dir is not None:
        return Path(root_dir).expanduser()
    return runtime_dir() / "agent_work"


def build_agent_evidence_payload(
    *,
    request: Any,
    scope_decision: Any,
    approval_decision: Any | None = None,
    orchestration_decision: Any | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    now = created_at or _utc_now()
    return {
        "schema_version": AGENT_EVIDENCE_SCHEMA_VERSION,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "request": _json_safe(request),
        "scope_decision": _json_safe(scope_decision),
        "approval_decision": _json_safe(approval_decision),
        "orchestration_decision": _json_safe(orchestration_decision),
        "safety": {
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "live_mode_touched": False,
            "allowed_for_live_execution": False,
        },
        "metadata": {
            "contract": "agent_evidence_v1",
            "scope": "audit_evidence_only_no_runtime_no_broker_no_live",
            "includes_orchestration": orchestration_decision is not None,
        },
    }


def write_agent_evidence(
    *,
    request: Any,
    scope_decision: Any,
    approval_decision: Any | None = None,
    orchestration_decision: Any | None = None,
    root_dir: str | Path | None = None,
    created_at: datetime | None = None,
) -> AgentEvidenceWriteResult:
    root = ensure_dir(_root(root_dir))
    payload = build_agent_evidence_payload(
        request=request,
        scope_decision=scope_decision,
        approval_decision=approval_decision,
        orchestration_decision=orchestration_decision,
        created_at=created_at,
    )
    created_text = str(payload["created_at"])
    date_key = created_text[:10]

    latest_path = root / "agent_work_latest.json"
    journal_path = root / f"agent_work_{date_key}.jsonl"
    encoded = json.dumps(payload, sort_keys=True, indent=2, default=str)

    with tempfile.NamedTemporaryFile("w", delete=False, dir=root, encoding="utf-8") as tmp:
        tmp.write(encoded)
        tmp_path = Path(tmp.name)
    tmp_path.replace(latest_path)

    if not get_jsonl_writer(journal_path).write(payload):
        raise OSError("bounded_agent_evidence_write_rejected")

    return AgentEvidenceWriteResult(
        schema_version=AGENT_EVIDENCE_SCHEMA_VERSION,
        latest_path=str(latest_path),
        journal_path=str(journal_path),
        read_only=True,
        is_order_action=False,
        broker_api_called=False,
        live_mode_touched=False,
        allowed_for_live_execution=False,
        metadata={
            "contract": "agent_evidence_write_result_v1",
            "scope": "evidence_write_only_no_trading_state_mutation",
            "includes_orchestration": orchestration_decision is not None,
        },
    )


__all__ = [
    "AGENT_EVIDENCE_SCHEMA_VERSION",
    "AgentEvidenceWriteResult",
    "build_agent_evidence_payload",
    "write_agent_evidence",
]
