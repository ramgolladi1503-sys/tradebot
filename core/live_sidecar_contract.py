"""Contracts for isolated, exact-SHA, read-only PR validation consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


RUNTIME_CANDIDATE_TOUCHES = frozenset({
    "run_live.sh", "core/kite_depth_ws.py", "core/feed", "core/broker",
    "core/execution", "core/risk", "core/strategy", "persistence",
})


@dataclass(frozen=True)
class SidecarSpec:
    pr_number: int
    pr_sha: str
    base_sha: str
    validation_objective: str
    input_source: str
    evidence_path: str
    touches: tuple[str, ...] = ()
    broker_order_calls: int = 0
    live_db_writes: int = 0

    def validate(self) -> None:
        for name in ("pr_sha", "base_sha", "validation_objective", "input_source", "evidence_path"):
            if not str(getattr(self, name) or "").strip():
                raise ValueError(f"sidecar_missing_{name}")
        if self.broker_order_calls != 0:
            raise ValueError("sidecar_broker_order_calls_nonzero")
        if self.live_db_writes != 0:
            raise ValueError("sidecar_live_db_writes_nonzero")
        if classify_touches(self.touches) != "SIDECAR_SAFE":
            raise ValueError("sidecar_requires_runtime_candidate")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "PR_NUMBER": self.pr_number,
            "PR_SHA": self.pr_sha,
            "BASE_SHA": self.base_sha,
            "VALIDATION_OBJECTIVE": self.validation_objective,
            "INPUT_SOURCE": self.input_source,
            "EVIDENCE_PATH": self.evidence_path,
            "TOUCHES": list(self.touches),
            "BROKER_ORDER_CALLS": 0,
            "LIVE_DB_WRITES": 0,
            "EXECUTION_STATUS": "READ_ONLY_SIDECAR",
        }


def classify_touches(touches: Any) -> str:
    paths = tuple(str(item).strip().lstrip("./") for item in (touches or ()))
    if not paths:
        return "NOT_READY"
    if any(path == blocked or path.startswith(blocked + "/") for path in paths for blocked in RUNTIME_CANDIDATE_TOUCHES):
        return "RUNTIME_CANDIDATE_REQUIRED"
    return "SIDECAR_SAFE"


def sidecar_health(spec: SidecarSpec, *, main_session_id: str, failed: bool = False) -> dict[str, Any]:
    spec.validate()
    return {
        **spec.to_dict(),
        "MAIN_SESSION_ID": main_session_id,
        "STATUS": "FAILED_ISOLATED" if failed else "READY",
        "CAN_MUTATE_MAIN": False,
        "CAN_OWN_CANONICAL_FEED": False,
        "BROKER_WRITE_AUTHORITY": False,
        "ORDER_AUTHORITY": False,
    }
