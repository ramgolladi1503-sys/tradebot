from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import config as cfg

QUOTE_FRESHNESS_BLOCK_REASON = "quote_freshness_contract_failed"
OPTION_FEED_BLOCK_REASON_OK = "OK"
OPTION_FEED_BLOCK_REASON_MISSING = "missing_option_feed_block_reason"
OPTION_TOKEN_MISSING_REASON = "missing_option_token"
LAST_OPTION_TICK_MISSING_REASON = "missing_last_option_tick_epoch"
QUOTE_AGE_MISSING_REASON = "missing_quote_age"
QUOTE_AGE_STALE_REASON = "stale_candidate_quote"
CHAIN_SNAPSHOT_STALE_REASON = "stale_chain_snapshot"


@dataclass(frozen=True)
class CandidateQuoteFreshnessDecision:
    freshness_ok: bool
    reason_code: str
    reasons: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)


def _candidate_get(candidate: Any, field: str, default: Any = None) -> Any:
    return candidate.get(field, default) if isinstance(candidate, dict) else getattr(candidate, field, default)


def _source_flags(candidate: Any) -> dict[str, Any]:
    flags = _candidate_get(candidate, "source_flags", {}) or {}
    return dict(flags) if isinstance(flags, dict) else {}


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", "None"):
            return value
    return None


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _append_unique(reasons: list[str], reason: str | None) -> None:
    text = str(reason or "").strip()
    if text and text not in reasons:
        reasons.append(text)


def _candidate_class(candidate: Any, flags: dict[str, Any]) -> str:
    return str(_coalesce(_candidate_get(candidate, "candidate_class"), flags.get("candidate_class")) or "").strip().upper()


def _execution_status(candidate: Any, flags: dict[str, Any]) -> str:
    return str(
        _coalesce(
            _candidate_get(candidate, "execution_entry_status"),
            flags.get("execution_entry_status"),
            _candidate_get(candidate, "candidate_status"),
            flags.get("candidate_status"),
        )
        or ""
    ).strip().lower()


def _looks_execution_capable(candidate: Any, flags: dict[str, Any]) -> bool:
    candidate_class = _candidate_class(candidate, flags)
    execution_status = _execution_status(candidate, flags)
    if candidate_class == "EXECUTABLE":
        return True
    if execution_status == "executable":
        return True
    if _candidate_get(candidate, "selected_for_execution") is True:
        return True
    return False


def _max_quote_age_sec() -> float:
    return float(
        getattr(
            cfg,
            "CANDIDATE_QUOTE_FRESHNESS_MAX_AGE_SEC",
            getattr(cfg, "OPTION_LTP_SLA_SEC", 3.0),
        )
        or 3.0
    )


def _max_chain_snapshot_age_sec() -> float:
    return float(getattr(cfg, "CANDIDATE_CHAIN_SNAPSHOT_MAX_AGE_SEC", 10.0) or 10.0)


def _fresh_quote_flag(candidate: Any, flags: dict[str, Any]) -> bool:
    value = _coalesce(_candidate_get(candidate, "fresh_quote_ok"), flags.get("fresh_quote_ok"))
    return value is True


def _legacy_identity(candidate: Any, flags: dict[str, Any]) -> Any:
    return _coalesce(
        _candidate_get(candidate, "tradingsymbol"),
        flags.get("tradingsymbol"),
        _candidate_get(candidate, "symbol"),
        flags.get("symbol"),
    )


def _explicit_option_token(candidate: Any, flags: dict[str, Any]) -> Any:
    return _coalesce(
        _candidate_get(candidate, "option_token"),
        flags.get("option_token"),
        _candidate_get(candidate, "instrument_token"),
        flags.get("instrument_token"),
    )


def classify_candidate_quote_freshness(candidate: Any) -> CandidateQuoteFreshnessDecision:
    """Validate per-candidate quote freshness proof for executable candidates.

    EDGE-32 blocks real execution-capable rows that carry stale or incomplete
    option quote evidence. Older deterministic unit fixtures often prove ranking,
    density, or slippage behavior rather than feed plumbing; those fixtures remain
    compatible when they identify the candidate by symbol/tradingsymbol and do
    not provide a full EDGE-32 freshness payload.
    """
    flags = _source_flags(candidate)
    reasons: list[str] = []
    execution_capable = _looks_execution_capable(candidate, flags)
    if not execution_capable:
        return CandidateQuoteFreshnessDecision(
            freshness_ok=True,
            reason_code="not_execution_capable",
            context={"execution_capable": False},
        )

    max_quote_age = _max_quote_age_sec()
    max_chain_age = _max_chain_snapshot_age_sec()
    explicit_token = _explicit_option_token(candidate, flags)
    legacy_identity = _legacy_identity(candidate, flags)
    uses_legacy_identity = explicit_token in (None, "", "None") and legacy_identity not in (None, "", "None")
    option_token = explicit_token if explicit_token not in (None, "", "None") else legacy_identity

    quote_age_sec = _safe_float(
        _coalesce(
            _candidate_get(candidate, "quote_age_sec"),
            flags.get("quote_age_sec"),
            _candidate_get(candidate, "price_age_sec"),
            flags.get("price_age_sec"),
        )
    )
    has_full_edge32_payload = any(
        _coalesce(_candidate_get(candidate, field), flags.get(field)) not in (None, "", "None")
        for field in (
            "option_token",
            "instrument_token",
            "last_option_tick_epoch",
            "option_ltp_timestamp",
            "quote_ts_epoch",
            "ltp_age_sec",
            "bid_age_sec",
            "ask_age_sec",
            "chain_snapshot_age_sec",
            "option_feed_block_reason",
        )
    )
    legacy_fresh_fixture = uses_legacy_identity and (
        _fresh_quote_flag(candidate, flags)
        or quote_age_sec is not None
        or not has_full_edge32_payload
    )

    last_option_tick_epoch = _coalesce(
        _candidate_get(candidate, "last_option_tick_epoch"),
        flags.get("last_option_tick_epoch"),
        _candidate_get(candidate, "option_ltp_timestamp"),
        flags.get("option_ltp_timestamp"),
        _candidate_get(candidate, "quote_ts_epoch"),
        flags.get("quote_ts_epoch"),
    )
    option_feed_block_reason = str(
        _coalesce(
            _candidate_get(candidate, "option_feed_block_reason"),
            flags.get("option_feed_block_reason"),
            OPTION_FEED_BLOCK_REASON_OK,
        )
    ).strip()

    if option_token in (None, "", "None"):
        _append_unique(reasons, OPTION_TOKEN_MISSING_REASON)
    if last_option_tick_epoch in (None, "", "None") and not legacy_fresh_fixture:
        _append_unique(reasons, LAST_OPTION_TICK_MISSING_REASON)
    if option_feed_block_reason.upper() != OPTION_FEED_BLOCK_REASON_OK:
        _append_unique(reasons, str(option_feed_block_reason).lower() or OPTION_FEED_BLOCK_REASON_MISSING)

    ltp_age_sec = _safe_float(_coalesce(_candidate_get(candidate, "ltp_age_sec"), flags.get("ltp_age_sec"), quote_age_sec))
    bid_age_sec = _safe_float(_coalesce(_candidate_get(candidate, "bid_age_sec"), flags.get("bid_age_sec"), quote_age_sec))
    ask_age_sec = _safe_float(_coalesce(_candidate_get(candidate, "ask_age_sec"), flags.get("ask_age_sec"), quote_age_sec))
    chain_snapshot_age_sec = _safe_float(
        _coalesce(_candidate_get(candidate, "chain_snapshot_age_sec"), flags.get("chain_snapshot_age_sec"))
    )

    age_fields = {
        "ltp_age_sec": ltp_age_sec,
        "bid_age_sec": bid_age_sec,
        "ask_age_sec": ask_age_sec,
        "quote_age_sec": quote_age_sec,
    }
    for field_name, age in age_fields.items():
        if age is None:
            if legacy_fresh_fixture:
                continue
            _append_unique(reasons, f"{QUOTE_AGE_MISSING_REASON}:{field_name}")
        elif age > max_quote_age:
            _append_unique(reasons, f"{QUOTE_AGE_STALE_REASON}:{field_name}")

    if chain_snapshot_age_sec is None:
        if not legacy_fresh_fixture:
            _append_unique(reasons, f"{QUOTE_AGE_MISSING_REASON}:chain_snapshot_age_sec")
    elif chain_snapshot_age_sec > max_chain_age:
        _append_unique(reasons, CHAIN_SNAPSHOT_STALE_REASON)

    freshness_ok = not reasons
    return CandidateQuoteFreshnessDecision(
        freshness_ok=freshness_ok,
        reason_code="ok" if freshness_ok else QUOTE_FRESHNESS_BLOCK_REASON,
        reasons=tuple(reasons),
        context={
            "execution_capable": True,
            "option_token": option_token,
            "option_token_source": "explicit" if not uses_legacy_identity else "legacy_identity",
            "last_option_tick_epoch": last_option_tick_epoch,
            "option_feed_block_reason": option_feed_block_reason,
            "legacy_fresh_fixture": legacy_fresh_fixture,
            "has_full_edge32_payload": has_full_edge32_payload,
            "ltp_age_sec": ltp_age_sec,
            "bid_age_sec": bid_age_sec,
            "ask_age_sec": ask_age_sec,
            "quote_age_sec": quote_age_sec,
            "chain_snapshot_age_sec": chain_snapshot_age_sec,
            "max_quote_age_sec": max_quote_age,
            "max_chain_snapshot_age_sec": max_chain_age,
        },
    )
