from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dt_time
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from config import config as cfg


@dataclass(frozen=True)
class SessionSpec:
    tz: ZoneInfo
    open_time: dt_time
    close_time: dt_time
    name: str
    segment: str


_IST = ZoneInfo("Asia/Kolkata")


def _default_sessions() -> Dict[str, SessionSpec]:
    return {
        "NSE_EQ": SessionSpec(_IST, dt_time(9, 15), dt_time(15, 30), "NSE Equity", "NSE_EQ"),
        "NSE_FNO": SessionSpec(_IST, dt_time(9, 15), dt_time(15, 30), "NSE F&O", "NSE_FNO"),
        "CDS": SessionSpec(_IST, dt_time(9, 0), dt_time(17, 0), "Currency", "CDS"),
        "MCX": SessionSpec(_IST, dt_time(9, 0), dt_time(23, 30), "Commodities", "MCX"),
    }


def _apply_overrides(sessions: Dict[str, SessionSpec]) -> Dict[str, SessionSpec]:
    overrides = getattr(cfg, "SESSION_OVERRIDES", {}) or {}
    out = dict(sessions)
    for segment, spec in overrides.items():
        if not isinstance(spec, dict):
            continue
        base = out.get(segment)
        if not base:
            base = SessionSpec(_IST, dt_time(9, 0), dt_time(17, 0), segment, segment)
        open_raw = spec.get("open") or spec.get("open_time")
        close_raw = spec.get("close") or spec.get("close_time")
        name = spec.get("name") or base.name
        open_time = _parse_time(open_raw) or base.open_time
        close_time = _parse_time(close_raw) or base.close_time
        out[segment] = SessionSpec(_IST, open_time, close_time, name, segment)
    return out


def _parse_time(val: Optional[str]) -> Optional[dt_time]:
    if not val:
        return None
    if isinstance(val, dt_time):
        return val
    s = str(val).strip()
    if not s:
        return None
    parts = s.split(":")
    try:
        hh = int(parts[0])
        mm = int(parts[1]) if len(parts) > 1 else 0
        return dt_time(hh, mm)
    except Exception:
        return None


def get_session(segment: Optional[str] = None) -> SessionSpec:
    sessions = _apply_overrides(_default_sessions())
    seg = segment or getattr(cfg, "DEFAULT_SEGMENT", "NSE_FNO")
    return sessions.get(seg, sessions["NSE_FNO"])


def is_open(now_dt: Optional[datetime] = None, segment: Optional[str] = None) -> bool:
    sess = get_session(segment)
    now_dt = now_dt or datetime.now(tz=sess.tz)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=sess.tz)
    if now_dt.weekday() >= 5:
        return False
    open_dt = now_dt.replace(hour=sess.open_time.hour, minute=sess.open_time.minute, second=0, microsecond=0)
    close_dt = now_dt.replace(hour=sess.close_time.hour, minute=sess.close_time.minute, second=0, microsecond=0)
    return open_dt <= now_dt <= close_dt


def minutes_since_open(now_dt: Optional[datetime] = None, segment: Optional[str] = None) -> int:
    sess = get_session(segment)
    now_dt = now_dt or datetime.now(tz=sess.tz)
    if not is_open(now_dt, segment):
        return 0
    open_dt = now_dt.replace(hour=sess.open_time.hour, minute=sess.open_time.minute, second=0, microsecond=0)
    return max(0, int((now_dt - open_dt).total_seconds() / 60))


def minutes_to_close(now_dt: Optional[datetime] = None, segment: Optional[str] = None) -> int:
    sess = get_session(segment)
    now_dt = now_dt or datetime.now(tz=sess.tz)
    if not is_open(now_dt, segment):
        return 0
    close_dt = now_dt.replace(hour=sess.close_time.hour, minute=sess.close_time.minute, second=0, microsecond=0)
    return max(0, int((close_dt - now_dt).total_seconds() / 60))
