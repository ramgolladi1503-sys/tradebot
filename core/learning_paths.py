from __future__ import annotations

"""Canonical path helpers for suggestion/rejection learning feedback.

Migration note:
- Runtime canonical paths come from config/runtime roots.
- Legacy ./logs paths are still read as fallback for backward compatibility.
"""

from pathlib import Path

from config import config as cfg
from core.paths import logs_dir


def _cfg_path(name: str, default: str) -> Path:
    raw = str(getattr(cfg, name, default) or "").strip()
    return Path(raw)


def _unique(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def canonical_suggestions_log_path() -> Path:
    return _cfg_path("SUGGESTIONS_LOG_PATH", str(logs_dir() / "suggestions.jsonl"))


def suggestion_log_paths() -> list[Path]:
    return _unique(
        [
            canonical_suggestions_log_path(),
            Path("logs/suggestions.jsonl"),
        ]
    )


def canonical_suggestion_eval_log_path() -> Path:
    return _cfg_path("SUGGESTION_EVAL_LOG_PATH", str(logs_dir() / "suggestion_eval.jsonl"))


def suggestion_eval_log_paths() -> list[Path]:
    return _unique(
        [
            canonical_suggestion_eval_log_path(),
            Path("logs/suggestion_eval.jsonl"),
        ]
    )


def canonical_rejected_candidates_path() -> Path:
    return _cfg_path("REJECTED_CANDIDATES_LOG_PATH", str(logs_dir() / "rejected_candidates.jsonl"))


def rejected_candidates_paths() -> list[Path]:
    desk_path = None
    try:
        desk_log_dir = str(getattr(cfg, "DESK_LOG_DIR", "") or "").strip()
        if desk_log_dir:
            desk_path = Path(desk_log_dir) / "blocked_candidates.jsonl"
    except Exception:
        desk_path = None
    out = [canonical_rejected_candidates_path(), Path("logs/rejected_candidates.jsonl")]
    if desk_path is not None:
        out.insert(0, desk_path)
    return _unique(out)


def blocked_tracking_path() -> Path:
    return _cfg_path("BLOCKED_TRACK_PATH", str(logs_dir() / "blocked_tracking.jsonl"))


def blocked_outcomes_path() -> Path:
    return _cfg_path("BLOCKED_OUTCOMES_PATH", str(logs_dir() / "blocked_outcomes.jsonl"))


def blocked_outcomes_processed_path() -> Path:
    return _cfg_path(
        "BLOCKED_OUTCOMES_PROCESSED_PATH",
        str(logs_dir() / "blocked_outcomes_processed.json"),
    )


def feedback_train_state_path() -> Path:
    return _cfg_path("FEEDBACK_TRAIN_STATE_PATH", str(logs_dir() / "feedback_train_state.json"))
