"""Point-in-Time Low-Premium Strike Selector.

Identifies low-premium option contracts mapping to the predetermined
ladder tiers: [38, 48, 58, 68, 88, 128].

Selection criteria:
- Evaluated strictly at or before 09:19:00 / 09:20:00 (no future bar leakage)
- Matches target ladder tiers based on current morning premium
- Nearest weekly/monthly expiry
- Valid lot size
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Union
import numpy as np
import pandas as pd

# Predetermined Option Ladder tiers in INR points
PREMIUM_LADDER_TIERS: tuple[float, ...] = (38.0, 48.0, 58.0, 68.0, 88.0, 128.0)


@dataclass(frozen=True)
class RankedStrikeCandidate:
    """Strike candidate with composite score across premium tier alignment and liquidity/spread metrics."""
    date: str
    expiry: str
    strike: float
    option_type: str  # 'CE' or 'PE'
    premium_at_eval: float
    matched_tier: float
    distance_to_tier: float
    lot_size: int
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    spread_pct: Optional[float] = None
    composite_score: float = 0.0

    def validate(self) -> None:
        if self.strike <= 0:
            raise ValueError(f"Strike must be positive: {self.strike}")
        if self.option_type not in ('CE', 'PE'):
            raise ValueError(f"option_type must be CE or PE: {self.option_type}")
        if self.premium_at_eval <= 0:
            raise ValueError(f"premium_at_eval must be positive: {self.premium_at_eval}")
        if self.lot_size <= 0:
            raise ValueError(f"lot_size must be positive: {self.lot_size}")
        if self.expiry < self.date:
            raise ValueError(f"expiry ({self.expiry}) < date ({self.date})")
        if self.bid is not None and self.bid < 0:
            raise ValueError(f"bid cannot be negative: {self.bid}")
        if self.ask is not None and self.ask < 0:
            raise ValueError(f"ask cannot be negative: {self.ask}")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError(f"bid ({self.bid}) cannot exceed ask ({self.ask})")


class MultiStrikeChainRanker:
    """Point-in-time multi-strike chain ranker evaluating options by premium tier proximity and spread penalty."""

    def __init__(
        self,
        allowed_tiers: Sequence[float] = PREMIUM_LADDER_TIERS,
        spread_penalty_weight: float = 0.5,
    ):
        self.allowed_tiers = tuple(sorted(allowed_tiers))
        self.spread_penalty_weight = float(spread_penalty_weight)

    def rank_chain_at_timestamp(
        self,
        contracts_df: pd.DataFrame,
        date: str,
        option_type: str,
        eval_timestamp: Union[str, pd.Timestamp],
        target_tier: Optional[float] = None,
        max_tier_distance: Optional[float] = None,
        max_spread_pct: Optional[float] = None,
        top_k: int = 5,
    ) -> List[RankedStrikeCandidate]:
        """Rank option contracts point-in-time strictly up to eval_timestamp.

        Composite score:
            tier_penalty = distance_to_tier
            spread_penalty = (spread_pct * premium) * spread_penalty_weight (or 0 if spread unavailable)
            composite_score = tier_penalty + spread_penalty

        Lower composite_score is better (closest to ideal tier with minimal execution friction).
        """
        if top_k <= 0:
            raise ValueError(f"top_k must be positive, got {top_k}")
        if max_tier_distance is not None and max_tier_distance < 0:
            raise ValueError(f"max_tier_distance must be non-negative, got {max_tier_distance}")
        if max_spread_pct is not None and max_spread_pct < 0:
            raise ValueError(f"max_spread_pct must be non-negative, got {max_spread_pct}")

        eval_ts = pd.to_datetime(eval_timestamp)
        df = contracts_df.copy()

        if 'timestamp' not in df.columns:
            raise ValueError("contracts_df must contain 'timestamp' column for causal point-in-time ranking")

        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            df['timestamp'] = pd.to_datetime(df['timestamp'])

        df['date_str'] = df['timestamp'].dt.strftime('%Y-%m-%d')
        # Strict causal filter: strictly <= eval_ts and same date
        df = df[(df['date_str'] == date) & (df['timestamp'] <= eval_ts)]

        if df.empty:
            return []

        if 'option_type' in df.columns:
            df['option_type'] = df['option_type'].astype(str).str.upper()
            df = df[df['option_type'] == option_type.upper()]

        if df.empty:
            return []

        # Filter to nearest expiry on or after date
        df['expiry_str'] = pd.to_datetime(df['expiry']).dt.strftime('%Y-%m-%d')
        valid_expiries = df[df['expiry_str'] >= date]['expiry_str']
        if valid_expiries.empty:
            return []
        nearest_exp = valid_expiries.min()
        df = df[df['expiry_str'] == nearest_exp]

        if df.empty:
            return []

        # Point-in-time: Take the latest bar available on or before eval_timestamp per strike
        df = df.sort_values('timestamp').groupby(['expiry', 'strike', 'option_type']).last().reset_index()

        tiers = [target_tier] if target_tier is not None else list(self.allowed_tiers)
        candidates: List[RankedStrikeCandidate] = []

        for _, row in df.iterrows():
            premium = float(row.get('close', row.get('open', 0.0)))
            if premium <= 0:
                continue

            strike = float(row['strike'])
            lot_size = int(row.get('lot_size', 50))

            # Matched tier calculation
            distances = [abs(premium - t) for t in tiers]
            best_idx = int(np.argmin(distances))
            dist = distances[best_idx]
            matched_tier = tiers[best_idx]

            if max_tier_distance is not None and dist > max_tier_distance:
                continue

            bid = float(row['bid']) if 'bid' in row and pd.notna(row['bid']) else None
            ask = float(row['ask']) if 'ask' in row and pd.notna(row['ask']) else None
            spread = None
            spread_pct = None

            if bid is not None and ask is not None and ask >= bid:
                spread = ask - bid
                spread_pct = spread / premium if premium > 0 else 0.0

            if max_spread_pct is not None and spread_pct is not None and spread_pct > max_spread_pct:
                continue

            # Composite score calculation:
            # tier distance penalty + weighted spread friction
            # Lower score = better rank
            spread_friction = (spread if spread is not None else 0.0) * self.spread_penalty_weight
            comp_score = float(dist + spread_friction)

            cand = RankedStrikeCandidate(
                date=date,
                expiry=nearest_exp,
                strike=strike,
                option_type=option_type.upper(),
                premium_at_eval=premium,
                matched_tier=matched_tier,
                distance_to_tier=dist,
                lot_size=lot_size,
                bid=bid,
                ask=ask,
                spread=spread,
                spread_pct=spread_pct,
                composite_score=comp_score,
            )
            cand.validate()
            candidates.append(cand)

        # Sort: lowest composite score first, then lowest distance, then closest to matched tier
        candidates.sort(key=lambda c: (c.composite_score, c.distance_to_tier, abs(c.premium_at_eval - c.matched_tier)))
        return candidates[:top_k]


@dataclass(frozen=True)
class OptionContractCandidate:
    """Option contract candidate evaluated at a point in time."""
    date: str
    expiry: str
    strike: float
    option_type: str  # 'CE' or 'PE'
    premium_at_eval: float
    matched_tier: float
    distance_to_tier: float
    lot_size: int

    def validate(self) -> None:
        if self.strike <= 0:
            raise ValueError(f"Strike must be positive: {self.strike}")
        if self.option_type not in ('CE', 'PE'):
            raise ValueError(f"option_type must be CE or PE: {self.option_type}")
        if self.premium_at_eval <= 0:
            raise ValueError(f"premium_at_eval must be positive: {self.premium_at_eval}")
        if self.lot_size <= 0:
            raise ValueError(f"lot_size must be positive: {self.lot_size}")
        if self.expiry < self.date:
            raise ValueError(f"expiry ({self.expiry}) < date ({self.date})")


def select_low_premium_strike(
    contracts_df: pd.DataFrame,
    date: str,
    option_type: str,
    target_tier: Optional[float] = None,
    allowed_tiers: Sequence[float] = PREMIUM_LADDER_TIERS,
    eval_time: str = "09:19",
    max_tier_distance: Optional[float] = None,
) -> Optional[OptionContractCandidate]:
    """Select the best low-premium strike matching a target tier or nearest ladder tier.

    Parameters
    ----------
    contracts_df : pd.DataFrame
        Snapshot or bars at `eval_time`. Must contain:
        ['date', 'expiry', 'strike', 'option_type', 'close', 'lot_size']
        (or 'timestamp' from which time can be filtered).
    date : str
        Trading date 'YYYY-MM-DD'.
    option_type : str
        'CE' or 'PE'.
    target_tier : float, optional
        Specific desired premium ladder tier (e.g. 58.0). If None, selects the contract
        closest to ANY tier in `allowed_tiers`.
    allowed_tiers : Sequence[float]
        The set of ladder tiers [38, 48, 58, 68, 88, 128].
    eval_time : str
        Time string 'HH:MM' (default '09:19').
    max_tier_distance : float, optional
        Maximum absolute distance in premium points to accept a strike.

    Returns
    -------
    OptionContractCandidate or None
    """
    df = contracts_df.copy()
    if 'timestamp' in df.columns:
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['time'] = df['timestamp'].dt.strftime('%H:%M')
        df['date_str'] = df['timestamp'].dt.strftime('%Y-%m-%d')
        df = df[(df['date_str'] == date) & (df['time'] <= eval_time)]
        # Take the latest available bar up to eval_time for each contract
        df = df.sort_values('timestamp').groupby(['expiry', 'strike', 'option_type']).last().reset_index()
    else:
        if 'date' in df.columns:
            df = df[df['date'] == date]

    if 'option_type' in df.columns:
        df['option_type'] = df['option_type'].astype(str).str.upper()
        df = df[df['option_type'] == option_type.upper()]

    if df.empty:
        return None

    # Filter to nearest expiry (expiry >= date)
    df['expiry_str'] = pd.to_datetime(df['expiry']).dt.strftime('%Y-%m-%d')
    valid_expiries = df[df['expiry_str'] >= date]['expiry_str']
    if valid_expiries.empty:
        return None
    nearest_exp = valid_expiries.min()
    df = df[df['expiry_str'] == nearest_exp]

    if df.empty:
        return None

    candidates: List[OptionContractCandidate] = []
    tiers = [target_tier] if target_tier is not None else list(allowed_tiers)

    for _, row in df.iterrows():
        premium = float(row.get('close', row.get('open', 0.0)))
        if premium <= 0:
            continue
        strike = float(row['strike'])
        lot_size = int(row.get('lot_size', 50))

        # Find closest tier among allowed
        distances = [abs(premium - t) for t in tiers]
        best_idx = int(np.argmin(distances))
        best_dist = distances[best_idx]
        best_tier = tiers[best_idx]

        if max_tier_distance is not None and best_dist > max_tier_distance:
            continue

        cand = OptionContractCandidate(
            date=date,
            expiry=nearest_exp,
            strike=strike,
            option_type=option_type.upper(),
            premium_at_eval=premium,
            matched_tier=best_tier,
            distance_to_tier=best_dist,
            lot_size=lot_size,
        )
        candidates.append(cand)

    if not candidates:
        return None

    # Sort by minimum distance to tier, then tie-break by proximity to target_tier value
    candidates.sort(key=lambda c: (c.distance_to_tier, abs(c.premium_at_eval - c.matched_tier)))
    best = candidates[0]
    best.validate()
    return best


def select_strike_at_touch(
    contracts_df: pd.DataFrame,
    date: str,
    option_type: str,
    touch_timestamp: Union[str, pd.Timestamp],
    target_tier: Optional[float] = None,
    allowed_tiers: Sequence[float] = PREMIUM_LADDER_TIERS,
    max_tier_distance: Optional[float] = None,
) -> Optional[OptionContractCandidate]:
    """Select the best low-premium strike dynamically at point-of-reversal touch time.

    Enforces strict point-in-time filtering: only contract bars strictly on or before
    `touch_timestamp` are visible (zero lookahead).

    Parameters
    ----------
    contracts_df : pd.DataFrame
        Historical option candles. Must contain:
        ['timestamp', 'expiry', 'strike', 'option_type', 'close', 'lot_size']
        (or 'open' if close missing).
    date : str
        Trading date 'YYYY-MM-DD'.
    option_type : str
        'CE' or 'PE'.
    touch_timestamp : str or pd.Timestamp
        Exact timestamp of spot boundary touch.
    target_tier : float, optional
        Specific desired ladder tier (e.g. 58.0).
    allowed_tiers : Sequence[float]
        Ladder tiers [38, 48, 58, 68, 88, 128].
    max_tier_distance : float, optional
        Maximum allowable distance to ladder tier.

    Returns
    -------
    OptionContractCandidate or None
    """
    df = contracts_df.copy()
    if 'timestamp' not in df.columns:
        raise ValueError("contracts_df must contain 'timestamp' for point-of-reversal selection")

    if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
        df['timestamp'] = pd.to_datetime(df['timestamp'])

    touch_ts = pd.to_datetime(touch_timestamp)

    # Strictly filter <= touch_timestamp and date == date
    df['date_str'] = df['timestamp'].dt.strftime('%Y-%m-%d')
    df = df[(df['date_str'] == date) & (df['timestamp'] <= touch_ts)]

    if df.empty:
        return None

    if 'option_type' in df.columns:
        df['option_type'] = df['option_type'].astype(str).str.upper()
        df = df[df['option_type'] == option_type.upper()]

    if df.empty:
        return None

    # Filter to nearest expiry on or after date
    df['expiry_str'] = pd.to_datetime(df['expiry']).dt.strftime('%Y-%m-%d')
    valid_expiries = df[df['expiry_str'] >= date]['expiry_str']
    if valid_expiries.empty:
        return None
    nearest_exp = valid_expiries.min()
    df = df[df['expiry_str'] == nearest_exp]

    if df.empty:
        return None

    # Take the latest bar available on or before touch_timestamp per strike
    df = df.sort_values('timestamp').groupby(['expiry', 'strike', 'option_type']).last().reset_index()

    candidates: List[OptionContractCandidate] = []
    tiers = [target_tier] if target_tier is not None else list(allowed_tiers)

    for _, row in df.iterrows():
        premium = float(row.get('close', row.get('open', 0.0)))
        if premium <= 0:
            continue
        strike = float(row['strike'])
        lot_size = int(row.get('lot_size', 50))

        distances = [abs(premium - t) for t in tiers]
        best_idx = int(np.argmin(distances))
        best_dist = distances[best_idx]
        best_tier = tiers[best_idx]

        if max_tier_distance is not None and best_dist > max_tier_distance:
            continue

        cand = OptionContractCandidate(
            date=date,
            expiry=nearest_exp,
            strike=strike,
            option_type=option_type.upper(),
            premium_at_eval=premium,
            matched_tier=best_tier,
            distance_to_tier=best_dist,
            lot_size=lot_size,
        )
        candidates.append(cand)

    if not candidates:
        return None

    candidates.sort(key=lambda c: (c.distance_to_tier, abs(c.premium_at_eval - c.matched_tier)))
    best = candidates[0]
    best.validate()
    return best

