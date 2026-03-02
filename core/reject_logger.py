from __future__ import annotations

from core.paths import data_root, logs_dir
import json
from pathlib import Path
from typing import Iterable

from config import config as cfg
from core.time_utils import now_ist, now_utc_epoch


def _reject_log_path() -> Path:
    return Path(getattr(cfg, "REJECT_REASONS_LOG_PATH", str(logs_dir() / "reject_reasons.jsonl")))


def append_reject_reasons(
    *,
    symbol: str | None,
    strategy: str | None,
    reasons: Iterable[str] | None,
    mode: str | None,
    source: str = "decision",
    extra: dict | None = None,
) -> None:
    rows = []
    seen = set()
    for raw_reason in (reasons or []):
        if raw_reason is None:
            continue
        reason = str(raw_reason).strip()
        if (not reason) or (reason.lower() == "none"):
            continue
        key = reason.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(reason)
    if not rows:
        return
    ts_epoch = now_utc_epoch()
    ts_ist = now_ist().isoformat()
    payload_extra = dict(extra or {})
    path = _reject_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for reason in rows:
                rec = {
                    "ts_epoch": ts_epoch,
                    "ts_ist": ts_ist,
                    "symbol": str(symbol or "").upper() or "UNKNOWN",
                    "strategy": str(strategy or "UNKNOWN"),
                    "reason": reason,
                    "reason_code": reason,
                    "mode": str(mode or getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
                    "source": str(source),
                    "details": payload_extra,
                }
                handle.write(json.dumps(rec, ensure_ascii=True) + "\n")
    except Exception:
        pass
    try:
        from core.storage import emit_gate_rejected_event

        missing_fields = payload_extra.get("missing_fields") if isinstance(payload_extra.get("missing_fields"), list) else []
        gate_name = payload_extra.get("gate_name") if payload_extra.get("gate_name") is not None else source
        for reason in rows:
            emit_gate_rejected_event(
                symbol=str(symbol or "").upper() or None,
                strategy=str(strategy or "") or None,
                reason_code=str(reason),
                mode=str(mode or getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
                gate_name=str(gate_name) if gate_name is not None else None,
                data_source=str(source),
                missing_fields=[str(x) for x in missing_fields if str(x).strip()],
                features_summary=payload_extra,
            )
    except Exception:
        pass
