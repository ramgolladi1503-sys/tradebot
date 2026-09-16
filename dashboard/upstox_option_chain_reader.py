from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PRIMARY_BASE_DIR = Path("/Volumes/TradeBotData/live market capture")
FALLBACK_BASE_DIR = Path(__file__).resolve().parents[1] / ".runtime" / "market_data"
SNAPSHOT_NAME = "upstox_live_option_chain_snapshot.json"


@dataclass(frozen=True)
class UpstoxSnapshot:
    status: str
    path: str | None
    age_sec: float | None
    payload: dict[str, Any]
    message: str = ""


def _candidate_paths(now: datetime) -> list[Path]:
    day = now.strftime("%Y-%m-%d")
    return [PRIMARY_BASE_DIR / day / SNAPSHOT_NAME, FALLBACK_BASE_DIR / day / SNAPSHOT_NAME]


def load_upstox_option_chain_snapshot(*, now: datetime | None = None, stale_after_sec: float = 5.0) -> UpstoxSnapshot:
    """Read the Upstox UI snapshot only. Never authenticates, subscribes, reconnects, or mutates capture state."""
    now = now or datetime.now()
    path = next((p for p in _candidate_paths(now) if p.exists()), None)
    if path is None:
        return UpstoxSnapshot("missing", None, None, {}, "Upstox live snapshot unavailable")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        written_epoch = float(payload.get("written_epoch") or 0.0)
        age = max(0.0, now.timestamp() - written_epoch) if written_epoch else None
        status = "fresh" if age is not None and age <= stale_after_sec else "stale"
        return UpstoxSnapshot(status, str(path), age, payload)
    except Exception as exc:
        return UpstoxSnapshot("error", str(path), None, {}, f"snapshot_read_error:{type(exc).__name__}")
