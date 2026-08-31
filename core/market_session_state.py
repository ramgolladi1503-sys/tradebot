"""Authoritative market-session state and read-only feed expectations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from core.market_calendar import IN_HOLIDAYS
from core.session_calendar import get_session
from core.time_utils import IST_TZ, now_ist

SESSION_STATE_UNKNOWN = "SESSION_STATE_UNKNOWN"
MARKET_CLOSED = "MARKET_CLOSED"
PREMARKET = "PREMARKET"
MARKET_OPEN = "MARKET_OPEN"
POSTMARKET = "POSTMARKET"

_AUTHORITY = "repository_session_calendar_and_holiday_authority"


@dataclass(frozen=True)
class MarketSessionPolicy:
    market_state: str
    session_date: str
    observed_at: str
    market_state_authority: str
    fresh_ticks_required: bool
    persistence_advancement_required: bool
    strategies_active: bool
    cas_active: bool
    ranking_active: bool
    advisory_emission_active: bool
    feed_staleness_timer_active: bool
    feed_restart_allowed: bool
    restart_storm_counter_increment_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_date": self.session_date,
            "observed_at": self.observed_at,
            "market_state": self.market_state,
            "market_state_authority": self.market_state_authority,
            "fresh_ticks_required": self.fresh_ticks_required,
            "persistence_advancement_required": self.persistence_advancement_required,
            "strategies_active": self.strategies_active,
            "cas_active": self.cas_active,
            "ranking_active": self.ranking_active,
            "advisory_emission_active": self.advisory_emission_active,
            "feed_staleness_timer_active": self.feed_staleness_timer_active,
            "feed_restart_allowed": self.feed_restart_allowed,
            "restart_storm_counter_increment_allowed": self.restart_storm_counter_increment_allowed,
        }


def _state_for_time(now: datetime, *, segment: str) -> str:
    session = get_session(segment)
    if now.weekday() >= 5 or now.date() in IN_HOLIDAYS:
        return MARKET_CLOSED
    premarket = time(9, 0)
    current = now.time()
    if current < premarket:
        return MARKET_CLOSED
    if current < session.open_time:
        return PREMARKET
    if current <= session.close_time:
        return MARKET_OPEN
    return POSTMARKET


def derive_market_session_policy(*, now: datetime | None = None, segment: str = "NSE_FNO") -> MarketSessionPolicy:
    observed = now or now_ist()
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=IST_TZ)
    else:
        observed = observed.astimezone(IST_TZ)
    try:
        state = _state_for_time(observed, segment=segment)
    except Exception:
        state = SESSION_STATE_UNKNOWN
    strict = state == MARKET_OPEN
    return MarketSessionPolicy(
        market_state=state,
        session_date=observed.date().isoformat(),
        observed_at=observed.isoformat(),
        market_state_authority=_AUTHORITY if state != SESSION_STATE_UNKNOWN else "unknown",
        fresh_ticks_required=strict,
        persistence_advancement_required=strict,
        strategies_active=strict,
        cas_active=strict,
        ranking_active=strict,
        advisory_emission_active=strict,
        feed_staleness_timer_active=strict,
        feed_restart_allowed=strict,
        restart_storm_counter_increment_allowed=strict,
    )


def current_session_identity(*, source_sha: str = "") -> dict[str, str]:
    policy = derive_market_session_policy()
    return {"session_date": policy.session_date, "source_sha": source_sha}
