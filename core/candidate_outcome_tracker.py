from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from core.candidate_journal import _fallback_used as _journal_fallback_used
from core.candidate_outcome_truth import (
    AMBIGUOUS_SAME_BAR,
    CANDIDATE_OUTCOME_TRUTH_SCHEMA_VERSION,
    CandidateOutcomeInput,
    CandidateOutcomeTruth,
    INVALID_INPUT,
    NO_OBSERVATIONS,
    NOT_EXECUTABLE,
    PriceObservation,
    build_candidate_outcome_truth,
)
from core.paths import runtime_dir

logger = logging.getLogger(__name__)

TRACKER_SCHEMA_VERSION = 1
DEFAULT_WINDOWS_SEC = (300, 600, 900, 1800)
_DEFAULT_TRACKER_SUBDIR = "candidates"
_DEFAULT_TRACKER_FILENAME = "candidate_outcomes.jsonl"


@dataclass(frozen=True)
class CandidateOutcomeTrackerResult:
    schema_version: int
    generated_by: str
    candidate_count: int
    observation_source: str
    outcome_rows: tuple[dict[str, Any], ...]
    read_only: bool = True
    append: bool = True

    @property
    def safety(self) -> dict[str, object]:
        return {
            "read_only": self.read_only,
            "append": self.append,
            "is_order_action": False,
            "broker_api_called": False,
            "live_order_allowed": False,
            "live_order_action": False,
            "broker_order_action": False,
            "runtime_wired": False,
            "external_services_used": False,
            "proves_trading_edge": False,
        }

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["safety"] = dict(self.safety)
        return payload


def candidate_outcome_tracker_path() -> Path:
    try:
        from config import config as cfg

        raw = str(getattr(cfg, "CANDIDATE_OUTCOME_TRACKER_PATH", "") or "").strip()
    except Exception:
        raw = ""
    if raw:
        return Path(raw).expanduser()
    return runtime_dir() / _DEFAULT_TRACKER_SUBDIR / _DEFAULT_TRACKER_FILENAME


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    return number


def _window_secs(windows_sec: Iterable[int] | None) -> tuple[int, ...]:
    windows = tuple(int(window) for window in (windows_sec or DEFAULT_WINDOWS_SEC) if int(window) > 0)
    return windows or DEFAULT_WINDOWS_SEC


def _journal_key(row: Mapping[str, Any]) -> str:
    candidate_id = _text(row.get("candidate_id"))
    if candidate_id:
        return candidate_id
    trade_id = _text(row.get("trade_id"))
    if trade_id:
        return trade_id
    return ""


def _is_fallback_candidate(row: Mapping[str, Any]) -> bool:
    return bool(_journal_fallback_used(row))


def _is_executable_candidate_row(row: Mapping[str, Any]) -> bool:
    if not isinstance(row, Mapping):
        return False
    if _is_fallback_candidate(row):
        return False
    if bool(row.get("execution_truth_blocked")) or bool(row.get("execution_truth_blockers")):
        return False
    reportable_executable = bool(row.get("reportable_executable"))
    execution_allowed = bool(row.get("execution_allowed"))
    permission = _text(row.get("permission")).upper()
    final_action = _text(row.get("final_action")).upper()
    execution_status = _text(row.get("execution_status")).lower()
    candidate_status = _text(row.get("candidate_status")).lower()
    readiness = _text(row.get("readiness")).upper()
    execution_entry_status = _text(row.get("execution_entry_status")).lower()
    if not (reportable_executable and execution_allowed):
        return False
    if permission != "EXECUTE" or final_action != "EXECUTE":
        return False
    if execution_status != "executable":
        return False
    if readiness != "READY":
        return False
    if execution_entry_status != "executable":
        return False
    if candidate_status not in {"executable", "near_executable"}:
        return False
    return True


def _candidate_input_from_journal_row(row: Mapping[str, Any], *, window_sec: int) -> CandidateOutcomeInput:
    signal_epoch = _float(row.get("signal_epoch"))
    if signal_epoch is None:
        signal_epoch = _float(row.get("created_at_epoch"))
    if signal_epoch is None:
        signal_epoch = _float(row.get("entry_epoch"))
    return CandidateOutcomeInput(
        candidate_id=_text(row.get("candidate_id")) or None,
        trade_id=_text(row.get("trade_id")) or None,
        strategy_family=_text(row.get("strategy_family")),
        symbol=_text(row.get("symbol")),
        index=_text(row.get("index")) or None,
        regime=_text(row.get("regime")) or None,
        expiry_type=_text(row.get("expiry_type")) or None,
        signal_epoch=signal_epoch,
        entry_price=_float(row.get("entry_price")) if row.get("entry_price") not in (None, "", "None") else _float(row.get("entry")),
        stop_loss_price=_float(row.get("stop_loss_price")) if row.get("stop_loss_price") not in (None, "", "None") else _float(row.get("stop_loss")),
        target_price=_float(row.get("target_price")) if row.get("target_price") not in (None, "", "None") else _float(row.get("target")),
        timeout_epoch=(signal_epoch + float(window_sec)) if signal_epoch is not None else None,
        side=_text(row.get("side")) or None,
        direction=_text(row.get("direction")) or None,
        feed_truth_state=_text(row.get("feed_truth_state")) or None,
        reportable_executable=_is_executable_candidate_row(row),
        execution_allowed=_is_executable_candidate_row(row),
        estimated_cost_r=_float(row.get("estimated_cost_r")),
        estimated_cost_abs=_float(row.get("estimated_cost_abs")),
    )


def _coerce_observation(value: PriceObservation | Mapping[str, Any]) -> PriceObservation | None:
    if isinstance(value, PriceObservation):
        return value
    if not isinstance(value, Mapping):
        return None
    observed_epoch = _float(value.get("observed_epoch"))
    ltp = _float(value.get("ltp"))
    if observed_epoch is None or ltp is None:
        return None
    return PriceObservation(
        observed_epoch=observed_epoch,
        ltp=ltp,
        bid=_float(value.get("bid")),
        ask=_float(value.get("ask")),
        spread=_float(value.get("spread")),
        source=_text(value.get("source")) or None,
        quote_age_sec=_float(value.get("quote_age_sec")),
    )


def _normalize_observation_rows(
    observations: Iterable[PriceObservation | Mapping[str, Any]] | None,
) -> list[PriceObservation]:
    normalized = [_coerce_observation(item) for item in (observations or [])]
    return [item for item in normalized if item is not None]


def _observations_by_key(
    observations: Mapping[str, Iterable[PriceObservation | Mapping[str, Any]]] | Iterable[Mapping[str, Any]] | None,
) -> dict[str, list[PriceObservation]]:
    if observations is None:
        return {}
    if isinstance(observations, Mapping):
        grouped: dict[str, list[PriceObservation]] = {}
        for key, rows in observations.items():
            normalized = _normalize_observation_rows(rows)
            if key:
                grouped[str(key)] = normalized
        return grouped
    grouped: dict[str, list[PriceObservation]] = {}
    for row in observations:
        if not isinstance(row, Mapping):
            continue
        key = _journal_key(row)
        if not key:
            continue
        normalized = _coerce_observation(row)
        if normalized is None:
            continue
        grouped.setdefault(key, []).append(normalized)
    return grouped


def _row_observations(
    row: Mapping[str, Any],
    grouped_observations: Mapping[str, Sequence[PriceObservation]] | None,
) -> list[PriceObservation]:
    key = _journal_key(row)
    if not key or not grouped_observations:
        return []
    rows = grouped_observations.get(key) or []
    return list(rows)


def build_candidate_outcome_records(
    journal_rows: Iterable[Mapping[str, Any]] | None,
    observations: Mapping[str, Iterable[PriceObservation | Mapping[str, Any]]] | Iterable[Mapping[str, Any]] | None = None,
    *,
    windows_sec: Iterable[int] | None = None,
    observation_source: str = "in_memory",
) -> list[dict[str, Any]]:
    windows = _window_secs(windows_sec)
    candidate_rows = [dict(row) for row in (journal_rows or []) if isinstance(row, Mapping)]
    grouped_observations = _observations_by_key(observations)
    outcome_rows: list[dict[str, Any]] = []
    for row in candidate_rows:
        for window_sec in windows:
            candidate_input = _candidate_input_from_journal_row(row, window_sec=window_sec)
            candidate_observations = _row_observations(row, grouped_observations)
            truth = build_candidate_outcome_truth(candidate_input, candidate_observations)
            payload = truth.to_payload()
            payload.update(
                {
                    "window_sec": int(window_sec),
                    "observation_source": observation_source,
                    "fallback_used": bool(row.get("fallback_used")),
                    "candidate_row_kind": row.get("row_kind"),
                    "candidate_class": row.get("candidate_class"),
                    "candidate_origin": row.get("candidate_origin"),
                    "quote_source": row.get("quote_source"),
                    "source_reportable_executable": bool(row.get("reportable_executable")),
                    "source_execution_allowed": bool(row.get("execution_allowed")),
                }
            )
            outcome_rows.append(payload)
    outcome_rows.sort(
        key=lambda item: (
            _text(item.get("candidate_id")),
            _text(item.get("trade_id")),
            int(item.get("window_sec") or 0),
        )
    )
    return outcome_rows


def _write_jsonl_rows(path: Path, rows: Iterable[Mapping[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), sort_keys=True, default=str) + "\n")
    return path


def write_candidate_outcome_records(
    rows: Iterable[Mapping[str, Any]],
    *,
    path: str | Path | None = None,
) -> tuple[Path, bool]:
    target = Path(path).expanduser() if path is not None else candidate_outcome_tracker_path()
    try:
        written = _write_jsonl_rows(target, rows)
    except Exception as exc:
        logger.warning("candidate_outcome_tracker_write_failed path=%s error=%s", target, exc)
        return target, False
    return written, True


def track_candidate_outcomes(
    journal_rows: Iterable[Mapping[str, Any]] | None,
    observations: Mapping[str, Iterable[PriceObservation | Mapping[str, Any]]] | Iterable[Mapping[str, Any]] | None = None,
    *,
    path: str | Path | None = None,
    windows_sec: Iterable[int] | None = None,
    observation_source: str = "in_memory",
) -> tuple[list[dict[str, Any]], Path, bool]:
    outcome_rows = build_candidate_outcome_records(
        journal_rows,
        observations=observations,
        windows_sec=windows_sec,
        observation_source=observation_source,
    )
    written_path, ok = write_candidate_outcome_records(outcome_rows, path=path)
    return outcome_rows, written_path, ok


__all__ = [
    "AMBIGUOUS_SAME_BAR",
    "CANDIDATE_OUTCOME_TRUTH_SCHEMA_VERSION",
    "CandidateOutcomeTrackerResult",
    "DEFAULT_WINDOWS_SEC",
    "INVALID_INPUT",
    "NO_OBSERVATIONS",
    "NOT_EXECUTABLE",
    "STOP_HIT",
    "TARGET_HIT",
    "TIMEOUT",
    "build_candidate_outcome_records",
    "candidate_outcome_tracker_path",
    "track_candidate_outcomes",
    "write_candidate_outcome_records",
]
