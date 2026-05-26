"""Pure option-chain confirmation layer for EDGE-76."""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.candidate_intent import CandidateIntent
from core.candidate_intent_pool import CandidateIntentPoolReport, build_candidate_intent_pool

OPTION_CHAIN_CONFIRMATION_SCHEMA_VERSION = 1
OPTION_CHAIN_CONFIRMATION_SOURCE = "option_chain_confirmation_layer_v1"
OPTION_CHAIN_CONFIRMATION_STATUS_CONFIRMED = "OPTION_CHAIN_CONFIRMED"
OPTION_CHAIN_CONFIRMATION_STATUS_BLOCKED = "OPTION_CHAIN_BLOCKED"

OPTION_CHAIN_EMPTY_CANDIDATES = "option_chain_empty_candidates"
OPTION_CHAIN_EMPTY_SNAPSHOT = "option_chain_empty_snapshot"
OPTION_CHAIN_CANDIDATE_NOT_POOL_ELIGIBLE = "option_chain_candidate_not_pool_eligible"
OPTION_CHAIN_DIRECTION_NOT_OPTION_SPECIFIC = "option_chain_direction_not_option_specific"
OPTION_CHAIN_CONTRACT_NOT_FOUND = "option_chain_contract_not_found"
OPTION_CHAIN_OPTION_TYPE_MISMATCH = "option_chain_option_type_mismatch"
OPTION_CHAIN_MISSING_LTP = "option_chain_missing_ltp"
OPTION_CHAIN_MISSING_BID_ASK = "option_chain_missing_bid_ask"
OPTION_CHAIN_CROSSED_BID_ASK = "option_chain_crossed_bid_ask"
OPTION_CHAIN_WIDE_SPREAD = "option_chain_wide_spread"
OPTION_CHAIN_LOW_VOLUME = "option_chain_low_volume"
OPTION_CHAIN_LOW_OPEN_INTEREST = "option_chain_low_open_interest"
OPTION_CHAIN_STALE_SNAPSHOT = "option_chain_stale_snapshot"
OPTION_CHAIN_FALLBACK_OR_PATCHED_DATA = "option_chain_fallback_or_patched_data"
OPTION_CHAIN_INVALID_NUMERIC_INPUT = "option_chain_invalid_numeric_input"

_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"
_INVALID = object()

_ROW_KEYS = ("contracts", "rows", "option_chain", "data", "records", "items")
_SYMBOL_KEYS = ("tradingsymbol", "symbol", "instrument", "contract", "option_symbol")
_UNDERLYING_KEYS = ("underlying", "underlying_symbol", "index", "root_symbol", "name")
_TYPE_KEYS = ("option_type", "instrument_type", "right", "type")
_STRIKE_KEYS = ("strike", "strike_price")
_EXPIRY_KEYS = ("expiry", "expiry_date")
_LTP_KEYS = ("ltp", "last_price", "last_traded_price", "last", "option_ltp")
_BID_KEYS = ("bid", "best_bid", "bid_price", "buy_price")
_ASK_KEYS = ("ask", "best_ask", "ask_price", "offer", "sell_price")
_VOLUME_KEYS = ("volume", "vol", "traded_volume")
_OI_KEYS = ("oi", "open_interest")
_TS_KEYS = ("as_of_epoch", "timestamp_epoch", "generated_epoch", "updated_epoch", "last_update_epoch", "exchange_timestamp_epoch")
_QUALITY_KEYS = ("data_quality", "quote_quality", "source", "status", "flags", "warnings", "blockers", "feed_status", "quote_status", "ltp_source")
_TARGET_SYMBOL_KEYS = ("option_symbol", "tradingsymbol", "contract_symbol", "selected_contract")
_PATCHED_MARKERS = ("fallback", "recovered_fallback", "rest_fallback", "estimated", "stale", "price_mismatch", "missing_quote", "subscription_failed")


@dataclass(frozen=True)
class OptionChainConfirmation:
    confirmation_id: str
    candidate_intent_id: str
    instrument: str
    direction: str
    expected_option_type: str | None
    status: str
    selected_contract: dict[str, Any] | None = None
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True
    append: bool = False
    source: str = OPTION_CHAIN_CONFIRMATION_SOURCE

    @property
    def confirmed(self) -> bool:
        return self.status == OPTION_CHAIN_CONFIRMATION_STATUS_CONFIRMED and not self.blockers

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "confirmation_id": self.confirmation_id,
            "candidate_intent_id": self.candidate_intent_id,
            "instrument": self.instrument,
            "direction": self.direction,
            "expected_option_type": self.expected_option_type,
            "status": self.status,
            "confirmed": self.confirmed,
            "selected_contract": dict(self.selected_contract or {}),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class OptionChainConfirmationReport:
    schema_version: int
    read_only: bool
    append: bool
    source: str
    confirmations: tuple[OptionChainConfirmation, ...]
    pool_report: CandidateIntentPoolReport
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def valid(self) -> bool:
        return not self.blockers and self.pool_report.valid

    @property
    def confirmed_confirmations(self) -> tuple[OptionChainConfirmation, ...]:
        return tuple(item for item in self.confirmations if item.confirmed)

    @property
    def blocked_confirmations(self) -> tuple[OptionChainConfirmation, ...]:
        return tuple(item for item in self.confirmations if not item.confirmed)

    @property
    def confirmation_ready(self) -> bool:
        return self.valid and bool(self.confirmed_confirmations)

    @property
    def confirmed_candidate_intent_ids(self) -> tuple[str, ...]:
        return tuple(item.candidate_intent_id for item in self.confirmed_confirmations)

    @property
    def blocked_candidate_intent_ids(self) -> tuple[str, ...]:
        return tuple(item.candidate_intent_id for item in self.blocked_confirmations)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "source": self.source,
            "valid": self.valid,
            "confirmation_ready": self.confirmation_ready,
            "confirmation_count": len(self.confirmations),
            "confirmed_count": len(self.confirmed_confirmations),
            "blocked_count": len(self.blocked_confirmations),
            "confirmed_candidate_intent_ids": list(self.confirmed_candidate_intent_ids),
            "blocked_candidate_intent_ids": list(self.blocked_candidate_intent_ids),
            "confirmations": [item.to_payload() for item in self.confirmations],
            "pool_report": self.pool_report.to_payload(),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        _mark_non_action(payload)
        return payload


def confirm_option_chain_for_candidates(
    candidates: Iterable[CandidateIntent | Mapping[str, Any]],
    option_chain: Iterable[Mapping[str, Any]] | Mapping[str, Any] | None,
    *,
    current_epoch: float | None = None,
    max_snapshot_age_seconds: float = 60.0,
    max_spread_pct: float = 0.12,
    max_spread_abs: float | None = None,
    min_volume: float = 1.0,
    min_open_interest: float = 1.0,
    source: str = OPTION_CHAIN_CONFIRMATION_SOURCE,
) -> OptionChainConfirmationReport:
    pool_report = build_candidate_intent_pool(tuple(candidates or ()))
    return confirm_option_chain_for_candidate_pool(
        pool_report,
        option_chain,
        current_epoch=current_epoch,
        max_snapshot_age_seconds=max_snapshot_age_seconds,
        max_spread_pct=max_spread_pct,
        max_spread_abs=max_spread_abs,
        min_volume=min_volume,
        min_open_interest=min_open_interest,
        source=source,
    )


def confirm_option_chain_for_candidate_pool(
    pool_report: CandidateIntentPoolReport,
    option_chain: Iterable[Mapping[str, Any]] | Mapping[str, Any] | None,
    *,
    current_epoch: float | None = None,
    max_snapshot_age_seconds: float = 60.0,
    max_spread_pct: float = 0.12,
    max_spread_abs: float | None = None,
    min_volume: float = 1.0,
    min_open_interest: float = 1.0,
    source: str = OPTION_CHAIN_CONFIRMATION_SOURCE,
) -> OptionChainConfirmationReport:
    rows, chain_ts = _extract_rows(option_chain)
    chain_blockers = (OPTION_CHAIN_EMPTY_SNAPSHOT,) if not rows else ()
    if rows and _stale(chain_ts, current_epoch, max_snapshot_age_seconds):
        chain_blockers = (OPTION_CHAIN_STALE_SNAPSHOT,)

    confirmations = [
        _confirm_one(
            entry.intent,
            rows,
            chain_ts,
            chain_blockers,
            current_epoch,
            max_snapshot_age_seconds,
            max_spread_pct,
            max_spread_abs,
            min_volume,
            min_open_interest,
            source,
        )
        for entry in pool_report.eligible_intents
    ]
    confirmations.extend(
        _blocked(
            entry.intent,
            blockers=_dedupe((OPTION_CHAIN_CANDIDATE_NOT_POOL_ELIGIBLE, *entry.blockers)),
            warnings=entry.warnings,
            metadata={"pool_status": entry.pool_status},
            source=source,
        )
        for entry in pool_report.blocked_intents
    )
    return OptionChainConfirmationReport(
        schema_version=OPTION_CHAIN_CONFIRMATION_SCHEMA_VERSION,
        read_only=True,
        append=False,
        source=source,
        confirmations=tuple(sorted(confirmations, key=lambda item: item.confirmation_id)),
        pool_report=pool_report,
        blockers=() if confirmations else (OPTION_CHAIN_EMPTY_CANDIDATES,),
        warnings=_dedupe((*chain_blockers, *pool_report.warnings)),
        metadata={
            "model": OPTION_CHAIN_CONFIRMATION_SOURCE,
            "scope": "pure_option_chain_confirmation_no_runtime_wiring_no_ranking",
            "row_count": len(rows),
            "chain_timestamp_epoch": chain_ts,
            "max_snapshot_age_seconds": float(max_snapshot_age_seconds),
            "max_spread_pct": float(max_spread_pct),
            "max_spread_abs": None if max_spread_abs is None else float(max_spread_abs),
            "min_volume": float(min_volume),
            "min_open_interest": float(min_open_interest),
            "does_not_import_strategy_modules": True,
            "does_not_execute_strategy_callables": True,
            "does_not_rank_candidates": True,
            "does_not_score_edge": True,
            "does_not_touch_runtime": True,
        },
    )


def _confirm_one(intent: CandidateIntent, rows, chain_ts, chain_blockers, current_epoch, max_age, max_spread_pct, max_spread_abs, min_volume, min_oi, source):
    expected_type = _expected_type(intent)
    if expected_type is None:
        return _blocked(intent, blockers=(OPTION_CHAIN_DIRECTION_NOT_OPTION_SPECIFIC,), metadata={"reason": "candidate_direction_does_not_identify_call_or_put"}, source=source)

    blockers = list(chain_blockers)
    matches = _matching_rows(intent, rows, expected_type)
    selected = _select_best(matches)
    if selected is None:
        blockers.append(OPTION_CHAIN_CONTRACT_NOT_FOUND)
        return _blocked(
            intent,
            expected_option_type=expected_type,
            blockers=_dedupe(blockers),
            metadata={"candidate_direction": intent.direction, "expected_option_type": expected_type, "evaluated_contract_count": 0, "chain_timestamp_epoch": chain_ts},
            source=source,
        )

    row_type = _norm_type(_text(selected, _TYPE_KEYS))
    row_ts = _num(selected, _TS_KEYS, default=chain_ts)
    ltp, bid, ask = _num(selected, _LTP_KEYS), _num(selected, _BID_KEYS), _num(selected, _ASK_KEYS)
    volume, oi = _num(selected, _VOLUME_KEYS, default=0.0), _num(selected, _OI_KEYS, default=0.0)
    values = (row_ts, ltp, bid, ask, volume, oi)

    if row_type != expected_type:
        blockers.append(OPTION_CHAIN_OPTION_TYPE_MISMATCH)
    if any(value is _INVALID for value in values):
        blockers.append(OPTION_CHAIN_INVALID_NUMERIC_INPUT)
    if row_ts is not _INVALID and _stale(row_ts, current_epoch, max_age):
        blockers.append(OPTION_CHAIN_STALE_SNAPSHOT)
    if _patched(selected):
        blockers.append(OPTION_CHAIN_FALLBACK_OR_PATCHED_DATA)
    if ltp in (None, _INVALID) or float(ltp) <= 0:
        blockers.append(OPTION_CHAIN_MISSING_LTP)
    if bid in (None, _INVALID) or ask in (None, _INVALID) or float(bid or 0) <= 0 or float(ask or 0) <= 0:
        blockers.append(OPTION_CHAIN_MISSING_BID_ASK)
    elif float(ask) < float(bid):
        blockers.append(OPTION_CHAIN_CROSSED_BID_ASK)

    spread_abs = spread_pct = None
    if not any(item in blockers for item in (OPTION_CHAIN_INVALID_NUMERIC_INPUT, OPTION_CHAIN_MISSING_LTP, OPTION_CHAIN_MISSING_BID_ASK, OPTION_CHAIN_CROSSED_BID_ASK)):
        spread_abs = float(ask) - float(bid)
        spread_pct = spread_abs / max(float(ltp), 0.01)
        if spread_pct > float(max_spread_pct) or (max_spread_abs is not None and spread_abs > float(max_spread_abs)):
            blockers.append(OPTION_CHAIN_WIDE_SPREAD)
    if volume in (None, _INVALID) or float(volume) < float(min_volume):
        blockers.append(OPTION_CHAIN_LOW_VOLUME)
    if oi in (None, _INVALID) or float(oi) < float(min_oi):
        blockers.append(OPTION_CHAIN_LOW_OPEN_INTEREST)

    contract = _contract(selected, expected_type, ltp, bid, ask, volume, oi, spread_abs, spread_pct)
    blockers_tuple = _dedupe(blockers)
    return OptionChainConfirmation(
        confirmation_id=_candidate_key(f"{intent.candidate_intent_id}:{contract.get('symbol') or 'contract'}"),
        candidate_intent_id=intent.candidate_intent_id,
        instrument=intent.instrument,
        direction=intent.direction,
        expected_option_type=expected_type,
        status=OPTION_CHAIN_CONFIRMATION_STATUS_BLOCKED if blockers_tuple else OPTION_CHAIN_CONFIRMATION_STATUS_CONFIRMED,
        selected_contract=contract,
        blockers=blockers_tuple,
        metadata={
            "candidate_direction": intent.direction,
            "expected_option_type": expected_type,
            "evaluated_contract_count": len(matches),
            "chain_timestamp_epoch": chain_ts,
            "row_timestamp_epoch": None if row_ts is _INVALID else row_ts,
            "max_snapshot_age_seconds": float(max_age),
            "max_spread_pct": float(max_spread_pct),
            "max_spread_abs": None if max_spread_abs is None else float(max_spread_abs),
            "min_volume": float(min_volume),
            "min_open_interest": float(min_oi),
            "does_not_rank_candidates": True,
            "does_not_score_edge": True,
            "does_not_touch_runtime": True,
        },
        source=source,
    )


def _blocked(intent: CandidateIntent, *, blockers, source, expected_option_type=None, warnings=(), metadata=None):
    return OptionChainConfirmation(
        confirmation_id=_candidate_key(f"{intent.candidate_intent_id}:blocked"),
        candidate_intent_id=intent.candidate_intent_id,
        instrument=intent.instrument,
        direction=intent.direction,
        expected_option_type=expected_option_type,
        status=OPTION_CHAIN_CONFIRMATION_STATUS_BLOCKED,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        metadata=dict(metadata or {}),
        source=source,
    )


def _extract_rows(option_chain):
    if option_chain is None:
        return (), None
    if isinstance(option_chain, Mapping):
        ts = _num(option_chain, _TS_KEYS, default=None)
        ts = None if ts is _INVALID else ts
        for key in _ROW_KEYS:
            if key in option_chain:
                return _rows(option_chain.get(key)), ts
        if any(key in option_chain for key in (*_SYMBOL_KEYS, *_UNDERLYING_KEYS, *_TYPE_KEYS)):
            return (option_chain,), ts
        return (), ts
    return _rows(option_chain), None


def _rows(raw):
    if isinstance(raw, Mapping):
        return tuple(row for row in raw.values() if isinstance(row, Mapping))
    try:
        return tuple(row for row in raw if isinstance(row, Mapping))
    except TypeError:
        return ()


def _expected_type(intent: CandidateIntent):
    metadata_type = _norm_type(_text(intent.metadata, _TYPE_KEYS))
    if metadata_type:
        return metadata_type
    direction = str(intent.direction or "").upper()
    if "CALL" in direction or direction.endswith("_CE") or direction == "CE":
        return "CE"
    if "PUT" in direction or direction.endswith("_PE") or direction == "PE":
        return "PE"
    return None


def _matching_rows(intent, rows, expected_type):
    matches, instrument = [], _key(intent.instrument)
    target_symbol = _text(intent.metadata, _TARGET_SYMBOL_KEYS)
    target_strike = _num(intent.metadata, _STRIKE_KEYS, default=None)
    target_expiry = _text(intent.metadata, _EXPIRY_KEYS)
    has_target = bool(target_symbol or target_expiry or target_strike not in (None, _INVALID))
    for row in rows:
        row_type = _norm_type(_text(row, _TYPE_KEYS))
        if row_type and row_type != expected_type:
            continue
        row_symbol, row_underlying = _key(_text(row, _SYMBOL_KEYS)), _key(_text(row, _UNDERLYING_KEYS))
        if target_symbol and row_symbol != _key(target_symbol):
            continue
        if target_expiry and _key(_text(row, _EXPIRY_KEYS)) != _key(target_expiry):
            continue
        if target_strike not in (None, _INVALID):
            row_strike = _num(row, _STRIKE_KEYS, default=None)
            if row_strike in (None, _INVALID) or float(row_strike) != float(target_strike):
                continue
        if has_target or (instrument and (instrument == row_underlying or instrument == row_symbol or row_symbol.startswith(instrument))):
            matches.append(row)
    return tuple(matches)


def _select_best(rows):
    if not rows:
        return None
    def score(row):
        ltp, bid, ask = _num(row, _LTP_KEYS, default=0), _num(row, _BID_KEYS, default=0), _num(row, _ASK_KEYS, default=0)
        volume, oi = _num(row, _VOLUME_KEYS, default=0), _num(row, _OI_KEYS, default=0)
        if any(item is _INVALID for item in (ltp, bid, ask, volume, oi)):
            return (999999.0, 0.0, 0.0)
        spread = 999999.0
        if float(ltp or 0) > 0 and float(ask or 0) >= float(bid or 0) > 0:
            spread = (float(ask) - float(bid)) / max(float(ltp), 0.01)
        return (spread, -float(volume or 0), -float(oi or 0))
    return sorted(rows, key=score)[0]


def _contract(row, expected_type, ltp, bid, ask, volume, oi, spread_abs, spread_pct):
    return {
        "symbol": _text(row, _SYMBOL_KEYS),
        "underlying": _text(row, _UNDERLYING_KEYS),
        "option_type": _norm_type(_text(row, _TYPE_KEYS)) or expected_type,
        "strike": _safe(_num(row, _STRIKE_KEYS, default=None)),
        "expiry": _text(row, _EXPIRY_KEYS),
        "ltp": _safe(ltp),
        "bid": _safe(bid),
        "ask": _safe(ask),
        "spread_abs": spread_abs,
        "spread_pct": spread_pct,
        "volume": _safe(volume),
        "open_interest": _safe(oi),
    }


def _patched(row):
    text = " ".join(str(row.get(key, "")) for key in _QUALITY_KEYS).lower()
    return any(marker in text for marker in _PATCHED_MARKERS)


def _stale(ts, current_epoch, max_age):
    if current_epoch is None or ts in (None, _INVALID):
        return False
    try:
        return float(current_epoch) - float(ts) > float(max_age)
    except (TypeError, ValueError):
        return True


def _text(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _num(payload: Mapping[str, Any], keys: tuple[str, ...], default: float | None = None):
    for key in keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None or str(value).strip() == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return _INVALID
    return default


def _norm_type(value):
    value = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    if value in {"CE", "CALL", "C", "CALL_OPTION"}:
        return "CE"
    if value in {"PE", "PUT", "P", "PUT_OPTION"}:
        return "PE"
    return None


def _safe(value):
    return None if value in (None, _INVALID) else float(value)


def _key(value):
    return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")


def _candidate_key(value):
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if str(value)}))


def _mark_non_action(payload):
    payload[_ORDER_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "OPTION_CHAIN_CANDIDATE_NOT_POOL_ELIGIBLE",
    "OPTION_CHAIN_CONFIRMATION_SCHEMA_VERSION",
    "OPTION_CHAIN_CONFIRMATION_SOURCE",
    "OPTION_CHAIN_CONFIRMATION_STATUS_BLOCKED",
    "OPTION_CHAIN_CONFIRMATION_STATUS_CONFIRMED",
    "OPTION_CHAIN_CONTRACT_NOT_FOUND",
    "OPTION_CHAIN_CROSSED_BID_ASK",
    "OPTION_CHAIN_DIRECTION_NOT_OPTION_SPECIFIC",
    "OPTION_CHAIN_EMPTY_CANDIDATES",
    "OPTION_CHAIN_EMPTY_SNAPSHOT",
    "OPTION_CHAIN_FALLBACK_OR_PATCHED_DATA",
    "OPTION_CHAIN_INVALID_NUMERIC_INPUT",
    "OPTION_CHAIN_LOW_OPEN_INTEREST",
    "OPTION_CHAIN_LOW_VOLUME",
    "OPTION_CHAIN_MISSING_BID_ASK",
    "OPTION_CHAIN_MISSING_LTP",
    "OPTION_CHAIN_OPTION_TYPE_MISMATCH",
    "OPTION_CHAIN_STALE_SNAPSHOT",
    "OPTION_CHAIN_WIDE_SPREAD",
    "OptionChainConfirmation",
    "OptionChainConfirmationReport",
    "confirm_option_chain_for_candidate_pool",
    "confirm_option_chain_for_candidates",
]
