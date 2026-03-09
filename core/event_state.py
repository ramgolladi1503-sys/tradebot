from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

from core.paths import logs_dir


def _parse_epoch(ts_value: Any) -> float | None:
    if ts_value is None:
        return None
    if isinstance(ts_value, (int, float)):
        raw = float(ts_value)
        if raw > 1_000_000_000_000:
            raw /= 1000.0
        return raw
    text = str(ts_value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc).timestamp()
    except Exception:
        return None


def _dedupe_bucket(ts_value: Any) -> int:
    epoch = _parse_epoch(ts_value)
    if epoch is None:
        return 0
    return int(epoch)


@dataclass
class EventState:
    seen_event_ids: set[str] = field(default_factory=set)
    seen_order_ids: set[str] = field(default_factory=set)
    seen_trade_ids: set[str] = field(default_factory=set)
    last_recon_id: str | None = None
    _seen_fallback: set[tuple[str, str, str, int]] = field(default_factory=set)

    def ingest(self, events_iter: Iterable[dict[str, Any]]) -> "EventState":
        for row in events_iter:
            if not isinstance(row, dict):
                continue
            event_type = str(row.get("type") or "").strip()
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}

            event_id = str(payload.get("event_id") or row.get("event_id") or "").strip()
            if event_id:
                if event_id in self.seen_event_ids:
                    continue
                self.seen_event_ids.add(event_id)
            else:
                order_id = str(payload.get("order_id") or "").strip() or "-"
                trade_id = str(payload.get("trade_id") or "").strip() or "-"
                bucket = _dedupe_bucket(row.get("ts"))
                fallback_key = (event_type, order_id, trade_id, bucket)
                if fallback_key in self._seen_fallback:
                    continue
                self._seen_fallback.add(fallback_key)

            order_id = str(payload.get("order_id") or "").strip()
            if order_id:
                self.seen_order_ids.add(order_id)

            trade_id = str(payload.get("trade_id") or "").strip()
            if trade_id:
                self.seen_trade_ids.add(trade_id)

            recon_id = str(
                payload.get("recon_id")
                or payload.get("reconciliation_id")
                or row.get("recon_id")
                or row.get("reconciliation_id")
                or ""
            ).strip()
            if recon_id:
                self.last_recon_id = recon_id
        return self


def _events_path_for_desk(desk_id: str) -> Path:
    _ = str(desk_id or "DEFAULT")  # kept for interface compatibility
    return logs_dir() / "events.jsonl"


def build_state_from_events(desk_id: str) -> EventState:
    path = _events_path_for_desk(desk_id)
    state = EventState()
    if not path.exists():
        return state
    with path.open("r", encoding="utf-8") as handle:
        rows: list[dict[str, Any]] = []
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return state.ingest(rows)
