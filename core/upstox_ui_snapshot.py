from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

SNAPSHOT_NAME = "upstox_live_option_chain_snapshot.json"


def build_option_chain_snapshot(*, latest_by_key: Mapping[str, Mapping[str, Any]], metadata_by_key: Mapping[str, Mapping[str, Any]], subscribed_count: int, written_epoch: float | None = None) -> dict[str, Any]:
    chains: dict[str, dict[str, Any]] = {}
    for key, tick in latest_by_key.items():
        meta = dict(metadata_by_key.get(key) or {})
        root = str(meta.get("root") or "").upper()
        side = str(meta.get("side") or "").upper()
        strike = meta.get("strike")
        if root not in {"NIFTY", "BANKNIFTY", "SENSEX"} or side not in {"CE", "PE"} or strike is None:
            continue
        chain = chains.setdefault(root, {"expiry": meta.get("expiry"), "rows_by_strike": {}})
        row = chain["rows_by_strike"].setdefault(str(strike), {"strike": float(strike)})
        prefix = side.lower()
        for field in ("ltp", "bid", "ask", "vol", "oi", "depth", "received_epoch", "exchange_epoch"):
            row[f"{prefix}_{field}"] = tick.get(field)
    normalized: dict[str, Any] = {}
    for root, chain in chains.items():
        rows = sorted(chain.pop("rows_by_strike").values(), key=lambda row: float(row["strike"]))
        normalized[root] = {"expiry": chain.get("expiry"), "rows": rows}
    now = float(written_epoch if written_epoch is not None else time.time())
    fresh_ticks = [float(t.get("received_epoch") or 0.0) for t in latest_by_key.values() if t.get("received_epoch")]
    return {
        "schema_version": 1,
        "source": "UPSTOX_DAILY_CAPTURE_V1",
        "read_only": True,
        "broker_write_authority": False,
        "order_authority": False,
        "written_epoch": now,
        "subscribed_count": int(subscribed_count),
        "observed_count": len(latest_by_key),
        "last_receive_epoch": max(fresh_ticks) if fresh_ticks else None,
        "chains": normalized,
    }


def write_snapshot_atomic(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(dict(payload), sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(target)
