from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

IST = "Asia/Kolkata"
VALID_OPTION_TYPES = {"CE", "PE"}
VALID_PARTITIONS = {"development", "validation", "holdout"}


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
        if self.earliest_entry_timestamp <= self.signal_timestamp:
            raise ReplayDataError("entry_must_be_strictly_after_signal")
        if float(self.underlying_price) <= 0:
            raise ReplayDataError("underlying_price_must_be_positive")
        partition = None if self.partition in (None, "", "nan") else str(self.partition).lower()
        if partition is not None and partition not in VALID_PARTITIONS:
            raise ReplayDataError(f"invalid_partition:{partition}")
        object.__setattr__(self, "option_type", option_type)
        object.__setattr__(self, "underlying", str(self.underlying).upper())
        object.__setattr__(self, "direction", str(self.direction).upper())
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
    raw_candle_path: str
    session_dates: tuple[date, ...] = ()

    @property
    def first_session_date(self) -> date | None:
        return min(self.session_dates) if self.session_dates else None

    @property
    def last_session_date(self) -> date | None:
        return max(self.session_dates) if self.session_dates else None

    def covers(self, session_date: date) -> bool:
        return not self.session_dates or session_date in self.session_dates


@dataclass(frozen=True)
class ReplayTrade:
    strategy_id: str
    signal_identity_hash: str
    signal_timestamp: str
    earliest_entry_timestamp: str
    signal_to_entry_seconds: float
    underlying: str
    option_type: str
    expiry: str
    strike: float
    instrument_key: str
    entry_timestamp: str
    entry_price: float
    exit_timestamp: str
    exit_price: float
    exit_reason: str
    quantity: int
    gross_pnl: float
    friction_cost: float
    net_pnl: float
    return_pct: float
    partition: str
    authority: str = "UPSTOX_EXPIRED_OPTION_1M_RAW_RESPONSE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def _instrument_dir_name(instrument_key: str, expiry: date) -> str:
    token = str(instrument_key).replace("|", "_")
    return f"instrument={token}_{expiry.strftime('%d-%m-%Y')}"


def _valid_candle_session_dates(candles: Sequence[Sequence[Any]]) -> tuple[date, ...]:
    dates: set[date] = set()
    for candle in candles:
        if not isinstance(candle, (list, tuple)) or len(candle) < 5:
            continue
        try:
            stamp = pd.Timestamp(candle[0])
            if stamp.tzinfo is None:
                stamp = stamp.tz_localize(IST)
            else:
                stamp = stamp.tz_convert(IST)
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


def build_contract_inventory(
    root: Path, *, underlying: str | None = None
) -> tuple[Contract, ...]:
    """Build authority-backed inventory from contracts.json plus valid raw candles.

    Normalized parquet existence is deliberately ignored as proof of data. A contract
    is admitted only when its raw Upstox response contains valid positive OHLC, and
    its actual covered trading dates are frozen into the inventory.
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
            candle_path = (
                contract_file.parent
                / _instrument_dir_name(instrument_key, expiry)
                / "candles_1minute.json"
            )
            if not candle_path.exists():
                continue
            candles = _candles_from_payload(_load_json(candle_path))
            session_dates = _valid_candle_session_dates(candles)
            if not session_dates:
                continue
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
                    raw_candle_path=str(candle_path.relative_to(root)),
                    session_dates=session_dates,
                )
            )
    unique = {(contract.instrument_key, contract.expiry): contract for contract in out}
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                item.underlying,
                item.expiry,
                item.option_type,
                item.strike,
            ),
        )
    )


def resolve_expiry(intent: OptionIntent, contracts: Sequence[Contract]) -> date:
    signal_day = intent.signal_timestamp.date()
    expiries = sorted(
        {
            contract.expiry
            for contract in contracts
            if contract.underlying == intent.underlying
            and contract.option_type == intent.option_type
            and contract.expiry >= signal_day
            and contract.covers(signal_day)
        }
    )
    if not expiries:
        raise ReplayDataError("no_contract_with_same_session_price_authority")
    if intent.expiry_rule != "nearest_non_expired":
        raise ReplayDataError(f"unsupported_expiry_rule:{intent.expiry_rule}")
    return expiries[0]


def resolve_contract(intent: OptionIntent, contracts: Sequence[Contract]) -> Contract:
    expiry = resolve_expiry(intent, contracts)
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
        raise ReplayDataError("resolved_expiry_has_no_same_session_contracts")
    strikes = sorted({contract.strike for contract in eligible})
    positive_diffs = [
        later - earlier
        for earlier, later in zip(strikes, strikes[1:])
        if later > earlier
    ]
    step = min(positive_diffs) if positive_diffs else (
        50.0 if intent.underlying == "NIFTY" else 100.0
    )
    if intent.strike_rule != "ATM":
        raise ReplayDataError(f"unsupported_strike_rule:{intent.strike_rule}")
    atm = min(strikes, key=lambda strike: (abs(strike - intent.underlying_price), strike))
    target = atm + float(intent.strike_offset_steps) * step
    return min(
        eligible,
        key=lambda contract: (
            abs(contract.strike - target),
            abs(contract.strike - intent.underlying_price),
            contract.strike,
        ),
    )


def load_raw_candles(root: Path, contract: Contract) -> pd.DataFrame:
    path = Path(root) / contract.raw_candle_path
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


def replay_intent(
    intent: OptionIntent,
    root: Path,
    contracts: Sequence[Contract],
    *,
    partition: str,
    max_hold_minutes: int = 30,
    stop_loss_pct: float = 0.25,
    target_pct: float = 0.375,
    friction_bps_per_side: float = 5.0,
) -> ReplayTrade:
    if partition not in VALID_PARTITIONS:
        raise ReplayDataError(f"invalid_replay_partition:{partition}")
    contract = resolve_contract(intent, contracts)
    frame = load_raw_candles(root, contract)
    signal_day = intent.signal_timestamp.date()
    frame = frame.loc[frame["timestamp"].dt.date == signal_day].reset_index(drop=True)
    if frame.empty:
        raise ReplayDataError("selected_contract_has_no_same_session_candles")

    entry_at = pd.Timestamp(intent.earliest_entry_timestamp)
    if entry_at.tzinfo is None:
        entry_at = entry_at.tz_localize(IST)
    else:
        entry_at = entry_at.tz_convert(IST)
    legal = frame.loc[frame["timestamp"] >= entry_at]
    if legal.empty:
        raise ReplayDataError("no_legal_same_session_entry_bar")
    entry_index = int(legal.index[0])
    entry_row = frame.loc[entry_index]
    entry_price = float(entry_row["open"])
    stop = entry_price * (1.0 - stop_loss_pct)
    target = entry_price * (1.0 + target_pct)
    deadline = min(
        entry_row["timestamp"] + pd.Timedelta(minutes=max_hold_minutes),
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
        if float(row["low"]) <= stop:
            exit_row, exit_price, reason = row, stop, "stop"
            break
        if float(row["high"]) >= target:
            exit_row, exit_price, reason = row, target, "target"
            break
    quantity = max(1, int(contract.lot_size))
    gross = (exit_price - entry_price) * quantity
    friction = (
        (entry_price + exit_price)
        * quantity
        * friction_bps_per_side
        / 10000.0
    )
    net = gross - friction
    entry_stamp = pd.Timestamp(entry_row["timestamp"])
    signal_stamp = pd.Timestamp(intent.signal_timestamp)
    if signal_stamp.tzinfo is None:
        signal_stamp = signal_stamp.tz_localize(IST)
    else:
        signal_stamp = signal_stamp.tz_convert(IST)
    return ReplayTrade(
        strategy_id=intent.strategy_id,
        signal_identity_hash=intent.signal_identity_hash,
        signal_timestamp=str(signal_stamp),
        earliest_entry_timestamp=str(entry_at),
        signal_to_entry_seconds=float((entry_stamp - signal_stamp).total_seconds()),
        underlying=intent.underlying,
        option_type=intent.option_type,
        expiry=contract.expiry.isoformat(),
        strike=contract.strike,
        instrument_key=contract.instrument_key,
        entry_timestamp=str(entry_stamp),
        entry_price=entry_price,
        exit_timestamp=str(exit_row["timestamp"]),
        exit_price=float(exit_price),
        exit_reason=reason,
        quantity=quantity,
        gross_pnl=gross,
        friction_cost=friction,
        net_pnl=net,
        return_pct=(exit_price / entry_price - 1.0) * 100.0,
        partition=partition,
    )


def profit_factor(values: Iterable[float]) -> float | None:
    values = [float(value) for value in values]
    positive = sum(value for value in values if value > 0)
    negative = -sum(value for value in values if value < 0)
    if negative == 0:
        return math.inf if positive > 0 else None
    return positive / negative


def metrics(trades: Sequence[ReplayTrade]) -> dict[str, Any]:
    ordered = sorted(trades, key=lambda trade: trade.entry_timestamp)
    pnl = [trade.net_pnl for trade in ordered]
    equity = pd.Series(pnl, dtype=float).cumsum()
    drawdown = float((equity.cummax() - equity).max()) if not equity.empty else 0.0
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    return {
        "trades": len(ordered),
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
