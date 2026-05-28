from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from core.replay_session_path import (
    OK_REASON,
    SessionPathReplayEvidence,
    build_session_path_replay_evidence,
)

SESSION_PATH_REPLAY_REPORT_SCHEMA_VERSION = 1
SESSION_PATH_REPLAY_REPORT_SOURCE = "session_path_replay_report_v1"
SESSION_PATH_REPLAY_PASSED = "SESSION_PATH_REPLAY_PASSED"
SESSION_PATH_REPLAY_BLOCKED = "SESSION_PATH_REPLAY_BLOCKED"


@dataclass(frozen=True)
class SessionPathReplayReport:
    schema_version: int
    source: str
    status: str
    candidate_count: int
    valid_candidate_count: int
    invalid_candidate_count: int
    reasons: tuple[str, ...]
    evidence: tuple[SessionPathReplayEvidence, ...]
    read_only: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence"] = [item.to_payload() for item in self.evidence]
        payload["read_only"] = True
        payload["is_order_action"] = False
        payload["broker_api_called"] = False
        payload["live_order_action"] = False
        payload["broker_order_action"] = False
        return payload


def build_session_path_replay_report(
    replay_candidates: Sequence[Mapping[str, Any]] | None,
    *,
    default_target_pct: float = 4.0,
    metadata: Mapping[str, Any] | None = None,
) -> SessionPathReplayReport:
    """Build read-only session-path replay evidence for replay candidate rows.

    This is the EDGE-91A wiring point. It accepts already-replayed candidate
    rows and emits a deterministic evidence report. It does not import runtime,
    dashboard, broker, execution, strategy, or ranking modules.
    """

    rows = tuple(replay_candidates or ())
    evidence = tuple(
        build_session_path_replay_evidence(
            candidate_id=_pick_text(row, "candidate_id", "id"),
            symbol=_pick_text(row, "symbol", "instrument", "tradingsymbol"),
            entry_time=_pick_text(row, "entry_time", "entry_timestamp", "timestamp"),
            exit_time=_pick_text(row, "exit_time", "exit_timestamp"),
            entry_price=_pick_value(row, "entry_price", "entry_ltp", "entry"),
            price_path=_pick_price_path(row),
            target_pct=_pick_float(row, "target_pct", default=default_target_pct),
            top_mover_rank=_pick_optional_int(row, "top_mover_rank", "rank"),
            relative_strength_percentile=_pick_value(row, "relative_strength_percentile", "rs_percentile"),
            regime_at_entry=_pick_text(row, "regime_at_entry", "entry_regime", "regime"),
            metadata=_pick_metadata(row),
        )
        for row in rows
    )
    reasons = tuple(sorted({item.reason for item in evidence if item.reason != OK_REASON}))
    invalid_count = sum(1 for item in evidence if not item.valid)
    status = SESSION_PATH_REPLAY_BLOCKED if invalid_count else SESSION_PATH_REPLAY_PASSED
    return SessionPathReplayReport(
        schema_version=SESSION_PATH_REPLAY_REPORT_SCHEMA_VERSION,
        source=SESSION_PATH_REPLAY_REPORT_SOURCE,
        status=status,
        candidate_count=len(evidence),
        valid_candidate_count=sum(1 for item in evidence if item.valid),
        invalid_candidate_count=invalid_count,
        reasons=reasons,
        evidence=evidence,
        metadata={
            "default_target_pct": float(default_target_pct),
            "evidence_only": True,
            "does_not_rank_candidates": True,
            "does_not_change_execution": True,
            **dict(metadata or {}),
        },
    )


def _pick_value(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _pick_text(row: Mapping[str, Any], *keys: str) -> str | None:
    value = _pick_value(row, *keys)
    if value is None:
        return None
    return str(value)


def _pick_float(row: Mapping[str, Any], *keys: str, default: float) -> float:
    value = _pick_value(row, *keys)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pick_optional_int(row: Mapping[str, Any], *keys: str) -> int | None:
    value = _pick_value(row, *keys)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pick_price_path(row: Mapping[str, Any]) -> Sequence[float | int | str] | None:
    value = _pick_value(row, "price_path", "prices_after_entry", "ltp_path", "replay_prices")
    if value is None:
        return None
    if isinstance(value, (str, bytes)):
        return None
    try:
        return tuple(value)
    except TypeError:
        return None


def _pick_metadata(row: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = row.get("metadata")
    base = dict(raw) if isinstance(raw, Mapping) else {}
    for key in ("strategy", "side", "source", "timeframe"):
        if key in row:
            base[key] = row[key]
    return base
