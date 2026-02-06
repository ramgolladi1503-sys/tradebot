from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from config import config as cfg


CALENDAR_PATH = Path("data/calendar_events.json")
SHOCK_PATH = Path("data/news_shock.json")


@dataclass
class CalendarEvent:
    name: str
    ts_ist: str
    importance: int
    category: str


def _atomic_write(path: Path, payload: dict):
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(path)


class NewsCalendar:
    def __init__(self, calendar_path: Path = CALENDAR_PATH):
        self.calendar_path = calendar_path
        self._events: list[CalendarEvent] = []
        self._last_load = None
        self._tz = ZoneInfo("Asia/Kolkata")
        self._load()

    def _load(self):
        try:
            if not self.calendar_path.exists():
                self._events = []
                return
            raw = json.loads(self.calendar_path.read_text())
            events = []
            for ev in raw:
                try:
                    events.append(
                        CalendarEvent(
                            name=str(ev.get("name")),
                            ts_ist=str(ev.get("ts_ist")),
                            importance=int(ev.get("importance", 1)),
                            category=str(ev.get("category", "UNKNOWN")),
                        )
                    )
                except Exception:
                    continue
            self._events = events
            self._last_load = datetime.now(self._tz)
        except Exception:
            self._events = []

    def _minutes_to_event(self, ev: CalendarEvent) -> Optional[float]:
        try:
            ts = datetime.fromisoformat(ev.ts_ist)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=self._tz)
            now = datetime.now(self._tz)
            return (ts - now).total_seconds() / 60.0
        except Exception:
            return None

    def _importance_weight(self, importance: int) -> float:
        # Map 1..5 to 0.2..1.0
        imp = max(1, min(5, int(importance)))
        return imp / 5.0

    def get_shock(self) -> Dict[str, Any]:
        # Reload daily
        try:
            if self._last_load is None:
                self._load()
            else:
                now = datetime.now(self._tz)
                if now.date() != self._last_load.date():
                    self._load()
        except Exception:
            pass

        pre_decay = float(getattr(cfg, "NEWS_PRE_DECAY_MINUTES", 180.0))
        post_decay = float(getattr(cfg, "NEWS_POST_DECAY_MINUTES", 120.0))

        best = {
            "shock_score": 0.0,
            "event_name": None,
            "minutes_to_event": None,
            "uncertainty_index": 0.0,
            "event_category": None,
            "event_importance": None,
        }

        for ev in self._events:
            minutes = self._minutes_to_event(ev)
            if minutes is None:
                continue
            weight = self._importance_weight(ev.importance)
            if minutes >= 0:
                score = weight * math.exp(-minutes / max(pre_decay, 1.0))
            else:
                score = weight * math.exp(-abs(minutes) / max(post_decay, 1.0))
            if score > best["shock_score"]:
                best = {
                    "shock_score": float(score),
                    "event_name": ev.name,
                    "minutes_to_event": float(minutes),
                    "uncertainty_index": float(min(1.0, score * (1.0 + (ev.importance - 3) * 0.1))),
                    "event_category": ev.category,
                    "event_importance": ev.importance,
                }

        _atomic_write(SHOCK_PATH, {"timestamp": datetime.now(self._tz).isoformat(), **best})
        return best

