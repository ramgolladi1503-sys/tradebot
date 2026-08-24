from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from enum import Enum
from typing import Iterable, Sequence


class AuctionState(str, Enum):
    WARMUP = "WARMUP"
    BALANCE = "BALANCE"
    TRANSITION = "TRANSITION"
    UP_DISCOVERY = "UP_DISCOVERY"
    DOWN_DISCOVERY = "DOWN_DISCOVERY"


class SetupType(str, Enum):
    DISCOVERY_CONTINUATION = "DISCOVERY_CONTINUATION"
    FAILED_DISCOVERY_RETURN_TO_VALUE = "FAILED_DISCOVERY_RETURN_TO_VALUE"
    BALANCE_EXTREME_REVERSION = "BALANCE_EXTREME_REVERSION"


@dataclass(frozen=True)
class FormulaConfig:
    band_sigma: float = 1.0
    extreme_sigma: float = 1.8
    min_bars: int = 20
    atr_lookback: int = 14
    efficiency_lookback: int = 10
    slope_lookback: int = 10
    acceptance_window: int = 5
    acceptance_fraction: float = 0.80
    discovery_efficiency_min: float = 0.55
    discovery_slope_atr_min: float = 0.05
    balance_efficiency_max: float = 0.35
    balance_slope_atr_max: float = 0.08
    balance_inside_fraction_min: float = 0.60
    balance_crossings_min: int = 2
    pullback_tolerance_sigma: float = 0.35
    failed_reentry_penetration_sigma: float = 0.25
    rejection_penetration_sigma: float = 0.25
    failure_lookback: int = 6
    stop_buffer_atr: float = 0.10
    continuation_target_r: float = 2.0
    min_reward_risk: float = 1.50
    sigma_floor_atr: float = 0.05
    max_signals_per_session: int = 3
    cooldown_minutes: int = 15
    last_entry_time: time = time(14, 45)
    forced_exit_time: time = time(15, 15)
    max_hold_minutes: int = 30
    option_max_spread_pct: float = 0.02
    option_max_quote_staleness_seconds: int = 90
    option_min_volume: float = 1.0
    option_min_open_interest: float = 1.0
    primary_min_dte: int = 1
    primary_max_dte: int = 7
    allow_zero_dte: bool = False
    max_risk_fraction: float = 0.05
    lot_size: int = 65

    def validate(self) -> None:
        if not 0.5 <= self.band_sigma <= 2.0:
            raise ValueError("band_sigma out of bounded research range")
        if not self.extreme_sigma > self.band_sigma:
            raise ValueError("extreme_sigma must exceed band_sigma")
        if self.min_bars < max(self.atr_lookback, self.efficiency_lookback, self.slope_lookback, self.acceptance_window):
            raise ValueError("min_bars must cover every causal lookback")
        for name, value in (
            ("acceptance_fraction", self.acceptance_fraction),
            ("discovery_efficiency_min", self.discovery_efficiency_min),
            ("balance_efficiency_max", self.balance_efficiency_max),
            ("balance_inside_fraction_min", self.balance_inside_fraction_min),
            ("max_risk_fraction", self.max_risk_fraction),
        ):
            if not 0.0 < float(value) <= 1.0:
                raise ValueError(f"{name} must be in (0, 1]")
        if self.balance_efficiency_max >= self.discovery_efficiency_min:
            raise ValueError("balance/discovery efficiency thresholds must leave a transition region")
        if self.continuation_target_r < self.min_reward_risk:
            raise ValueError("continuation target must satisfy the minimum reward/risk")
        if self.primary_min_dte < 0 or self.primary_max_dte < self.primary_min_dte:
            raise ValueError("invalid DTE bounds")
        if self.max_signals_per_session <= 0 or self.cooldown_minutes < 0:
            raise ValueError("invalid signal frequency controls")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")


DEFAULT_CONFIG = FormulaConfig()


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    volume_provenance: str = "AUTHORITATIVE"

    def validate(self) -> None:
        values = (self.open, self.high, self.low, self.close, self.volume)
        if not all(math.isfinite(float(v)) for v in values):
            raise ValueError("bar contains non-finite value")
        if self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
            raise ValueError("bar prices must be positive")
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close, self.high):
            raise ValueError("bar OHLC geometry invalid")
        if self.volume <= 0:
            raise ValueError("true positive volume is required for VWAP authority")
        if self.volume_provenance.upper() not in {"AUTHORITATIVE", "EXCHANGE", "FUTURES_AUTHORITATIVE"}:
            raise ValueError("VWAP requires authoritative traded volume")


@dataclass(frozen=True)
class FeatureSnapshot:
    ts: datetime
    vwap: float
    sigma: float
    atr: float
    z_close: float
    z_high: float
    z_low: float
    efficiency: float
    slope_atr: float
    outside_up_fraction: float
    outside_down_fraction: float
    inside_fraction: float
    vwap_crossings: int
    state: AuctionState


@dataclass(frozen=True)
class SignalIntent:
    ts: datetime
    direction: str
    setup_type: SetupType
    state: AuctionState
    entry_reference: float
    structural_stop: float
    structural_target: float
    reward_risk: float
    reason: str
    entry_rule: str = "NEXT_AVAILABLE_OPTION_ASK_AFTER_SIGNAL"
    read_only: bool = True
    allowed_for_live_execution: bool = False

    @property
    def option_type(self) -> str:
        if self.direction == "BUY_CALL":
            return "CE"
        if self.direction == "BUY_PUT":
            return "PE"
        raise ValueError("buy-only direction required")


@dataclass(frozen=True)
class OptionQuote:
    ts: datetime
    symbol: str
    option_type: str
    strike: float
    expiry: date
    bid: float
    ask: float
    volume: float
    open_interest: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_pct(self) -> float:
        mid = self.mid
        return (self.ask - self.bid) / mid if mid > 0 else math.inf

    def validate(self) -> None:
        if self.option_type not in {"CE", "PE"}:
            raise ValueError("invalid option type")
        if not self.symbol:
            raise ValueError("option symbol required")
        if self.strike <= 0 or self.bid <= 0 or self.ask <= 0 or self.ask < self.bid:
            raise ValueError("invalid option quote")
        if self.volume < 0 or self.open_interest < 0:
            raise ValueError("invalid option liquidity values")


@dataclass(frozen=True)
class EntryFill:
    symbol: str
    ts: datetime
    price: float
    quote_spread_pct: float
    direction: str
    option_type: str
    read_only: bool = True
    allowed_for_live_execution: bool = False


@dataclass(frozen=True)
class TradeOutcome:
    symbol: str
    direction: str
    setup_type: SetupType
    signal_ts: datetime
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    option_points: float
    option_return_pct: float
    exit_reason: str
    read_only: bool = True
    allowed_for_live_execution: bool = False


def _typical_price(bar: Bar) -> float:
    return (bar.high + bar.low + bar.close) / 3.0


def _true_range(bar: Bar, previous_close: float | None) -> float:
    if previous_close is None:
        return bar.high - bar.low
    return max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close))


def _efficiency(closes: Sequence[float]) -> float:
    if len(closes) < 2:
        return 0.0
    path = sum(abs(b - a) for a, b in zip(closes, closes[1:]))
    return abs(closes[-1] - closes[0]) / path if path > 0 else 0.0


def _crossings(z_values: Sequence[float]) -> int:
    signs: list[int] = []
    for z in z_values:
        if z > 0:
            signs.append(1)
        elif z < 0:
            signs.append(-1)
        else:
            signs.append(0)
    total = 0
    prev = 0
    for sign in signs:
        if sign == 0:
            continue
        if prev and sign != prev:
            total += 1
        prev = sign
    return total


def _classify(
    *,
    z_close: float,
    efficiency: float,
    slope_atr: float,
    outside_up_fraction: float,
    outside_down_fraction: float,
    inside_fraction: float,
    crossings: int,
    cfg: FormulaConfig,
) -> AuctionState:
    if (
        z_close >= cfg.band_sigma
        and outside_up_fraction >= cfg.acceptance_fraction
        and efficiency >= cfg.discovery_efficiency_min
        and slope_atr >= cfg.discovery_slope_atr_min
    ):
        return AuctionState.UP_DISCOVERY
    if (
        z_close <= -cfg.band_sigma
        and outside_down_fraction >= cfg.acceptance_fraction
        and efficiency >= cfg.discovery_efficiency_min
        and slope_atr <= -cfg.discovery_slope_atr_min
    ):
        return AuctionState.DOWN_DISCOVERY
    if (
        efficiency <= cfg.balance_efficiency_max
        and abs(slope_atr) <= cfg.balance_slope_atr_max
        and inside_fraction >= cfg.balance_inside_fraction_min
        and crossings >= cfg.balance_crossings_min
    ):
        return AuctionState.BALANCE
    return AuctionState.TRANSITION


def compute_causal_features(bars: Sequence[Bar], cfg: FormulaConfig = DEFAULT_CONFIG) -> tuple[FeatureSnapshot, ...]:
    cfg.validate()
    if not bars:
        return ()
    previous_ts: datetime | None = None
    session_date: date | None = None
    for bar in bars:
        bar.validate()
        if previous_ts is not None and bar.ts <= previous_ts:
            raise ValueError("bars must be strictly increasing")
        if session_date is None:
            session_date = bar.ts.date()
        elif bar.ts.date() != session_date:
            raise ValueError("one compute_causal_features call must contain one session")
        previous_ts = bar.ts

    sum_w = 0.0
    sum_wx = 0.0
    sum_wx2 = 0.0
    vwaps: list[float] = []
    trs: list[float] = []
    closes: list[float] = []
    snapshots: list[FeatureSnapshot] = []

    previous_close: float | None = None
    for index, bar in enumerate(bars):
        tp = _typical_price(bar)
        w = float(bar.volume)
        sum_w += w
        sum_wx += w * tp
        sum_wx2 += w * tp * tp
        vwap = sum_wx / sum_w
        raw_variance = max(sum_wx2 / sum_w - vwap * vwap, 0.0)

        tr = _true_range(bar, previous_close)
        trs.append(tr)
        atr_window = trs[-cfg.atr_lookback :]
        atr = sum(atr_window) / len(atr_window)
        sigma_floor = max(atr * cfg.sigma_floor_atr, bar.close * 1e-8)
        sigma = max(math.sqrt(raw_variance), sigma_floor)

        closes.append(bar.close)
        vwaps.append(vwap)
        z_close = (bar.close - vwap) / sigma
        z_high = (bar.high - vwap) / sigma
        z_low = (bar.low - vwap) / sigma

        eff_start = max(0, len(closes) - cfg.efficiency_lookback - 1)
        efficiency = _efficiency(closes[eff_start:])
        slope_index = max(0, index - cfg.slope_lookback)
        slope_atr = (vwap - vwaps[slope_index]) / max(atr, 1e-12)

        recent_z = [snap.z_close for snap in snapshots[-(cfg.acceptance_window - 1) :]] + [z_close]
        outside_up_fraction = sum(z >= cfg.band_sigma for z in recent_z) / len(recent_z)
        outside_down_fraction = sum(z <= -cfg.band_sigma for z in recent_z) / len(recent_z)
        inside_fraction = sum(abs(z) < cfg.band_sigma for z in recent_z) / len(recent_z)

        balance_window = max(cfg.efficiency_lookback, cfg.acceptance_window)
        crossing_z = [snap.z_close for snap in snapshots[-(balance_window - 1) :]] + [z_close]
        crossings = _crossings(crossing_z)

        if index + 1 < cfg.min_bars:
            state = AuctionState.WARMUP
        else:
            state = _classify(
                z_close=z_close,
                efficiency=efficiency,
                slope_atr=slope_atr,
                outside_up_fraction=outside_up_fraction,
                outside_down_fraction=outside_down_fraction,
                inside_fraction=inside_fraction,
                crossings=crossings,
                cfg=cfg,
            )
        snapshots.append(
            FeatureSnapshot(
                ts=bar.ts,
                vwap=vwap,
                sigma=sigma,
                atr=atr,
                z_close=z_close,
                z_high=z_high,
                z_low=z_low,
                efficiency=efficiency,
                slope_atr=slope_atr,
                outside_up_fraction=outside_up_fraction,
                outside_down_fraction=outside_down_fraction,
                inside_fraction=inside_fraction,
                vwap_crossings=crossings,
                state=state,
            )
        )
        previous_close = bar.close
    return tuple(snapshots)


def _rr(direction: str, entry: float, stop: float, target: float) -> float:
    if direction == "BUY_CALL":
        risk = entry - stop
        reward = target - entry
    elif direction == "BUY_PUT":
        risk = stop - entry
        reward = entry - target
    else:
        return 0.0
    if risk <= 0 or reward <= 0:
        return 0.0
    return reward / risk


def _recent_discovery(features: Sequence[FeatureSnapshot], state: AuctionState, lookback: int) -> int | None:
    start = max(0, len(features) - lookback - 1)
    for idx in range(len(features) - 2, start - 1, -1):
        if features[idx].state == state:
            return idx
    return None


def detect_signal(
    bars: Sequence[Bar],
    features: Sequence[FeatureSnapshot],
    cfg: FormulaConfig = DEFAULT_CONFIG,
) -> SignalIntent | None:
    cfg.validate()
    if len(bars) != len(features) or len(bars) < 3:
        return None
    current_bar = bars[-1]
    current = features[-1]
    if current.state == AuctionState.WARMUP:
        return None
    if current.ts.time() > cfg.last_entry_time:
        return None

    # A failed auction invalidates the continuation thesis, so failure has priority.
    up_idx = _recent_discovery(features, AuctionState.UP_DISCOVERY, cfg.failure_lookback)
    if up_idx is not None and current.z_close <= cfg.band_sigma - cfg.failed_reentry_penetration_sigma:
        recent_high = max(bar.high for bar in bars[up_idx:])
        stop = recent_high + cfg.stop_buffer_atr * current.atr
        target = current.vwap
        rr = _rr("BUY_PUT", current_bar.close, stop, target)
        if rr >= cfg.min_reward_risk:
            return SignalIntent(
                ts=current.ts,
                direction="BUY_PUT",
                setup_type=SetupType.FAILED_DISCOVERY_RETURN_TO_VALUE,
                state=current.state,
                entry_reference=current_bar.close,
                structural_stop=stop,
                structural_target=target,
                reward_risk=rr,
                reason="accepted upside auction failed and re-entered value",
            )

    down_idx = _recent_discovery(features, AuctionState.DOWN_DISCOVERY, cfg.failure_lookback)
    if down_idx is not None and current.z_close >= -cfg.band_sigma + cfg.failed_reentry_penetration_sigma:
        recent_low = min(bar.low for bar in bars[down_idx:])
        stop = recent_low - cfg.stop_buffer_atr * current.atr
        target = current.vwap
        rr = _rr("BUY_CALL", current_bar.close, stop, target)
        if rr >= cfg.min_reward_risk:
            return SignalIntent(
                ts=current.ts,
                direction="BUY_CALL",
                setup_type=SetupType.FAILED_DISCOVERY_RETURN_TO_VALUE,
                state=current.state,
                entry_reference=current_bar.close,
                structural_stop=stop,
                structural_target=target,
                reward_risk=rr,
                reason="accepted downside auction failed and re-entered value",
            )

    # Discovery pullback -> hold -> continuation.
    a, b, c = features[-3], features[-2], features[-1]
    bar_b, bar_c = bars[-2], bars[-1]
    if a.state == AuctionState.UP_DISCOVERY:
        touched = b.z_low <= cfg.band_sigma + cfg.pullback_tolerance_sigma
        held = b.z_close >= cfg.band_sigma - cfg.pullback_tolerance_sigma
        reconfirmed = c.z_close >= cfg.band_sigma and bar_c.close > bar_b.close
        if touched and held and reconfirmed:
            stop = bar_b.low - cfg.stop_buffer_atr * c.atr
            risk = bar_c.close - stop
            target = bar_c.close + cfg.continuation_target_r * risk
            rr = _rr("BUY_CALL", bar_c.close, stop, target)
            if rr >= cfg.min_reward_risk:
                return SignalIntent(
                    ts=c.ts,
                    direction="BUY_CALL",
                    setup_type=SetupType.DISCOVERY_CONTINUATION,
                    state=c.state,
                    entry_reference=bar_c.close,
                    structural_stop=stop,
                    structural_target=target,
                    reward_risk=rr,
                    reason="upside price discovery accepted a band retest and resumed",
                )
    if a.state == AuctionState.DOWN_DISCOVERY:
        touched = b.z_high >= -cfg.band_sigma - cfg.pullback_tolerance_sigma
        held = b.z_close <= -cfg.band_sigma + cfg.pullback_tolerance_sigma
        reconfirmed = c.z_close <= -cfg.band_sigma and bar_c.close < bar_b.close
        if touched and held and reconfirmed:
            stop = bar_b.high + cfg.stop_buffer_atr * c.atr
            risk = stop - bar_c.close
            target = bar_c.close - cfg.continuation_target_r * risk
            rr = _rr("BUY_PUT", bar_c.close, stop, target)
            if rr >= cfg.min_reward_risk:
                return SignalIntent(
                    ts=c.ts,
                    direction="BUY_PUT",
                    setup_type=SetupType.DISCOVERY_CONTINUATION,
                    state=c.state,
                    entry_reference=bar_c.close,
                    structural_stop=stop,
                    structural_target=target,
                    reward_risk=rr,
                    reason="downside price discovery accepted a band retest and resumed",
                )

    # Balance extreme rejection -> mean reversion to frozen signal-time VWAP.
    recent_balance = any(f.state == AuctionState.BALANCE for f in features[-3:-1])
    if recent_balance:
        if current.z_high >= cfg.extreme_sigma and current.z_close <= cfg.extreme_sigma - cfg.rejection_penetration_sigma:
            stop = current_bar.high + cfg.stop_buffer_atr * current.atr
            target = current.vwap
            rr = _rr("BUY_PUT", current_bar.close, stop, target)
            if rr >= cfg.min_reward_risk:
                return SignalIntent(
                    ts=current.ts,
                    direction="BUY_PUT",
                    setup_type=SetupType.BALANCE_EXTREME_REVERSION,
                    state=current.state,
                    entry_reference=current_bar.close,
                    structural_stop=stop,
                    structural_target=target,
                    reward_risk=rr,
                    reason="balanced auction rejected an upper statistical extreme",
                )
        if current.z_low <= -cfg.extreme_sigma and current.z_close >= -cfg.extreme_sigma + cfg.rejection_penetration_sigma:
            stop = current_bar.low - cfg.stop_buffer_atr * current.atr
            target = current.vwap
            rr = _rr("BUY_CALL", current_bar.close, stop, target)
            if rr >= cfg.min_reward_risk:
                return SignalIntent(
                    ts=current.ts,
                    direction="BUY_CALL",
                    setup_type=SetupType.BALANCE_EXTREME_REVERSION,
                    state=current.state,
                    entry_reference=current_bar.close,
                    structural_stop=stop,
                    structural_target=target,
                    reward_risk=rr,
                    reason="balanced auction rejected a lower statistical extreme",
                )
    return None


def generate_signals(
    bars: Sequence[Bar], cfg: FormulaConfig = DEFAULT_CONFIG
) -> tuple[SignalIntent, ...]:
    features = compute_causal_features(bars, cfg)
    signals: list[SignalIntent] = []
    last_signal_ts: datetime | None = None
    for end in range(cfg.min_bars, len(bars) + 1):
        signal = detect_signal(bars[:end], features[:end], cfg)
        if signal is None:
            continue
        if last_signal_ts is not None:
            elapsed = (signal.ts - last_signal_ts).total_seconds() / 60.0
            if elapsed < cfg.cooldown_minutes:
                continue
        if len(signals) >= cfg.max_signals_per_session:
            break
        signals.append(signal)
        last_signal_ts = signal.ts
    return tuple(signals)


def select_option_contract(
    signal: SignalIntent,
    quotes: Iterable[OptionQuote],
    underlying_price: float,
    cfg: FormulaConfig = DEFAULT_CONFIG,
) -> OptionQuote | None:
    cfg.validate()
    candidates: list[OptionQuote] = []
    required_type = signal.option_type
    for quote in quotes:
        quote.validate()
        if quote.option_type != required_type or quote.ts > signal.ts:
            continue
        staleness = (signal.ts - quote.ts).total_seconds()
        if staleness < 0 or staleness > cfg.option_max_quote_staleness_seconds:
            continue
        dte = (quote.expiry - signal.ts.date()).days
        if dte == 0 and not cfg.allow_zero_dte:
            continue
        if dte < cfg.primary_min_dte or dte > cfg.primary_max_dte:
            continue
        if quote.spread_pct > cfg.option_max_spread_pct:
            continue
        if quote.volume < cfg.option_min_volume or quote.open_interest < cfg.option_min_open_interest:
            continue
        candidates.append(quote)
    if not candidates:
        return None
    candidates.sort(
        key=lambda q: (
            (q.expiry - signal.ts.date()).days,
            abs(q.strike - underlying_price),
            q.spread_pct,
            -q.open_interest,
            q.symbol,
        )
    )
    return candidates[0]


def next_bar_long_entry(
    signal: SignalIntent,
    selected: OptionQuote,
    quotes: Sequence[OptionQuote],
    cfg: FormulaConfig = DEFAULT_CONFIG,
) -> EntryFill | None:
    cfg.validate()
    future = [q for q in quotes if q.symbol == selected.symbol and q.ts > signal.ts]
    future.sort(key=lambda q: q.ts)
    for quote in future:
        quote.validate()
        delay = (quote.ts - signal.ts).total_seconds()
        if delay > cfg.option_max_quote_staleness_seconds:
            return None
        if quote.spread_pct > cfg.option_max_spread_pct:
            continue
        return EntryFill(
            symbol=quote.symbol,
            ts=quote.ts,
            price=quote.ask,
            quote_spread_pct=quote.spread_pct,
            direction=signal.direction,
            option_type=signal.option_type,
        )
    return None


def max_lots_by_total_premium_risk(
    *,
    account_equity: float,
    option_ask: float,
    cfg: FormulaConfig = DEFAULT_CONFIG,
) -> int:
    cfg.validate()
    if account_equity <= 0 or option_ask <= 0:
        return 0
    maximum_rupee_loss = account_equity * cfg.max_risk_fraction
    premium_per_lot = option_ask * cfg.lot_size
    return max(0, int(maximum_rupee_loss // premium_per_lot))


def robustness_lattice(cfg: FormulaConfig = DEFAULT_CONFIG) -> tuple[tuple[str, FormulaConfig], ...]:
    cfg.validate()
    variants = (
        ("base", cfg),
        ("band_lo", replace(cfg, band_sigma=max(0.5, cfg.band_sigma - 0.1))),
        ("band_hi", replace(cfg, band_sigma=cfg.band_sigma + 0.1)),
        ("accept_lo", replace(cfg, acceptance_fraction=max(0.5, cfg.acceptance_fraction - 0.2))),
        ("accept_hi", replace(cfg, acceptance_fraction=min(1.0, cfg.acceptance_fraction + 0.2))),
        ("eff_lo", replace(cfg, discovery_efficiency_min=max(cfg.balance_efficiency_max + 0.05, cfg.discovery_efficiency_min - 0.05))),
        ("eff_hi", replace(cfg, discovery_efficiency_min=min(0.95, cfg.discovery_efficiency_min + 0.05))),
        ("slope_lo", replace(cfg, discovery_slope_atr_min=max(0.01, cfg.discovery_slope_atr_min - 0.02))),
        ("slope_hi", replace(cfg, discovery_slope_atr_min=cfg.discovery_slope_atr_min + 0.03)),
    )
    for _, variant in variants:
        variant.validate()
    fingerprints = {
        (
            v.band_sigma,
            v.acceptance_fraction,
            v.discovery_efficiency_min,
            v.discovery_slope_atr_min,
        )
        for _, v in variants
    }
    if len(fingerprints) != len(variants):
        raise AssertionError("robustness lattice contains duplicate formulas")
    return variants


FORMULA = {
    "vwap": "sum(tp_i * volume_i) / sum(volume_i), tp=(high+low+close)/3, session anchored",
    "sigma": "sqrt(sum(volume_i*(tp_i-vwap_t)^2)/sum(volume_i)) with causal ATR floor",
    "z": "(price_t-vwap_t)/sigma_t",
    "efficiency": "abs(close_t-close_t-L)/sum(abs(delta_close))",
    "slope_atr": "(vwap_t-vwap_t-L)/ATR_t",
    "discovery": "|z|>=band AND outside_fraction>=acceptance AND efficiency>=threshold AND signed_vwap_slope>=threshold",
    "balance": "efficiency<=balance_max AND |vwap_slope/ATR|<=balance_max AND inside_fraction>=threshold AND crossings>=minimum",
    "execution": "signal at completed bar close; long option entry only at next available ask; exit at bid",
}
