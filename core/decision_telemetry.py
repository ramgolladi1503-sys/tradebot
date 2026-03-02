"""Decision telemetry helpers for per-scan observability.

Migration note:
- Adds compact per-scan summaries for candidate generation.
- Intended for diagnostics only; does not alter strategy decisions.
"""

from __future__ import annotations

from core.paths import data_root, logs_dir
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Mapping

from config import config as cfg

logger = logging.getLogger(__name__)


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def build_scan_summary(
    *,
    symbol: str,
    total_candidates: int,
    accepted: int,
    rejected_by_reason: Mapping[str, int] | None,
    mode: str | None = None,
    profile_name: str | None = None,
) -> dict:
    rejected_map = {
        str(k): int(v)
        for k, v in (rejected_by_reason or {}).items()
        if str(k).strip() and int(v) > 0
    }
    rejected_total = int(sum(rejected_map.values()))
    ts_epoch = datetime.now(tz=timezone.utc).timestamp()
    top_symbols_rejected = {}
    if rejected_total > 0 and symbol:
        top_symbols_rejected[str(symbol)] = rejected_total
    return {
        "ts_epoch": float(ts_epoch),
        "ts_utc": datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat(),
        "symbol": str(symbol or ""),
        "mode": str(mode or ""),
        "profile": str(profile_name or ""),
        "total_candidates": int(max(0, total_candidates)),
        "accepted": int(max(0, accepted)),
        "rejected_by_reason": rejected_map,
        "top_symbols_rejected": top_symbols_rejected,
    }


def emit_scan_summary(summary: dict) -> None:
    if not bool(getattr(cfg, "DECISION_TELEMETRY_ENABLE", True)):
        return
    payload = dict(summary or {})
    if not payload:
        return

    compact = (
        "[DECISION_SCAN] "
        f"symbol={payload.get('symbol')} "
        f"mode={payload.get('mode')} "
        f"profile={payload.get('profile')} "
        f"total_candidates={payload.get('total_candidates')} "
        f"accepted={payload.get('accepted')} "
        f"rejected_by_reason={payload.get('rejected_by_reason')} "
        f"top_symbols_rejected={payload.get('top_symbols_rejected')}"
    )
    logger.info(compact)

    try:
        jsonl_path = Path(
            str(getattr(cfg, "DECISION_SCAN_SUMMARY_JSONL_PATH", str(logs_dir() / "decision_scan_summary.jsonl")))
        )
        latest_path = Path(
            str(getattr(cfg, "DECISION_SCAN_SUMMARY_LATEST_PATH", str(logs_dir() / "decision_scan_summary_latest.json")))
        )
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")
        _atomic_write_json(latest_path, payload)
    except Exception as exc:  # pragma: no cover - diagnostics fallback
        logger.warning("decision_scan_summary_persist_failed err=%s", f"{type(exc).__name__}:{exc}")
