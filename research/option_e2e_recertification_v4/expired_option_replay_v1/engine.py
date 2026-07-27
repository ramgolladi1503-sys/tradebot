from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

IST = "Asia/Kolkata"
VALID_OPTION_TYPES = {"CE", "PE"}
VALID_PARTITIONS = {"development", "validation", "holdout"}
DEFAULT_MAX_EXPIRY_GAP_DAYS = 7
DEFAULT_MAX_SIGNAL_TO_ENTRY_SECONDS = 120.0


class ReplayDataError(ValueError):
    """Raised when option replay authority is missing or contradictory."""


@dataclass(frozen=True)
class OptionIntent:
    strategy_id: str
    underlying: str
    signal_timestamp: datetime
    earliest_entry_timestamp: datetime
    direction: str
    option_type: str
    underlying_price: float
    expiry_rule: str = "nearest_non_expired"
    strike_rule: str = "ATM"
    strike_offset_steps: int = 0
    signal_identity_hash: str = ""
    partition: str | None = None

    def __post_init__(self) -> None:
        option_type = str(self.option_type).upper()
        if option_type not in VALID_OPTION_TYPES:
            raise ReplayDataError(f"invalid_option_type:{option_type}")
        signal = normalize_ist_timestamp(self.signal_timestamp)
        earliest = normalize_ist_timestamp(self.earliest_entry_timestamp)
        if earliest <= signal:
            raise ReplayDataError("entry_must_be_strictly_after_signal")
        if float(self.underlying_price) <= 0:
            raise ReplayDataError("underlying_price_must_be_positive")
        partition = None if self.partition in (None, "", "nan") else str(self.partition).lower()
        if partition is not None and partition not in VALID_PARTITIONS:
            raise ReplayDataError(f"invalid_partition:{partition}")
        object.__setattr__(self, "option_type", option_type)
        object.__setattr__(self, "underlying", str(self.underlying).upper())
        object.__setattr__(self, "direction", str(self.direction).upper())
        object.__setattr__(self, "signal_timestamp", signal.to_pydatetime())
        object.__setattr__(self, "earliest_entry_timestamp", earliest.to_pydatetime())
        object.__setattr__(self, "partition", partition)


@dataclass(frozen=True)
class Contract:
    underlying: str
    expiry: date
    option_type: str
    strike: float
    instrument_key: str
    trading_symbol: str
    lot_size: int
    raw_contract_path: str
    raw_candle_path: str = ""
    session_dates: tuple[date, ...] = ()

    @property
    def first_session_date(self) -> date | None:
        return min(self.session_dates) if self.session_dates else None

    @property
    def last_session_date(self) -> date | None:
        return max(self.session_dates) if self.session_dates else None

    @property
    def has_price_authority(self) -> bool:
        return bool(self.raw_candle_path and self.session_dates)

    def covers(self, session_date: date) -> bool:
        return session_date in self.session_dates


@dataclass(frozen=True)
class ReplayTrade:
    strategy_id: str
    signal_identity_hash: str
    signal_timestamp: str
    earliest_entry_timestamp: str
    signal_to_entry_seconds: float
    earliest_entry_to_entry_seconds: float
    underlying: str
    underlying_price: float
    option_type: str
    expiry: str
    atm_strike: float
    strike: float
    strike_offset_steps: int
    strike_distance_points: float
    instrument_key: str
    entry_timestamp: str
    entry_price: float
    exit_timestamp: str
    exit_price: float
    exit_reason: str
    quantity: int
    unit_gross_pnl: float
    unit_friction_cost: float
    unit_net_pnl: float
    gross_pnl: float
    friction_cost: float
    net_pnl: float
    gross_return_pct: float
    net_return_pct: float
    return_pct: float
    partition: str
    evidence_lane: str = "PRICE_STRUCTURE_CANDIDATE_OVERLAY"
    overlay_name: str = "COMMON_OPTION_OVERLAY_V1"
    authority: str = "UPSTOX_EXPIRED_OPTION_1M_RAW_RESPONSE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_ist_timestamp(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ReplayDataError("timestamp_is_nat")
    if stamp.tzinfo is None:
        return stamp.tz_localize(IST)
    return stamp.tz_convert(IST)


def strike_step(underlying: str) -> float:
    return 50.0 if str(underlying).upper() == "NIFTY" else 100.0


def exact_atm_strike(underlying: str, price: float) -> float:
    """Round positive index spot to the nearest strike, with ties rounded upward."""
    step = Decimal(str(strike_step(underlying)))
    value = Decimal(str(float(price))) / step
    return float(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReplayDataError(f"invalid_json:{path}:{type(exc).__name__}") from exc


def _candles_from_payload(payload: Any) -> list[list[Any]]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            candles = data.get("candles")
            return list(candles) if isinstance(candles, list) else []
        if isinstance(data, list):
            return list(data)
    if isinstance(payload, list):
        return list(payload)
    return []


def _contract_rows(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [row for row in data if isinstance(row, Mapping)]
        if isinstance(data, dict):
            contracts = data.get("contracts")
            if isinstance(contracts, list):
                return [row for row in contracts if isinstance(row, Mapping)]
    return []


def _instrument_dir_names(instrument_key: str, expiry: date) -> tuple[str, ...]:
    token = str(instrument_key).replace("|", "_")
    names = (
        f"instrument={token}",
        f"instrument={token}_{expiry.strftime('%d-%m-%Y')}",
    )
    return tuple(dict.fromkeys(names))


def _valid_candle_session_dates(candles: Sequence[Sequence[Any]]) -> tuple[date, ...]:
    dates: set[date] = set()
    for candle in candles:
        if not isinstance(candle, (list, tuple)) or len(candle) < 5:
            continue
        try:
            stamp = normalize_ist_timestamp(candle[0])
            open_, high, low, close = (float(candle[pos]) for pos in range(1, 5))
        except Exception:
            continue
        if (
            open_ > 0
            and close > 0
            and low > 0
            and high >= max(open_, close)
            and low <= min(open_, close)
            and high >= low
        ):
            dates.add(stamp.date())
    return tuple(sorted(dates))


def build_contract_universe(
    root: Path, *, underlying: str | None = None
) -> tuple[Contract, ...]:
    """Build metadata authority from every contracts.json row.

    Candle availability is attached when present, but it does not control which
    expiry is considered the nearest market expiry in the supplied universe.
    """
    root = Path(root)
    raw_root = root / "raw" / "responses"
    if not raw_root.exists():
        raise ReplayDataError(f"raw_response_root_missing:{raw_root}")
    out: list[Contract] = []
    for contract_file in sorted(raw_root.glob("*/expiry=*/contracts.json")):
        rows = _contract_rows(_load_json(contract_file))
        for row in rows:
            symbol = str(row.get("underlying_symbol") or row.get("name") or "").upper()
            if underlying and symbol != underlying.upper():
                continue
            option_type = str(row.get("instrument_type") or "").upper()
            if option_type not in VALID_OPTION_TYPES:
                continue
            try:
                expiry = date.fromisoformat(str(row["expiry"]))
                strike = float(row["strike_price"])
            except Exception:
                continue
            instrument_key = str(row.get("instrument_key") or "")
            if not instrument_key:
                continue
            candle_path = next(
                (
                    contract_file.parent / directory_name / "candles_1minute.json"
                    for directory_name in _instrument_dir_names(instrument_key, expiry)
                    if (contract_file.parent / directory_name / "candles_1minute.json").exists()
                ),
                None,
            )
            session_dates: tuple[date, ...] = ()
            if candle_path is not None:
                session_dates = _valid_candle_session_dates(
                    _candles_from_payload(_load_json(candle_path))
                )
            out.append(
                Contract(
                    underlying=symbol,
                    expiry=expiry,
                    option_type=option_type,
                    strike=strike,
                    instrument_key=instrument_key,
                    trading_symbol=str(row.get("trading_symbol") or ""),
                    lot_size=int(float(row.get("lot_size") or row.get("minimum_lot") or 1)),
                    raw_contract_path=str(contract_file.relative_to(root)),
                    raw_candle_path=(
                        str(candle_path.relative_to(root)) if candle_path is not None else ""
                    ),
                    session_dates=session_dates,
                )
            )
    unique = {(item.instrument_key, item.expiry): item for item in out}
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                item.underlying,
                item.expiry,
                item.option_type,
                item.strike,
                item.instrument_key,
            ),
        )
    )


def build_contract_inventory(
    root: Path, *, underlying: str | None = None
) -> tuple[Contract, ...]:
    """Return contracts backed by valid positive same-source raw option candles."""
    return tuple(
        item
        for item in build_contract_universe(root, underlying=underlying)
        if item.has_price_authority
    )


def resolve_expiry(
    intent: OptionIntent,
    contract_universe: Sequence[Contract],
    *,
    max_expiry_gap_days: int = DEFAULT_MAX_EXPIRY_GAP_DAYS,
) -> date:
    if intent.expiry_rule != "nearest_non_expired":
        raise ReplayDataError(f"unsupported_expiry_rule:{intent.expiry_rule}")
    signal_day = intent.signal_timestamp.date()
    expiries = sorted(
        {
            contract.expiry
            for contract in contract_universe
            if contract.underlying == intent.underlying
            and contract.option_type == intent.option_type
            and contract.expiry >= signal_day
        }
    )
    if not expiries:
        raise ReplayDataError("nearest_expiry_metadata_unavailable")
    expiry = expiries[0]
    gap = (expiry - signal_day).days
    if gap < 0 or gap > int(max_expiry_gap_days):
        raise ReplayDataError(
            f"nearest_expiry_universe_gap_exceeds_{int(max_expiry_gap_days)}_days:{expiry.isoformat()}:{gap}"
        )
    return expiry


def resolve_contract(
    intent: OptionIntent,
    contracts: Sequence[Contract],
    *,
    contract_universe: Sequence[Contract] | None = None,
    max_expiry_gap_days: int = DEFAULT_MAX_EXPIRY_GAP_DAYS,
) -> Contract:
    universe = contract_universe if contract_universe is not None else contracts
    expiry = resolve_expiry(
        intent, universe, max_expiry_gap_days=max_expiry_gap_days
    )
    signal_day = intent.signal_timestamp.date()
    eligible = [
        contract
        for contract in contracts
        if contract.underlying == intent.underlying
        and contract.option_type == intent.option_type
        and contract.expiry == expiry
        and contract.covers(signal_day)
    ]
    if not eligible:
        raise ReplayDataError(
            f"nearest_expiry_has_no_same_session_price_authority:{expiry.isoformat()}"
        )
    if intent.strike_rule != "ATM":
        raise ReplayDataError(f"unsupported_strike_rule:{intent.strike_rule}")
    atm = exact_atm_strike(intent.underlying, intent.underlying_price)
    target = atm + float(intent.strike_offset_steps) * strike_step(intent.underlying)
    matches = [item for item in eligible if abs(float(item.strike) - target) < 1e-9]
    if not matches:
        raise ReplayDataError(
            f"exact_atm_contract_unavailable:{expiry.isoformat()}:{target:.1f}"
        )
    return sorted(matches, key=lambda item: item.instrument_key)[0]


@lru_cache(maxsize=2048)
def _load_raw_candles_cached(path_text: str, instrument_key: str) -> pd.DataFrame:
    path = Path(path_text)
    candles = _candles_from_payload(_load_json(path))
    if not candles:
        raise ReplayDataError(f"empty_raw_candles:{contract.instrument_key}")
    rows = []
    for candle in candles:
        if not isinstance(candle, (list, tuple)) or len(candle) < 5:
            continue
        rows.append(
            {
                "timestamp": candle[0],
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
                "volume": candle[5] if len(candle) > 5 else 0,
                "open_interest": candle[6] if len(candle) > 6 else None,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ReplayDataError(f"no_well_formed_candles:{contract.instrument_key}")
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"], errors="coerce", utc=True
    ).dt.tz_convert(IST)
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    valid = (
        frame["timestamp"].notna()
        & (frame["open"] > 0)
        & (frame["close"] > 0)
        & (frame["high"] >= frame[["open", "close"]].max(axis=1))
        & (frame["low"] <= frame[["open", "close"]].min(axis=1))
        & (frame["low"] > 0)
        & (frame["high"] >= frame["low"])
    )
    frame = (
        frame.loc[valid]
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )
    if frame.empty:
        raise ReplayDataError(f"no_valid_positive_ohlc:{contract.instrument_key}")
    return frame


def load_raw_candles(root: Path, contract: Contract) -> pd.DataFrame:
    if not contract.raw_candle_path:
        raise ReplayDataError(f"contract_has_no_raw_candle_path:{contract.instrument_key}")
    path = (Path(root) / contract.raw_candle_path).resolve()
    return _load_raw_candles_cached(str(path), contract.instrument_key).copy()


def replay_intent(
    intent: OptionIntent,
    root: Path,
    contracts: Sequence[Contract],
    *,
    partition: str,
    contract_universe: Sequence[Contract] | None = None,
    max_hold_minutes: int = 30,
    stop_loss_pct: float = 0.25,
    target_pct: float = 0.375,
    friction_bps_per_side: float = 5.0,
    max_signal_to_entry_seconds: float = DEFAULT_MAX_SIGNAL_TO_ENTRY_SECONDS,
    max_expiry_gap_days: int = DEFAULT_MAX_EXPIRY_GAP_DAYS,
) -> ReplayTrade:
    if partition not in VALID_PARTITIONS:
        raise ReplayDataError(f"invalid_replay_partition:{partition}")
    contract = resolve_contract(
        intent,
        contracts,
        contract_universe=contract_universe,
        max_expiry_gap_days=max_expiry_gap_days,
    )
    frame = load_raw_candles(root, contract)
    signal_stamp = normalize_ist_timestamp(intent.signal_timestamp)
    entry_at = normalize_ist_timestamp(intent.earliest_entry_timestamp)
    signal_day = signal_stamp.date()
    frame = frame.loc[frame["timestamp"].dt.date == signal_day].reset_index(drop=True)
    if frame.empty:
        raise ReplayDataError("selected_contract_has_no_same_session_candles")

    legal = frame.loc[frame["timestamp"] >= entry_at]
    if legal.empty:
        raise ReplayDataError("no_legal_same_session_entry_bar")
    entry_index = int(legal.index[0])
    entry_row = frame.loc[entry_index]
    entry_stamp = pd.Timestamp(entry_row["timestamp"])
    if entry_stamp <= signal_stamp:
        raise ReplayDataError("entry_not_strictly_after_signal")
    signal_lag = float((entry_stamp - signal_stamp).total_seconds())
    earliest_lag = float((entry_stamp - entry_at).total_seconds())
    if signal_lag > float(max_signal_to_entry_seconds):
        raise ReplayDataError(
            f"signal_to_entry_lag_exceeds_{float(max_signal_to_entry_seconds):g}_seconds:{signal_lag:g}"
        )

    entry_price = float(entry_row["open"])
    stop = entry_price * (1.0 - stop_loss_pct)
    target = entry_price * (1.0 + target_pct)
    deadline = min(
        entry_stamp + pd.Timedelta(minutes=max_hold_minutes),
        pd.Timestamp(f"{signal_day.isoformat()} 15:29:00", tz=IST),
    )
    window = frame.loc[
        (frame.index >= entry_index) & (frame["timestamp"] <= deadline)
    ]
    if window.empty:
        raise ReplayDataError("empty_same_session_exit_window")
    exit_row = window.iloc[-1]
    exit_price = float(exit_row["close"])
    reason = "time_exit"
    for _, row in window.iterrows():
        row_open = float(row["open"])
        if float(row["low"]) <= stop:
            exit_row = row
            exit_price = min(stop, row_open)  # adverse gap-through fill for a long option
            reason = "stop"
            break
        if float(row["high"]) >= target:
            exit_row = row
            exit_price = target  # conservative target fill; never outside authoritative OHLC
            reason = "target"
            break

    quantity = max(1, int(contract.lot_size))
    unit_gross = exit_price - entry_price
    unit_friction = (
        (entry_price + exit_price) * friction_bps_per_side / 10000.0
    )
    unit_net = unit_gross - unit_friction
    gross = unit_gross * quantity
    friction = unit_friction * quantity
    net = unit_net * quantity
    atm = exact_atm_strike(intent.underlying, intent.underlying_price)
    gross_return_pct = unit_gross / entry_price * 100.0
    net_return_pct = unit_net / entry_price * 100.0
    return ReplayTrade(
        strategy_id=intent.strategy_id,
        signal_identity_hash=intent.signal_identity_hash,
        signal_timestamp=str(signal_stamp),
        earliest_entry_timestamp=str(entry_at),
        signal_to_entry_seconds=signal_lag,
        earliest_entry_to_entry_seconds=earliest_lag,
        underlying=intent.underlying,
        underlying_price=float(intent.underlying_price),
        option_type=intent.option_type,
        expiry=contract.expiry.isoformat(),
        atm_strike=atm,
        strike=contract.strike,
        strike_offset_steps=int(intent.strike_offset_steps),
        strike_distance_points=float(contract.strike - atm),
        instrument_key=contract.instrument_key,
        entry_timestamp=str(entry_stamp),
        entry_price=entry_price,
        exit_timestamp=str(exit_row["timestamp"]),
        exit_price=float(exit_price),
        exit_reason=reason,
        quantity=quantity,
        unit_gross_pnl=unit_gross,
        unit_friction_cost=unit_friction,
        unit_net_pnl=unit_net,
        gross_pnl=gross,
        friction_cost=friction,
        net_pnl=net,
        gross_return_pct=gross_return_pct,
        net_return_pct=net_return_pct,
        return_pct=net_return_pct,
        partition=partition,
    )


def profit_factor(values: Iterable[float]) -> float | None:
    values = [float(value) for value in values]
    positive = sum(value for value in values if value > 0)
    negative = -sum(value for value in values if value < 0)
    if negative == 0:
        return math.inf if positive > 0 else None
    return positive / negative


def value_metrics(values: Sequence[float]) -> dict[str, Any]:
    pnl = [float(value) for value in values]
    equity = pd.Series(pnl, dtype=float).cumsum()
    drawdown = float((equity.cummax() - equity).max()) if not equity.empty else 0.0
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    return {
        "trades": len(pnl),
        "profit_factor": profit_factor(pnl),
        "net_pnl": sum(pnl),
        "expectancy": sum(pnl) / len(pnl) if pnl else None,
        "win_rate": len(wins) / len(pnl) if pnl else None,
        "payoff_ratio": (
            (sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
            if wins and losses
            else None
        ),
        "maximum_drawdown": drawdown,
    }


def metrics(
    trades: Sequence[ReplayTrade], *, normalization: str = "one_lot_rupee"
) -> dict[str, Any]:
    ordered = sorted(trades, key=lambda trade: trade.entry_timestamp)
    if normalization == "one_lot_rupee":
        values = [trade.net_pnl for trade in ordered]
    elif normalization == "per_option_unit":
        values = [trade.unit_net_pnl for trade in ordered]
    elif normalization == "net_return_pct":
        values = [trade.net_return_pct for trade in ordered]
    else:
        raise ReplayDataError(f"unsupported_metric_normalization:{normalization}")
    return {"normalization": normalization, **value_metrics(values)}


def chronological_partitions(
    intents: Sequence[OptionIntent],
    development: float = 0.6,
    validation: float = 0.2,
) -> dict[str, set[date]]:
    dates = sorted({intent.signal_timestamp.date() for intent in intents})
    dev_end = int(len(dates) * development)
    val_end = int(len(dates) * (development + validation))
    return {
        "development": set(dates[:dev_end]),
        "validation": set(dates[dev_end:val_end]),
        "holdout": set(dates[val_end:]),
    }


def semantic_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
