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

    def __post_init__(self) -> None:
        option_type = str(self.option_type).upper()
        if option_type not in VALID_OPTION_TYPES:
            raise ReplayDataError(f"invalid_option_type:{option_type}")
        if self.earliest_entry_timestamp <= self.signal_timestamp:
            raise ReplayDataError("entry_must_be_strictly_after_signal")
        if float(self.underlying_price) <= 0:
            raise ReplayDataError("underlying_price_must_be_positive")
        object.__setattr__(self, "option_type", option_type)
        object.__setattr__(self, "underlying", str(self.underlying).upper())


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


@dataclass(frozen=True)
class ReplayTrade:
    strategy_id: str
    signal_identity_hash: str
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


def build_contract_inventory(root: Path, *, underlying: str | None = None) -> tuple[Contract, ...]:
    """Build authority-backed inventory from contracts.json plus non-empty raw candles.

    Normalized parquet existence is deliberately ignored as proof of data. A contract
    is admitted only when its raw Upstox response exists and contains at least one
    candle.
    """
    raw_root = Path(root) / "raw" / "responses"
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
            expiry = date.fromisoformat(str(row["expiry"]))
            instrument_key = str(row.get("instrument_key") or "")
            if not instrument_key:
                continue
            candle_path = contract_file.parent / _instrument_dir_name(instrument_key, expiry) / "candles_1minute.json"
            if not candle_path.exists():
                continue
            candles = _candles_from_payload(_load_json(candle_path))
            if not candles:
                continue
            out.append(
                Contract(
                    underlying=symbol,
                    expiry=expiry,
                    option_type=option_type,
                    strike=float(row["strike_price"]),
                    instrument_key=instrument_key,
                    trading_symbol=str(row.get("trading_symbol") or ""),
                    lot_size=int(float(row.get("lot_size") or row.get("minimum_lot") or 1)),
                    raw_contract_path=str(contract_file.relative_to(root)),
                    raw_candle_path=str(candle_path.relative_to(root)),
                )
            )
    unique = {(c.instrument_key, c.expiry): c for c in out}
    return tuple(sorted(unique.values(), key=lambda c: (c.underlying, c.expiry, c.option_type, c.strike)))


def resolve_expiry(intent: OptionIntent, contracts: Sequence[Contract]) -> date:
    signal_day = intent.signal_timestamp.date()
    expiries = sorted({c.expiry for c in contracts if c.underlying == intent.underlying and c.option_type == intent.option_type and c.expiry >= signal_day})
    if not expiries:
        raise ReplayDataError("no_non_expired_contract_for_signal")
    if intent.expiry_rule != "nearest_non_expired":
        raise ReplayDataError(f"unsupported_expiry_rule:{intent.expiry_rule}")
    return expiries[0]


def resolve_contract(intent: OptionIntent, contracts: Sequence[Contract]) -> Contract:
    expiry = resolve_expiry(intent, contracts)
    eligible = [c for c in contracts if c.underlying == intent.underlying and c.option_type == intent.option_type and c.expiry == expiry]
    if not eligible:
        raise ReplayDataError("resolved_expiry_has_no_contracts")
    strikes = sorted({c.strike for c in eligible})
    if len(strikes) > 1:
        step = min(b - a for a, b in zip(strikes, strikes[1:]) if b > a)
    else:
        step = 50.0 if intent.underlying == "NIFTY" else 100.0
    if intent.strike_rule != "ATM":
        raise ReplayDataError(f"unsupported_strike_rule:{intent.strike_rule}")
    atm = min(strikes, key=lambda strike: (abs(strike - intent.underlying_price), strike))
    target = atm + float(intent.strike_offset_steps) * step
    return min(eligible, key=lambda c: (abs(c.strike - target), abs(c.strike - intent.underlying_price), c.strike))


def load_raw_candles(root: Path, contract: Contract) -> pd.DataFrame:
    path = Path(root) / contract.raw_candle_path
    candles = _candles_from_payload(_load_json(path))
    if not candles:
        raise ReplayDataError(f"empty_raw_candles:{contract.instrument_key}")
    rows = []
    for candle in candles:
        if not isinstance(candle, (list, tuple)) or len(candle) < 5:
            continue
        rows.append({
            "timestamp": candle[0],
            "open": candle[1],
            "high": candle[2],
            "low": candle[3],
            "close": candle[4],
            "volume": candle[5] if len(candle) > 5 else 0,
            "open_interest": candle[6] if len(candle) > 6 else None,
        })
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ReplayDataError(f"no_well_formed_candles:{contract.instrument_key}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True).dt.tz_convert(IST)
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    valid = (
        frame["timestamp"].notna()
        & (frame["open"] > 0)
        & (frame["high"] >= frame[["open", "close"]].max(axis=1))
        & (frame["low"] <= frame[["open", "close"]].min(axis=1))
        & (frame["low"] > 0)
    )
    frame = frame.loc[valid].sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
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
    contract = resolve_contract(intent, contracts)
    frame = load_raw_candles(root, contract)
    entry_at = pd.Timestamp(intent.earliest_entry_timestamp)
    if entry_at.tzinfo is None:
        entry_at = entry_at.tz_localize(IST)
    else:
        entry_at = entry_at.tz_convert(IST)
    legal = frame.loc[frame["timestamp"] >= entry_at]
    if legal.empty:
        raise ReplayDataError("no_legal_entry_bar")
    entry_index = int(legal.index[0])
    entry_row = frame.loc[entry_index]
    entry_price = float(entry_row["open"])
    stop = entry_price * (1.0 - stop_loss_pct)
    target = entry_price * (1.0 + target_pct)
    deadline = entry_row["timestamp"] + pd.Timedelta(minutes=max_hold_minutes)
    window = frame.loc[(frame.index >= entry_index) & (frame["timestamp"] <= deadline)]
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
    friction = (entry_price + exit_price) * quantity * friction_bps_per_side / 10000.0
    net = gross - friction
    return ReplayTrade(
        strategy_id=intent.strategy_id,
        signal_identity_hash=intent.signal_identity_hash,
        underlying=intent.underlying,
        option_type=intent.option_type,
        expiry=contract.expiry.isoformat(),
        strike=contract.strike,
        instrument_key=contract.instrument_key,
        entry_timestamp=str(entry_row["timestamp"]),
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
    values = [float(v) for v in values]
    positive = sum(v for v in values if v > 0)
    negative = -sum(v for v in values if v < 0)
    if negative == 0:
        return math.inf if positive > 0 else None
    return positive / negative


def metrics(trades: Sequence[ReplayTrade]) -> dict[str, Any]:
    pnl = [trade.net_pnl for trade in trades]
    equity = pd.Series(pnl, dtype=float).cumsum()
    drawdown = float((equity.cummax() - equity).max()) if not equity.empty else 0.0
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    return {
        "trades": len(trades),
        "profit_factor": profit_factor(pnl),
        "net_pnl": sum(pnl),
        "expectancy": sum(pnl) / len(pnl) if pnl else None,
        "win_rate": len(wins) / len(pnl) if pnl else None,
        "payoff_ratio": (sum(wins) / len(wins)) / abs(sum(losses) / len(losses)) if wins and losses else None,
        "maximum_drawdown": drawdown,
    }


def chronological_partitions(intents: Sequence[OptionIntent], development: float = 0.6, validation: float = 0.2) -> dict[str, set[date]]:
    dates = sorted({intent.signal_timestamp.date() for intent in intents})
    dev_end = int(len(dates) * development)
    val_end = int(len(dates) * (development + validation))
    return {
        "development": set(dates[:dev_end]),
        "validation": set(dates[dev_end:val_end]),
        "holdout": set(dates[val_end:]),
    }


def semantic_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
