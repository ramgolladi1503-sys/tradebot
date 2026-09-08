from __future__ import annotations

import json, math
from dataclasses import dataclass, asdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

IST = 'Asia/Kolkata'

@dataclass(frozen=True)
class Policy:
    max_strike_distance: float = 100.0
    confirmation_lookback_minutes: int = 5
    minimum_entry_premium: float = 30.0
    entry_delay_minutes: int = 1
    maximum_signal_to_entry_seconds: int = 120
    holding_minutes: int = 20
    friction_bps_per_side: float = 5.0


def normalize_ts(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize(IST) if stamp.tzinfo is None else stamp.tz_convert(IST)


def round_atm(price: float) -> float:
    return float((Decimal(str(float(price))) / Decimal('50')).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * Decimal('50'))


def profit_factor(values: Iterable[float]) -> float | None:
    vals = [float(v) for v in values]
    gain = sum(v for v in vals if v > 0)
    loss = -sum(v for v in vals if v < 0)
    if loss > 0:
        return gain / loss
    return math.inf if gain > 0 else None


def metrics(rows: pd.DataFrame) -> dict[str, Any]:
    vals = rows['return_pct'].astype(float).tolist() if not rows.empty else []
    return {
        'trades': len(vals),
        'profit_factor': profit_factor(vals),
        'mean_return_pct': sum(vals) / len(vals) if vals else None,
        'median_return_pct': float(pd.Series(vals).median()) if vals else None,
        'win_rate': sum(v > 0 for v in vals) / len(vals) if vals else None,
        'net_return_pct_sum': sum(vals),
    }


def load_candles(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text())
    raw = (payload.get('data') or {}).get('candles', []) if isinstance(payload, dict) else payload
    out: list[dict[str, Any]] = []
    for row in raw or []:
        if len(row) < 7:
            continue
        try:
            stamp = normalize_ts(row[0]); o, h, l, c = map(float, row[1:5])
            if min(o, h, l, c) <= 0 or h < max(o, c) or l > min(o, c):
                continue
            out.append({'timestamp': stamp, 'open': o, 'high': h, 'low': l, 'close': c,
                        'volume': float(row[5] or 0), 'open_interest': float(row[6] or 0)})
        except Exception:
            continue
    return sorted(out, key=lambda x: x['timestamp'])


def causal_confirmation(candles: list[dict[str, Any]], signal: pd.Timestamp, lookback_minutes: int) -> dict[str, Any] | None:
    # A one-minute candle is complete only when start + 1 minute <= signal.
    completed = [r for r in candles if r['timestamp'] + pd.Timedelta(minutes=1) <= signal]
    if not completed:
        return None
    last = completed[-1]
    prior = [r for r in completed if r['timestamp'] <= last['timestamp'] - pd.Timedelta(minutes=lookback_minutes)]
    if not prior or prior[-1]['close'] <= 0:
        return None
    anchor = prior[-1]
    return {
        'last_completed_timestamp': last['timestamp'],
        'anchor_timestamp': anchor['timestamp'],
        'premium_change_pct': (last['close'] / anchor['close'] - 1.0) * 100.0,
        'last_volume': last['volume'],
        'last_open_interest': last['open_interest'],
    }


def replay_one(intent: dict[str, Any], contract: dict[str, Any], policy: Policy) -> dict[str, Any] | None:
    signal = normalize_ts(intent['signal_timestamp'])
    session = [r for r in load_candles(contract['path']) if r['timestamp'].date() == signal.date()]
    confirmation = causal_confirmation(session, signal, policy.confirmation_lookback_minutes)
    if not confirmation or confirmation['premium_change_pct'] <= 0:
        return None
    earliest = signal + pd.Timedelta(minutes=policy.entry_delay_minutes)
    legal = [r for r in session if r['timestamp'] >= earliest]
    if not legal:
        return None
    entry_bar = legal[0]
    lag = (entry_bar['timestamp'] - signal).total_seconds()
    if entry_bar['timestamp'] <= signal or lag > policy.maximum_signal_to_entry_seconds:
        return None
    if entry_bar['open'] < policy.minimum_entry_premium:
        return None
    deadline = min(entry_bar['timestamp'] + pd.Timedelta(minutes=policy.holding_minutes),
                   pd.Timestamp(f'{signal.date()} 15:29:00', tz=IST))
    window = [r for r in session if entry_bar['timestamp'] <= r['timestamp'] <= deadline]
    if not window:
        return None
    exit_bar = window[-1]
    friction = (entry_bar['open'] + exit_bar['close']) * policy.friction_bps_per_side / 10000.0
    net = exit_bar['close'] - entry_bar['open'] - friction
    return {
        **intent,
        'expiry': contract['expiry'].isoformat() if isinstance(contract['expiry'], date) else str(contract['expiry']),
        'strike': float(contract['strike']),
        'atm': round_atm(float(intent['underlying_price'])),
        'strike_distance': float(contract['strike']) - round_atm(float(intent['underlying_price'])),
        'entry_timestamp': entry_bar['timestamp'].isoformat(),
        'exit_timestamp': exit_bar['timestamp'].isoformat(),
        'signal_to_entry_seconds': lag,
        'entry_premium': entry_bar['open'],
        'exit_premium': exit_bar['close'],
        'unit_net': net,
        'return_pct': net / entry_bar['open'] * 100.0,
        **confirmation,
    }


def summarize(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for partition, group in trades.groupby('partition'):
        rows.append({'partition': partition, **metrics(group)})
        ordered = group.sort_values('return_pct', ascending=False)
        for remove in (1, 2):
            rows.append({'partition': partition, 'control': f'remove_top_{remove}', **metrics(ordered.iloc[remove:])})
        capped = group.copy(); capped['return_pct'] = capped['return_pct'].clip(upper=50.0)
        rows.append({'partition': partition, 'control': 'cap_winners_at_50pct', **metrics(capped)})
    return pd.DataFrame(rows)


def policy_dict(policy: Policy) -> dict[str, Any]:
    return asdict(policy)
