from __future__ import annotations

import json
import os
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
    isolated_root = os.getenv("UPSTOX_UI_SNAPSHOT_ROOT", "").strip()
    if isolated_root:
        # An explicit root is an isolation boundary for offline validation.  Do
        # not fall through to the live capture directory when it is supplied.
        return [Path(isolated_root).expanduser() / day / SNAPSHOT_NAME]
    return [PRIMARY_BASE_DIR / day / SNAPSHOT_NAME, FALLBACK_BASE_DIR / day / SNAPSHOT_NAME]


def load_upstox_option_chain_snapshot(*, now: datetime | None = None, stale_after_sec: float = 5.0) -> UpstoxSnapshot:
    """Read the Upstox UI snapshot only. Never authenticates, subscribes, reconnects, or mutates capture state."""
    now = now or datetime.now()
    path = next((p for p in _candidate_paths(now) if p.exists()), None)
    if path is None:
        return UpstoxSnapshot("missing", None, None, {}, "Upstox live snapshot unavailable")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return UpstoxSnapshot("error", str(path), None, {}, "snapshot_payload_not_object")
        written_epoch = float(payload.get("written_epoch") or 0.0)
        age = max(0.0, now.timestamp() - written_epoch) if written_epoch else None
        if age is None or age > stale_after_sec:
            status = "stale"
        else:
            chains = payload.get("chains")
            subscribed_count = int(payload.get("subscribed_count") or 0)
            observed_count = int(payload.get("observed_count") or 0)
            has_rows = isinstance(chains, dict) and any(
                isinstance(chain, dict) and isinstance(chain.get("rows"), list) and chain["rows"]
                for chain in chains.values()
            )
            if not has_rows:
                return UpstoxSnapshot("incomplete", str(path), age, payload, "snapshot_has_no_option_chain_rows")
            if subscribed_count and observed_count < subscribed_count:
                return UpstoxSnapshot("incomplete", str(path), age, payload, "snapshot_observation_incomplete")
            status = "fresh"
        return UpstoxSnapshot(status, str(path), age, payload)
    except Exception as exc:
        return UpstoxSnapshot("error", str(path), None, {}, f"snapshot_read_error:{type(exc).__name__}")
