from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import logging

try:
    from config import config as cfg
except Exception:  # pragma: no cover - config import guard
    cfg = None

from core.option_entry import get_option_ltp_sla_sec

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntryContractViolation(Exception):
    code: str
    message: str
    evidence: dict[str, Any]

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


_EXPECTED_ENTRY_SOURCES = (
    "expected_entry",
    "mark_price",
    "entry_price_proxy",
    "suggested_entry",
    "current_ltp",
    "entry",
    "entry_price",
    "signal_price",
)

_FILL_ENTRY_SOURCES = (
    "fill_entry",
    "avg_fill_price",
    "fill_price",
    "execution_fill_price",
    "broker_avg_fill_price",
)

# "APPROVED or later" is interpreted as the execution-side lifecycle where
# order approval has happened and downstream states follow.
_REQUIRES_EXPECTED_ENTRY_STATES = {
    "APPROVED",
    "SENT",
    "ACKNOWLEDGED",
    "PARTIAL",
    "FILLED",
    "EXECUTED",
    "CLOSED",
}
_REQUIRES_FILL_ENTRY_STATES = {"FILLED"}

ENTRY_SOURCE_ENUM = {
    "ask",
    "bid",
    "mark",
    "mid",
    "last",
    "retained_prior_ask",
    "retained_prior_bid",
    "retained_prior_mark",
    "none",
}
EXECUTION_ENTRY_STATUSES = {"executable", "non_executable", "missing"}
DISPLAY_ENTRY_STATUSES = {"displayable", "non_executable", "missing"}
_UNTRUSTED_QUOTE_SOURCES = {"synthetic_index", "subscription_failed", "missing_ltp", "stale_ltp", "none"}


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if out != out:  # NaN guard
        return None
    return out


def _mid_price(bid: Any, ask: Any) -> float | None:
    bid_v = _safe_float(bid)
    ask_v = _safe_float(ask)
    if bid_v is None or ask_v is None:
        return None
    if bid_v <= 0 or ask_v <= 0:
        return None
    return (bid_v + ask_v) / 2.0


def _snapshot_option_quote(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    snapshot = row.get("snapshot")
    if not isinstance(snapshot, Mapping):
        return None
    option_quote = snapshot.get("option_quote")
    if isinstance(option_quote, Mapping):
        return option_quote
    return None


def _valid_positive_quote(value: Any) -> float | None:
    out = _safe_float(value)
    if out is None or out <= 0:
        return None
    return float(out)


def _safe_lower_text(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text or None


def _resolve_direction(side: Any = None, direction: Any = None) -> str:
    side_text = str(side or "").strip().upper()
    if side_text in {"BUY", "SELL"}:
        return side_text
    direction_text = str(direction or "").strip().upper()
    if direction_text in {"BUY", "LONG", "BUY_CALL", "BUY_PUT"}:
        return "BUY"
    if direction_text in {"SELL", "SHORT", "SELL_CALL", "SELL_PUT"}:
        return "SELL"
    return "BUY"


def _valid_quote_by_age(value: Any, quote_age_sec: float | None, max_age_sec: float | None) -> float | None:
    out = _valid_positive_quote(value)
    if out is None:
        return None
    if max_age_sec is None:
        return out
    age_val = _safe_float(quote_age_sec)
    if age_val is None or age_val < 0:
        return None
    if age_val > float(max_age_sec):
        return None
    return out


def _derive_entry_thresholds(
    *,
    mode: str | None,
    allow_stale_quotes: bool,
    market_open: bool | None,
) -> tuple[float, float]:
    option_sla = float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0))
    canonical_live_sla = float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5))
    market_open_flag = bool(True if market_open is None else market_open)
    execution_max_age_sec = float(
        get_option_ltp_sla_sec(
            mode,
            min(option_sla, canonical_live_sla),
            allow_stale_quotes=False,
            market_open=market_open_flag,
            expiry_lotto_mode=bool(getattr(cfg, "EXPIRY_LOTTO_MODE", False)),
        )
    )
    display_max_age_sec = float(
        get_option_ltp_sla_sec(
            mode,
            option_sla,
            allow_stale_quotes=bool(allow_stale_quotes),
            market_open=market_open_flag,
            expiry_lotto_mode=bool(getattr(cfg, "EXPIRY_LOTTO_MODE", False)),
        )
    )
    return execution_max_age_sec, display_max_age_sec


def build_entry_state(
    *,
    symbol: Any,
    expiry: Any,
    strike: Any,
    right: Any,
    side: Any = None,
    direction: Any = None,
    bid: Any = None,
    ask: Any = None,
    mark: Any = None,
    mid: Any = None,
    last: Any = None,
    quote_age_sec: Any = None,
    mode: str | None = None,
    allow_stale_quotes: bool = False,
    market_open: bool | None = None,
    instrument_matches: bool = True,
    quote_source: Any = None,
) -> dict[str, Any]:
    exec_max_age_sec, display_max_age_sec = _derive_entry_thresholds(
        mode=mode,
        allow_stale_quotes=allow_stale_quotes,
        market_open=market_open,
    )
    direction_key = _resolve_direction(side=side, direction=direction)
    quote_source_key = _safe_lower_text(quote_source) or "none"
    age_val = _safe_float(quote_age_sec)
    trusted_quote_source = quote_source_key not in _UNTRUSTED_QUOTE_SOURCES

    display_mid = _valid_positive_quote(mid)
    display_bid = _valid_quote_by_age(bid, age_val, display_max_age_sec)
    display_ask = _valid_quote_by_age(ask, age_val, display_max_age_sec)
    display_mark = _valid_quote_by_age(mark, age_val, display_max_age_sec)
    display_last = _valid_quote_by_age(last, age_val, display_max_age_sec)
    if display_mid is None and display_bid is not None and display_ask is not None:
        display_mid = (display_bid + display_ask) / 2.0

    execution_bid = _valid_quote_by_age(bid, age_val, exec_max_age_sec)
    execution_ask = _valid_quote_by_age(ask, age_val, exec_max_age_sec)
    execution_entry = execution_ask if direction_key == "BUY" else execution_bid
    execution_entry_source = "ask" if direction_key == "BUY" else "bid"
    execution_entry_status = "executable" if execution_entry is not None else (
        "non_executable" if any(v is not None for v in (display_mark, display_mid, display_last, display_bid, display_ask)) else "missing"
    )

    display_entry = execution_entry
    display_entry_source = execution_entry_source if execution_entry is not None else None
    display_entry_status = "displayable" if execution_entry is not None else "missing"
    entry_reason = (
        f"execution_from_{execution_entry_source}" if execution_entry is not None else None
    )
    entry_clear_reason = None

    if not instrument_matches:
        execution_entry = None
        execution_entry_source = "none"
        execution_entry_status = "missing"
        display_entry = None
        display_entry_source = "none"
        display_entry_status = "missing"
        entry_reason = None
        entry_clear_reason = "instrument_mismatch"
    elif not trusted_quote_source:
        execution_entry = None
        execution_entry_source = "none"
        execution_entry_status = "missing"
        display_entry = None
        display_entry_source = "none"
        display_entry_status = "missing"
        entry_reason = None
        entry_clear_reason = "quote_source_untrusted"
    elif display_entry is None:
        for candidate_value, candidate_source, candidate_reason in (
            (display_mark, "mark", "display_from_mark"),
            (display_mid, "mid", "display_from_mid"),
            (display_last, "last", "display_from_last"),
        ):
            if candidate_value is not None:
                display_entry = candidate_value
                display_entry_source = candidate_source
                display_entry_status = "displayable"
                entry_reason = candidate_reason
                break
        if display_entry is None:
            display_entry_source = "none"
            display_entry_status = "missing"
            if age_val is None or age_val < 0:
                entry_clear_reason = "invalid_quote_value"
            elif age_val > float(display_max_age_sec):
                entry_clear_reason = "stale_quote"
            elif any(_valid_positive_quote(v) is not None for v in (bid, ask, mark, mid, last)):
                entry_clear_reason = "invalid_quote_value"
            else:
                entry_clear_reason = "missing_executable_quote"

    if execution_entry is not None:
        execution_entry_source = execution_entry_source or ("ask" if direction_key == "BUY" else "bid")
    else:
        execution_entry_source = "none"
    if display_entry is not None:
        display_entry_source = display_entry_source or "none"
        entry_clear_reason = None
    else:
        display_entry_source = "none"

    out = {
        "execution_entry": execution_entry,
        "execution_entry_source": execution_entry_source,
        "execution_entry_status": execution_entry_status,
        "display_entry": display_entry,
        "display_entry_source": display_entry_source,
        "display_entry_status": display_entry_status,
        "entry_reason": entry_reason,
        "entry_clear_reason": entry_clear_reason,
        "entry": display_entry,
        "entry_status": display_entry_status,
        "entry_source": display_entry_source,
        "execution_max_age_sec": exec_max_age_sec,
        "display_max_age_sec": display_max_age_sec,
    }

    if out["execution_entry"] is not None and out["execution_entry_status"] != "executable":
        raise EntryContractViolation(
            code="ENTRY_STATE_INVALID_EXECUTION_STATUS",
            message="execution_entry requires execution_entry_status=executable",
            evidence={"symbol": symbol, "expiry": expiry, "strike": strike, "right": right},
        )
    if out["display_entry"] is not None and out["execution_entry"] is None and out["display_entry_status"] == "missing":
        raise EntryContractViolation(
            code="ENTRY_STATE_INVALID_DISPLAY_STATUS",
            message="display_entry requires non-missing display_entry_status",
            evidence={"symbol": symbol, "expiry": expiry, "strike": strike, "right": right},
        )
    if out["entry"] is None and not out["entry_clear_reason"]:
        raise EntryContractViolation(
            code="ENTRY_STATE_MISSING_CLEAR_REASON",
            message="missing display entry requires entry_clear_reason",
            evidence={"symbol": symbol, "expiry": expiry, "strike": strike, "right": right},
        )

    logger.info(
        "entry_state_eval symbol=%s strike=%s expiry=%s right=%s direction=%s bid=%s ask=%s mark=%s mid=%s last=%s quote_age_sec=%s execution_entry=%s execution_entry_source=%s execution_entry_status=%s display_entry=%s display_entry_source=%s display_entry_status=%s entry_reason=%s entry_clear_reason=%s quote_source=%s",
        str(symbol or "").upper(),
        str(strike if strike is not None else ""),
        str(expiry or ""),
        str(right or "").upper(),
        direction_key,
        _valid_positive_quote(bid),
        _valid_positive_quote(ask),
        _valid_positive_quote(mark),
        _valid_positive_quote(mid),
        _valid_positive_quote(last),
        age_val,
        out["execution_entry"],
        out["execution_entry_source"],
        out["execution_entry_status"],
        out["display_entry"],
        out["display_entry_source"],
        out["display_entry_status"],
        out["entry_reason"],
        out["entry_clear_reason"],
        quote_source_key,
    )
    return out


def _derive_expected_from_snapshot(row: Mapping[str, Any]) -> float | None:
    option_quote = _snapshot_option_quote(row)
    if not option_quote:
        return None
    ltp_v = _safe_float(option_quote.get("ltp"))
    if ltp_v is not None:
        return ltp_v
    return _mid_price(option_quote.get("bid"), option_quote.get("ask"))


def _resolve_mode(row: Mapping[str, Any], mode: str | None) -> str:
    if mode:
        return str(mode).strip().upper()
    for key in ("execution_mode", "mode", "runtime_mode"):
        value = str(row.get(key) or "").strip()
        if value:
            return value.upper()
    try:
        config_mode = str(getattr(cfg, "EXECUTION_MODE", "") or "").strip()
    except Exception:
        config_mode = ""
    return config_mode.upper() if config_mode else "PAPER"


def resolve_entry_price(row: Mapping[str, Any], *, mode: str | None = None) -> float | None:
    """
    Contract:
    - PAPER/SIM/OFFHOURS/ADVISORY => expected_entry
    - LIVE/ARMED => fill_entry if available else expected_entry
    """
    expected_entry = _safe_float(row.get("expected_entry"))
    fill_entry = _safe_float(row.get("fill_entry"))
    mode_key = _resolve_mode(row, mode)
    if mode_key in {"LIVE", "ARMED"}:
        return fill_entry if fill_entry is not None else expected_entry
    return expected_entry


def derive_expected_entry(row: Mapping[str, Any]) -> float | None:
    snapshot_price = _derive_expected_from_snapshot(row)
    if snapshot_price is not None:
        return snapshot_price
    for key in _EXPECTED_ENTRY_SOURCES:
        value = _safe_float(row.get(key))
        if value is not None:
            return value
    return None


def derive_fill_entry(row: Mapping[str, Any]) -> float | None:
    for key in _FILL_ENTRY_SOURCES:
        value = _safe_float(row.get(key))
        if value is not None:
            return value
    return None


def _state_value(row: Mapping[str, Any]) -> str:
    for key in ("status", "order_state", "fill_status"):
        value = str(row.get(key) or "").strip().upper()
        if value:
            return value
    return ""


def enforce_entry_contract(row: Mapping[str, Any], *, stage: str, mode: str | None = None) -> dict[str, Any]:
    out = dict(row or {})

    expected_entry = _safe_float(out.get("expected_entry"))
    if expected_entry is None:
        expected_entry = derive_expected_entry(out)
    if expected_entry is not None:
        out["expected_entry"] = expected_entry

    fill_entry = _safe_float(out.get("fill_entry"))
    if fill_entry is None:
        fill_entry = derive_fill_entry(out)
    if fill_entry is not None:
        out["fill_entry"] = fill_entry

    entry_price = resolve_entry_price(out, mode=mode)
    if entry_price is not None:
        out["entry_price"] = entry_price

    state = _state_value(out)
    if state in _REQUIRES_EXPECTED_ENTRY_STATES:
        snapshot_id = str(out.get("snapshot_id") or "").strip()
        if not snapshot_id:
            raise EntryContractViolation(
                code="ENTRY_CONTRACT_MISSING_SNAPSHOT_ID",
                message="snapshot_id is required for APPROVED-or-later trade state.",
                evidence={"stage": stage, "state": state, "trade_id": out.get("trade_id")},
            )
        if _safe_float(out.get("expected_entry")) is None:
            raise EntryContractViolation(
                code="ENTRY_CONTRACT_MISSING_EXPECTED_ENTRY",
                message="expected_entry is required for APPROVED-or-later trade state.",
                evidence={"stage": stage, "state": state, "trade_id": out.get("trade_id")},
            )

    if state in _REQUIRES_FILL_ENTRY_STATES:
        if _safe_float(out.get("fill_entry")) is None:
            raise EntryContractViolation(
                code="ENTRY_CONTRACT_MISSING_FILL_ENTRY",
                message="fill_entry is required for FILLED trade state.",
                evidence={"stage": stage, "state": state, "trade_id": out.get("trade_id")},
            )

    return out
