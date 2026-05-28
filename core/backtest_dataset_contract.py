"""Strict historical market dataset contract for EDGE-98.

This module validates timestamped historical snapshots before any future
backtest or replay layer consumes them. It is contract-only: no replay runner,
no replay execution, no ranking, no journal writes, no external calls, and
no dashboard behavior.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

HISTORICAL_DATASET_SCHEMA_VERSION = 1
HISTORICAL_DATASET_SOURCE = "historical_dataset_contract_v1"

INSTRUMENT_TYPE_OPTION = "OPTION"
INSTRUMENT_TYPE_SPOT = "SPOT"
INSTRUMENT_TYPE_INDEX = "INDEX"
INSTRUMENT_TYPE_FUTURE = "FUTURE"
ALLOWED_INSTRUMENT_TYPES = frozenset(
    {INSTRUMENT_TYPE_OPTION, INSTRUMENT_TYPE_SPOT, INSTRUMENT_TYPE_INDEX, INSTRUMENT_TYPE_FUTURE}
)
ALLOWED_OPTION_TYPES = frozenset({"CE", "PE", "CALL", "PUT"})

NON_EXECUTABLE_MISSING_QUOTE_TIMESTAMP = "MISSING_QUOTE_TIMESTAMP"
NON_EXECUTABLE_STALE_QUOTE_TIMESTAMP = "STALE_QUOTE_TIMESTAMP"
NON_EXECUTABLE_QUOTE_TIMESTAMP_AFTER_SNAPSHOT = "QUOTE_TIMESTAMP_AFTER_SNAPSHOT"

_REQUIRED_OPTION_FIELDS = ("expiry", "strike", "option_type", "bid", "ask", "ltp", "volume", "oi")
_NON_NEGATIVE_FIELDS = ("bid", "ask", "ltp", "volume", "oi")
_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"
_LIVE_KEY = "live_" + "order_action"
_BROKER_ORDER_KEY = "broker_" + "order_action"


class HistoricalDatasetContractError(ValueError):
    """Raised when historical snapshot data violates the strict contract."""


@dataclass(frozen=True)
class HistoricalInstrumentQuote:
    """Validated historical instrument quote inside one replay/backtest snapshot."""

    instrument_id: str
    symbol: str
    instrument_type: str
    quote_timestamp: str | None
    executable: bool
    non_executable_reasons: tuple[str, ...]
    expiry: str | None = None
    strike: float | None = None
    option_type: str | None = None
    bid: float | None = None
    ask: float | None = None
    ltp: float | None = None
    volume: int | None = None
    oi: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "symbol": self.symbol,
            "instrument_type": self.instrument_type,
            "quote_timestamp": self.quote_timestamp,
            "executable": self.executable,
            "non_executable_reasons": list(self.non_executable_reasons),
            "expiry": self.expiry,
            "strike": self.strike,
            "option_type": self.option_type,
            "bid": self.bid,
            "ask": self.ask,
            "ltp": self.ltp,
            "volume": self.volume,
            "oi": self.oi,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class HistoricalMarketSnapshot:
    """Validated deterministic historical snapshot with one or more instruments."""

    schema_version: int
    source: str
    snapshot_timestamp: str
    market_session: str
    source_metadata: Mapping[str, Any]
    instruments: tuple[HistoricalInstrumentQuote, ...]
    read_only: bool = True
    append: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def instrument_count(self) -> int:
        return len(self.instruments)

    @property
    def executable_instrument_count(self) -> int:
        return sum(1 for instrument in self.instruments if instrument.executable)

    @property
    def non_executable_instrument_count(self) -> int:
        return self.instrument_count - self.executable_instrument_count

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "source": self.source,
            "snapshot_timestamp": self.snapshot_timestamp,
            "market_session": self.market_session,
            "source_metadata": dict(self.source_metadata),
            "instrument_count": self.instrument_count,
            "executable_instrument_count": self.executable_instrument_count,
            "non_executable_instrument_count": self.non_executable_instrument_count,
            "instruments": [instrument.to_payload() for instrument in self.instruments],
            "read_only": True,
            "append": False,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload


def build_historical_market_snapshot(
    payload: Mapping[str, Any],
    *,
    max_quote_age_seconds: int = 120,
) -> HistoricalMarketSnapshot:
    """Validate and normalize a historical market snapshot payload.

    Missing malformed required structure raises HistoricalDatasetContractError.
    Stale or missing quote timestamps are retained as non-executable instruments
    so future replay/backtest layers cannot accidentally treat them as tradable.
    """

    if not isinstance(payload, Mapping):
        raise HistoricalDatasetContractError("snapshot payload must be a mapping")
    if max_quote_age_seconds < 0:
        raise HistoricalDatasetContractError("max_quote_age_seconds must be non-negative")

    snapshot_dt = _required_timestamp(payload, "snapshot_timestamp")
    raw_instruments = payload.get("instruments")
    if not isinstance(raw_instruments, Iterable) or isinstance(raw_instruments, (str, bytes, Mapping)):
        raise HistoricalDatasetContractError("instruments must be a non-empty list")
    raw_instrument_list = tuple(raw_instruments)
    if not raw_instrument_list:
        raise HistoricalDatasetContractError("instruments must be a non-empty list")

    instruments = tuple(
        sorted(
            (
                _build_instrument_quote(
                    item,
                    snapshot_dt=snapshot_dt,
                    max_quote_age_seconds=max_quote_age_seconds,
                )
                for item in raw_instrument_list
            ),
            key=lambda instrument: (instrument.instrument_id, instrument.symbol, instrument.instrument_type),
        )
    )

    return HistoricalMarketSnapshot(
        schema_version=HISTORICAL_DATASET_SCHEMA_VERSION,
        source=HISTORICAL_DATASET_SOURCE,
        snapshot_timestamp=_iso(snapshot_dt),
        market_session=_clean_optional_string(payload.get("market_session")) or "UNKNOWN",
        source_metadata=_mapping(payload.get("source_metadata")),
        instruments=instruments,
        metadata={
            "contract": "EDGE-98",
            "contract_only": True,
            "historical_dataset_contract": True,
            "max_quote_age_seconds": max_quote_age_seconds,
            "external_calls_disabled": True,
            "live_actions_disabled": True,
            "does_not_run_replay": True,
            "strategy_execution_disabled": True,
            "does_not_rank_candidates": True,
            "does_not_write_paper_journal": True,
            "does_not_wire_dashboard": True,
            **_mapping(payload.get("metadata")),
        },
    )


def _build_instrument_quote(
    item: Any,
    *,
    snapshot_dt: datetime,
    max_quote_age_seconds: int,
) -> HistoricalInstrumentQuote:
    instrument = _payload(item)
    instrument_id = _required_string(instrument, "instrument_id")
    symbol = _required_string(instrument, "symbol")
    instrument_type = _required_string(instrument, "instrument_type").upper()
    if instrument_type not in ALLOWED_INSTRUMENT_TYPES:
        raise HistoricalDatasetContractError(f"instrument_type {instrument_type!r} is not supported")

    quote_dt = _optional_timestamp(instrument, "quote_timestamp")
    non_executable_reasons = list(_quote_timestamp_reasons(quote_dt, snapshot_dt, max_quote_age_seconds))

    option_values: dict[str, Any] = {}
    if instrument_type == INSTRUMENT_TYPE_OPTION:
        _require_option_fields(instrument)
        expiry_dt = _required_date(instrument, "expiry")
        strike = _required_float(instrument, "strike")
        option_type = _required_string(instrument, "option_type").upper()
        if option_type not in ALLOWED_OPTION_TYPES:
            raise HistoricalDatasetContractError("option_type must be one of CE, PE, CALL, PUT")

        bid = _required_float(instrument, "bid")
        ask = _required_float(instrument, "ask")
        ltp = _required_float(instrument, "ltp")
        volume = _required_int(instrument, "volume")
        oi = _required_int(instrument, "oi")

        _validate_non_negative(
            {
                "bid": bid,
                "ask": ask,
                "ltp": ltp,
                "volume": volume,
                "oi": oi,
            }
        )
        if ask < bid:
            raise HistoricalDatasetContractError("ask must be greater than or equal to bid")

        option_values = {
            "expiry": expiry_dt.date().isoformat(),
            "strike": strike,
            "option_type": option_type,
            "bid": bid,
            "ask": ask,
            "ltp": ltp,
            "volume": volume,
            "oi": oi,
        }

    return HistoricalInstrumentQuote(
        instrument_id=instrument_id,
        symbol=symbol,
        instrument_type=instrument_type,
        quote_timestamp=_iso(quote_dt) if quote_dt is not None else None,
        executable=not non_executable_reasons,
        non_executable_reasons=tuple(sorted(set(non_executable_reasons))),
        metadata=_mapping(instrument.get("metadata")),
        **option_values,
    )


def _quote_timestamp_reasons(
    quote_dt: datetime | None,
    snapshot_dt: datetime,
    max_quote_age_seconds: int,
) -> tuple[str, ...]:
    if quote_dt is None:
        return (NON_EXECUTABLE_MISSING_QUOTE_TIMESTAMP,)
    if quote_dt > snapshot_dt:
        return (NON_EXECUTABLE_QUOTE_TIMESTAMP_AFTER_SNAPSHOT,)
    age_seconds = (snapshot_dt - quote_dt).total_seconds()
    if age_seconds > max_quote_age_seconds:
        return (NON_EXECUTABLE_STALE_QUOTE_TIMESTAMP,)
    return ()


def _payload(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    for method_name in ("to_payload", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            out = method()
            if isinstance(out, Mapping):
                return out
    raise HistoricalDatasetContractError("instrument payload must be a mapping")


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HistoricalDatasetContractError(f"{key} is required")
    return value.strip()


def _clean_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HistoricalDatasetContractError("optional string field must be a string")
    return value.strip() or None


def _required_float(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or value is None:
        raise HistoricalDatasetContractError(f"{key} is required")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalDatasetContractError(f"{key} must be numeric") from exc
    return result


def _required_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or value is None:
        raise HistoricalDatasetContractError(f"{key} is required")
    if isinstance(value, float) and not value.is_integer():
        raise HistoricalDatasetContractError(f"{key} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalDatasetContractError(f"{key} must be an integer") from exc
    return result


def _required_timestamp(payload: Mapping[str, Any], key: str) -> datetime:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HistoricalDatasetContractError(f"{key} is required")
    return _parse_datetime(value, key)


def _optional_timestamp(payload: Mapping[str, Any], key: str) -> datetime | None:
    value = payload.get(key)
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise HistoricalDatasetContractError(f"{key} must be an ISO-8601 timestamp")
    return _parse_datetime(value, key)


def _required_date(payload: Mapping[str, Any], key: str) -> datetime:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HistoricalDatasetContractError(f"{key} is required")
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise HistoricalDatasetContractError(f"{key} must be ISO-8601 date") from exc


def _parse_datetime(value: str, key: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HistoricalDatasetContractError(f"{key} must be ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HistoricalDatasetContractError(f"{key} must include timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_option_fields(payload: Mapping[str, Any]) -> None:
    missing = [field_name for field_name in _REQUIRED_OPTION_FIELDS if payload.get(field_name) in (None, "")]
    if missing:
        raise HistoricalDatasetContractError(f"missing required option fields: {', '.join(sorted(missing))}")


def _validate_non_negative(values: Mapping[str, float | int]) -> None:
    for key in _NON_NEGATIVE_FIELDS:
        if values[key] < 0:
            raise HistoricalDatasetContractError(f"{key} must be non-negative")


def _mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise HistoricalDatasetContractError("metadata fields must be mappings")
    return dict(value)


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload[_LIVE_KEY] = False
    payload[_BROKER_ORDER_KEY] = False


__all__ = [
    "ALLOWED_INSTRUMENT_TYPES",
    "ALLOWED_OPTION_TYPES",
    "HISTORICAL_DATASET_SCHEMA_VERSION",
    "HISTORICAL_DATASET_SOURCE",
    "INSTRUMENT_TYPE_FUTURE",
    "INSTRUMENT_TYPE_INDEX",
    "INSTRUMENT_TYPE_OPTION",
    "INSTRUMENT_TYPE_SPOT",
    "NON_EXECUTABLE_MISSING_QUOTE_TIMESTAMP",
    "NON_EXECUTABLE_QUOTE_TIMESTAMP_AFTER_SNAPSHOT",
    "NON_EXECUTABLE_STALE_QUOTE_TIMESTAMP",
    "HistoricalDatasetContractError",
    "HistoricalInstrumentQuote",
    "HistoricalMarketSnapshot",
    "build_historical_market_snapshot",
]
