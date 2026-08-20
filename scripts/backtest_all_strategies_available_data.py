from __future__ import annotations

import argparse
import json
import math
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import numpy as np
import pandas as pd

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


TRADEABLE_INSTRUMENTS = ("NIFTY", "BANKNIFTY", "SENSEX")
REFERENCE_INSTRUMENTS = ("INDIAVIX",)
REQUIRED_COLUMNS = ("date", "open", "high", "low", "close", "volume", "instrument")
EXIT_HORIZONS = (5, 10, 15, 30)
COST_BPS = (0.0, 2.0, 5.0, 10.0)
ENTRY_RULE = "current_candle_close"
FINAL_VERDICT = "DIRECTIONAL_PROXY_ONLY, NOT_EXECUTABLE_OPTION_BACKTEST"
ENTRY_TIMING_NOTE = (
    "Signals are evaluated with information available through the current 1-minute candle close. "
    "Proxy entry uses that same close, so this is an optimistic directional research proxy, "
    "not an executable fill model."
)


def _forbidden_broker_call_sentinel(*_args: Any, **_kwargs: Any) -> None:
    """Test hook. The offline harness must never call this."""


@dataclass(frozen=True)
class DatasetInspection:
    columns: tuple[str, ...]
    instruments: tuple[str, ...]
    timestamp_start: str
    timestamp_end: str
    rows_total: int
    rows_by_instrument: dict[str, int]
    volume_quality: str
    missing_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategySpec:
    strategy: str
    module: str
    callable: str
    required_inputs: tuple[str, ...]
    option_specific: bool
    volume_dependent: bool
    vwap_dependent: bool
    runner: Callable[[Mapping[str, Any]], Any] | None = None
    uses_iv: bool = False
    uses_oi: bool = False
    uses_greeks: bool = False
    uses_spread: bool = False
    uses_depth: bool = False
    uses_option_ltp: bool = False
    uses_regime: bool = False
    uses_vix: bool = False
    signal_only: bool = False
    reason: str = ""


@dataclass(frozen=True)
class NormalizedSignal:
    strategy: str
    instrument: str
    timestamp: str
    direction: str
    side: int
    score: float | None
    reason: str
    executable: bool = False
    signal_only: bool = False
    advisory: bool = False
    fallback: bool = False


def load_dataset(path: Path | str) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    return frame.copy()


def inspect_dataset(frame: pd.DataFrame) -> DatasetInspection:
    missing = tuple(col for col in REQUIRED_COLUMNS if col not in frame.columns)
    data = frame.copy()
    if "date" in data.columns:
        data["date"] = pd.to_datetime(data["date"])
    instruments = tuple(sorted(str(item) for item in data.get("instrument", pd.Series(dtype=str)).dropna().astype(str).unique()))
    if "date" in data.columns and not data.empty:
        timestamp_start = data["date"].min().isoformat()
        timestamp_end = data["date"].max().isoformat()
    else:
        timestamp_start = ""
        timestamp_end = ""
    rows_by = {
        str(k): int(v)
        for k, v in data.groupby("instrument", observed=True).size().to_dict().items()
    } if "instrument" in data.columns else {}
    if "volume" not in data.columns:
        volume_quality = "MISSING_VOLUME"
    else:
        volume = pd.to_numeric(data["volume"], errors="coerce")
        if volume.isna().all():
            volume_quality = "MISSING_VOLUME"
        elif float(volume.fillna(0).sum()) == 0.0:
            volume_quality = "ZERO_VOLUME"
        elif volume.isna().any():
            volume_quality = "PARTIAL_VOLUME"
        else:
            volume_quality = "OK"
    return DatasetInspection(
        columns=tuple(str(col) for col in data.columns),
        instruments=instruments,
        timestamp_start=timestamp_start,
        timestamp_end=timestamp_end,
        rows_total=int(len(data)),
        rows_by_instrument=rows_by,
        volume_quality=volume_quality,
        missing_columns=missing,
    )


def _direction_to_side(direction: Any) -> int:
    text = str(direction or "").strip().upper()
    if text in {"BUY_CALL", "CALL", "CE", "LONG", "BUY", "UP", "BULLISH"}:
        return 1
    if text in {"BUY_PUT", "PUT", "PE", "SHORT", "SELL", "DOWN", "BEARISH"}:
        return -1
    return 0


def normalize_signal(
    *,
    strategy: str,
    instrument: str,
    timestamp: Any,
    direction: Any,
    score: Any = None,
    reason: Any = "",
    advisory: bool = False,
    fallback: bool = False,
) -> NormalizedSignal | None:
    side = _direction_to_side(direction)
    if side == 0:
        return None
    score_out: float | None
    try:
        score_out = None if score is None or score == "" else float(score)
        if score_out is not None and not math.isfinite(score_out):
            score_out = None
    except Exception:
        score_out = None
    signal_only = bool(advisory or fallback)
    return NormalizedSignal(
        strategy=str(strategy),
        instrument=str(instrument),
        timestamp=pd.Timestamp(timestamp).isoformat(),
        direction=str(direction),
        side=side,
        score=score_out,
        reason=str(reason or ""),
        executable=False,
        signal_only=signal_only,
        advisory=bool(advisory),
        fallback=bool(fallback),
    )


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    if not math.isfinite(out):
        return default
    return out


def _prepare_frames(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    data = frame.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["instrument"] = data["instrument"].astype(str)
    out: dict[str, pd.DataFrame] = {}
    for instrument, group in data.sort_values(["instrument", "date"]).groupby("instrument"):
        g = group.reset_index(drop=True).copy()
        typical = (g["high"] + g["low"] + g["close"]) / 3.0
        volume = pd.to_numeric(g["volume"], errors="coerce").replace(0, np.nan)
        if volume.notna().any():
            g["vwap"] = (typical * volume).cumsum() / volume.cumsum()
            g["vwap"] = g["vwap"].ffill().fillna(typical.expanding().mean())
            g["vwap_quality"] = "VOLUME_WEIGHTED"
        else:
            g["vwap"] = typical.expanding().mean()
            g["vwap_quality"] = "INVALID_VOLUME_PROXY"
        prev_close = g["close"].shift(1)
        true_range = pd.concat(
            [
                (g["high"] - g["low"]).abs(),
                (g["high"] - prev_close).abs(),
                (g["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        g["atr"] = true_range.rolling(14, min_periods=3).mean().fillna(0.0)
        g["atr_short"] = true_range.rolling(5, min_periods=3).mean().fillna(0.0)
        g["atr_long"] = true_range.rolling(30, min_periods=5).mean().fillna(0.0)
        g["ltp_change"] = g["close"].diff().fillna(0.0)
        g["ltp_change_5m"] = g["close"].diff(5).fillna(0.0)
        g["ltp_change_10m"] = g["close"].diff(10).fillna(0.0)
        g["ltp_change_window"] = g["close"].diff(5).fillna(0.0)
        g["vwap_slope"] = g["vwap"].diff(5).fillna(0.0)
        atr_mean = g["atr"].rolling(60, min_periods=10).mean()
        atr_std = g["atr"].rolling(60, min_periods=10).std().replace(0, np.nan)
        g["vol_z"] = ((g["atr"] - atr_mean) / atr_std).fillna(0.0)
        delta = g["close"].diff().fillna(0.0)
        up = delta.clip(lower=0).rolling(14, min_periods=3).mean()
        down = (-delta.clip(upper=0)).rolling(14, min_periods=3).mean().replace(0, np.nan)
        rsi = 100 - (100 / (1 + (up / down)))
        g["rsi_mom"] = ((rsi.fillna(50) - 50) / 50).clip(-1, 1)
        g["day_high_so_far"] = g["high"].cummax()
        g["day_low_so_far"] = g["low"].cummin()
        g["orb_high"] = np.nan
        g["orb_low"] = np.nan
        if len(g) >= 15:
            first_range_high = float(g.loc[:14, "high"].max())
            first_range_low = float(g.loc[:14, "low"].min())
            g.loc[15:, "orb_high"] = first_range_high
            g.loc[15:, "orb_low"] = first_range_low
        g["minutes_since_open"] = np.arange(len(g))
        g["minutes_to_close"] = len(g) - 1 - g["minutes_since_open"]
        g["hour"] = g["date"].dt.hour
        g["minute"] = g["date"].dt.minute
        g["bias"] = np.where(g["close"] >= g["vwap"], "bullish", "bearish")
        out[str(instrument)] = g
    return out


def _market_row(frames: Mapping[str, pd.DataFrame], instrument: str, idx: int) -> dict[str, Any]:
    row = frames[instrument].loc[idx]
    range_width = (_safe_float(row.day_high_so_far) - _safe_float(row.day_low_so_far)) / max(_safe_float(row.close), 1.0)
    vix = None
    if "INDIAVIX" in frames and idx < len(frames["INDIAVIX"]):
        vix = float(frames["INDIAVIX"].loc[idx, "close"])
    return {
        "symbol": instrument,
        "instrument_id": instrument,
        "date": row.date,
        "ltp": float(row.close),
        "open": float(row.open),
        "high": float(row.high),
        "low": float(row.low),
        "close": float(row.close),
        "volume": float(row.volume),
        "vwap": float(row.vwap),
        "vwap_quality": row.vwap_quality,
        "vwap_slope": float(row.vwap_slope),
        "atr": float(row.atr),
        "atr_short": float(row.atr_short),
        "atr_long": float(row.atr_long),
        "orb_high": float(row.orb_high),
        "orb_low": float(row.orb_low),
        "vol_z": float(row.vol_z),
        "rsi_mom": float(row.rsi_mom),
        "ltp_change": float(row.ltp_change),
        "ltp_change_5m": float(row.ltp_change_5m),
        "ltp_change_10m": float(row.ltp_change_10m),
        "ltp_change_window": float(row.ltp_change_window),
        "bias": str(row.bias),
        "regime": "TREND" if abs(float(row.close - row.vwap)) / max(float(row.vwap), 1.0) > 0.002 else "RANGE",
        "range_width_pct": float(range_width),
        "hour": int(row.hour),
        "minute": int(row.minute),
        "minutes_since_open": int(row.minutes_since_open),
        "minutes_to_close": int(row.minutes_to_close),
        "quote_age_sec": 0.0,
        "spread_pct": None,
        "bid_qty": None,
        "ask_qty": None,
        "call_oi_delta": None,
        "put_oi_delta": None,
        "iv_change": None,
        "vix": vix,
    }


def _strategy_context(market: Mapping[str, Any]) -> Any:
    from core.movement_contract import StrategyContext

    return StrategyContext(
        symbol=str(market["symbol"]),
        ts_epoch=float(pd.Timestamp(market["date"]).timestamp()),
        spot_ltp=market["close"],
        open_price=market["open"],
        vwap=market["vwap"],
        vwap_slope=market["vwap_slope"],
        day_high=market["high"],
        day_low=market["low"],
        orb_high=market["orb_high"],
        orb_low=market["orb_low"],
        nearest_support=market["low"],
        nearest_resistance=market["high"],
        atr=market["atr"],
        atr_short=market["atr_short"],
        atr_long=market["atr_long"],
        range_width_pct=market["range_width_pct"],
        volume_z=market["vol_z"],
        regime_hint=market["regime"],
        quote_source="index_1m_historical_chart",
        fallback_used=False,
        time_of_day=pd.Timestamp(market["date"]).strftime("%H:%M"),
        minutes_since_open=market["minutes_since_open"],
        minutes_to_close=market["minutes_to_close"],
        expiry_context=False,
        metadata={"source": "offline_available_data_backtest", "has_option_truth": False},
    )


def discover_strategy_specs() -> list[StrategySpec]:
    from core.breakout_candidate_generator import build_breakout_candidate_intents
    from core.mean_reversion_candidate_generator import build_mean_reversion_candidate_intents
    from core.pairs_candidate_generator import build_pairs_candidate_intents
    from core.vwap_candidate_generator import build_vwap_candidate_intents
    from core.zero_hero_candidate_generator import build_zero_hero_candidate_intents
    from strategies import banknifty_intraday, nifty_intraday, sensex_intraday
    from strategies.ensemble import ensemble_signal
    from strategies.pairs_arbitrage import generate_signal as pairs_signal
    from strategies.pro_layer.pro_strategy_engine import ProStrategyEngine
    from strategies.volatility_trend import volatility_scaled_trend_strategy
    from strategies.vwap_orb import vwap_orb_strategy
    from strategies.zero_hero import zero_hero_strategy

    specs: list[StrategySpec] = [
        StrategySpec("nifty_intraday.generate_signal", "strategies.nifty_intraday", "generate_signal", ("close", "vwap", "bias", "regime"), False, False, True, lambda m: nifty_intraday.generate_signal(m["ltp"], m["vwap"], m["bias"], regime=m["regime"]), uses_regime=True),
        StrategySpec("banknifty_intraday.generate_signal", "strategies.banknifty_intraday", "generate_signal", ("close", "vwap", "bias", "regime"), False, False, True, lambda m: banknifty_intraday.generate_signal(m["ltp"], m["vwap"], m["bias"], regime=m["regime"]), uses_regime=True),
        StrategySpec("sensex_intraday.generate_signal", "strategies.sensex_intraday", "generate_signal", ("close", "vwap", "bias", "regime"), False, False, True, lambda m: sensex_intraday.generate_signal(m["ltp"], m["vwap"], m["bias"], regime=m["regime"]), uses_regime=True),
        StrategySpec("vwap_orb_strategy", "strategies.vwap_orb", "vwap_orb_strategy", ("close", "vwap", "volume/CVD", "option_contract_proxy"), True, True, True, lambda m: vwap_orb_strategy(m["symbol"], m["ltp"], m["vwap"], market_data=m), uses_option_ltp=True, uses_spread=True, reason="emits option trade shape but available data has no option truth"),
        StrategySpec("volatility_scaled_trend_strategy", "strategies.volatility_trend", "volatility_scaled_trend_strategy", ("close", "vwap", "atr", "option_contract_proxy"), True, False, True, lambda m: volatility_scaled_trend_strategy(m["symbol"], m["ltp"], m["vwap"], m["atr"]), uses_option_ltp=True, reason="option premium is derived from index price"),
        StrategySpec("zero_hero_strategy", "strategies.zero_hero", "zero_hero_strategy", ("close", "bias", "expiry", "option_premium"), True, False, False, lambda m: zero_hero_strategy(m["symbol"], m["ltp"], {"bias": m["bias"]}, current_date=pd.Timestamp("2026-06-29").date(), regime=m["regime"]), uses_option_ltp=True, reason="manual option-premium advisory without option LTP"),
        StrategySpec("ensemble.ensemble_signal", "strategies.ensemble", "ensemble_signal", ("close", "vwap", "atr", "orb", "regime"), False, True, True, lambda m: ensemble_signal(dict(m)), uses_regime=True),
        StrategySpec("pairs_arbitrage.generate_signal", "strategies.pairs_arbitrage", "generate_signal", ("NIFTY close", "BANKNIFTY close", "history"), False, False, False, None, signal_only=False),
        StrategySpec("pro.ProStrategyEngine.run", "strategies.pro_layer.pro_strategy_engine", "ProStrategyEngine.run", ("pro_child_signals", "family_truth", "source_sha256", "contract_valid", "freshness_valid"), False, False, False, lambda m: ProStrategyEngine().run(dict(m)), signal_only=True, reason="pro meta-engine requires externally produced structurally valid child signals"),
        StrategySpec("core.breakout_candidate_generator.build_breakout_candidate_intents", "core.breakout_candidate_generator", "build_breakout_candidate_intents", ("close", "orb_high", "orb_low", "volume_z", "regime"), False, True, False, lambda m: build_breakout_candidate_intents(dict(m), instrument=m["symbol"]), uses_regime=True),
        StrategySpec("core.vwap_candidate_generator.build_vwap_candidate_intents", "core.vwap_candidate_generator", "build_vwap_candidate_intents", ("close", "vwap", "vwap_slope", "regime"), False, False, True, lambda m: build_vwap_candidate_intents(dict(m), instrument=m["symbol"]), uses_regime=True),
        StrategySpec("core.mean_reversion_candidate_generator.build_mean_reversion_candidate_intents", "core.mean_reversion_candidate_generator", "build_mean_reversion_candidate_intents", ("close", "vwap", "rsi_mom", "regime"), False, False, True, lambda m: build_mean_reversion_candidate_intents(dict(m), instrument=m["symbol"]), uses_regime=True),
        StrategySpec("core.zero_hero_candidate_generator.build_zero_hero_candidate_intents", "core.zero_hero_candidate_generator", "build_zero_hero_candidate_intents", ("option_ltp", "expiry_context", "underlying_momentum", "volume_z"), True, True, False, lambda m: build_zero_hero_candidate_intents(dict(m), instrument=m["symbol"]), uses_option_ltp=True, reason="requires option premium truth and expiry option context"),
        StrategySpec("core.pairs_candidate_generator.build_pairs_candidate_intents", "core.pairs_candidate_generator", "build_pairs_candidate_intents", ("cross_asset_prices", "spread_z", "cointegration"), False, False, False, lambda m: build_pairs_candidate_intents({"prices": {"NIFTY": m["ltp"], "BANKNIFTY": m["ltp"]}, "features": {}}), signal_only=True, reason="multi-leg statistical-arbitrage intent is signal-only in this single-underlying proxy harness"),
        StrategySpec("core.candidate_generator.generate_candidates", "core.candidate_generator", "generate_candidates", ("option_chain", "strikes", "expiry", "underlying_spot"), True, False, False, None, uses_option_ltp=True, uses_oi=True, uses_iv=True, uses_greeks=True, reason="runtime candidate generator requires option chain/contracts absent from parquet"),
    ]

    movement_specs = [
        ("movement.opening_drive_v1", "strategies.movement.opening_drive", "generate_opening_drive_candidates"),
        ("movement.opening_range_retest_v1", "strategies.movement.opening_range_breakout", "generate_opening_range_retest_candidates"),
        ("movement.compression_breakout_v1", "strategies.movement.compression_breakout", "generate_compression_breakout_candidates"),
        ("movement.trend_pullback_v1", "strategies.movement.trend_pullback", "generate_trend_pullback_candidates"),
        ("movement.vwap_reclaim_rejection_v1", "strategies.movement.vwap_reclaim", "generate_vwap_reclaim_rejection_candidates"),
        ("movement.failed_breakout_trap_v1", "strategies.movement.failed_breakout_trap", "generate_failed_breakout_trap_candidates"),
        ("movement.exhaustion_reversal_v1", "strategies.movement.exhaustion_reversal", "generate_exhaustion_reversal_candidates"),
        ("movement.mean_reversion_extension_v1", "strategies.movement.mean_reversion_extension", "generate_mean_reversion_extension_candidates"),
        ("movement.event_volatility_expansion_v1", "strategies.movement.event_volatility_expansion", "generate_event_volatility_expansion_candidates"),
        ("movement.option_pressure_confirmation_v1", "strategies.movement.option_pressure", "generate_option_pressure_candidates"),
        ("movement.late_day_momentum_v1", "strategies.movement.late_day_momentum", "generate_late_day_momentum_candidates"),
        ("movement.no_trade_engine_v1", "strategies.movement.no_trade_chop", "generate_no_trade_candidates"),
    ]
    for strategy, module, callable_name in movement_specs:
        specs.append(
            StrategySpec(
                strategy=strategy,
                module=module,
                callable=callable_name,
                required_inputs=("StrategyContext", "MovementRegimeResult", "option confirmation optional"),
                option_specific=strategy in {"movement.option_pressure_confirmation_v1"},
                volume_dependent=True,
                vwap_dependent=True,
                runner=None,
                uses_spread=strategy in {"movement.option_pressure_confirmation_v1"},
                uses_depth=strategy in {"movement.option_pressure_confirmation_v1"},
                uses_option_ltp=strategy in {"movement.option_pressure_confirmation_v1"},
                uses_regime=True,
                signal_only=strategy == "movement.no_trade_engine_v1",
            )
        )
    return specs


def _available_inputs(inspection: DatasetInspection) -> set[str]:
    available = set(inspection.columns)
    available.update({"close", "vwap_proxy", "atr_proxy", "regime_proxy", "rsi_proxy", "orb_proxy", "time"})
    if "INDIAVIX" in inspection.instruments:
        available.add("vix")
    return available


def _missing_inputs(spec: StrategySpec, inspection: DatasetInspection) -> tuple[str, ...]:
    missing: list[str] = []
    if spec.option_specific or spec.uses_option_ltp:
        missing.append("option_ltp")
    if spec.uses_spread:
        missing.append("bid_ask_spread")
    if spec.uses_depth:
        missing.append("market_depth")
    if spec.uses_oi:
        missing.append("open_interest")
    if spec.uses_iv:
        missing.append("implied_volatility")
    if spec.uses_greeks:
        missing.append("greeks")
    if spec.volume_dependent and inspection.volume_quality != "OK":
        missing.append(inspection.volume_quality.lower())
    return tuple(dict.fromkeys(missing))


def _classify_spec(spec: StrategySpec, inspection: DatasetInspection) -> tuple[str, str, str]:
    missing = _missing_inputs(spec, inspection)
    if spec.option_specific or any(item in missing for item in ("option_ltp", "bid_ask_spread", "market_depth", "open_interest", "implied_volatility", "greeks")):
        if spec.signal_only:
            return "SIGNAL_ONLY", "SIGNAL_ONLY", "option-specific no-trade/signal layer without executable option data"
        return "UNSUPPORTED_EXECUTABLE", "SKIP_PNL", spec.reason or "requires option executable data not present in parquet"
    if spec.signal_only:
        return "SIGNAL_ONLY", "SIGNAL_ONLY", "strategy emits non-trade/signal-only output"
    if spec.vwap_dependent and inspection.volume_quality in {"ZERO_VOLUME", "MISSING_VOLUME"}:
        return "PARTIAL_PROXY", "INVALID_VOLUME_PROXY", "VWAP uses expanding typical-price proxy because volume is zero/missing"
    if spec.volume_dependent and inspection.volume_quality != "OK":
        return "PARTIAL_PROXY", "INVALID_VOLUME_PROXY", "volume-dependent input is unavailable or invalid"
    return "SUPPORTED_PROXY", "DIRECTIONAL_PROXY", "required directional inputs are available as index OHLC proxies"


def build_capability_matrix(inspection: DatasetInspection, specs: Iterable[StrategySpec] | None = None) -> pd.DataFrame:
    specs = list(specs or discover_strategy_specs())
    available = sorted(_available_inputs(inspection))
    rows = []
    for spec in specs:
        missing = _missing_inputs(spec, inspection)
        bucket, test_mode, reason = _classify_spec(spec, inspection)
        rows.append(
            {
                "strategy": spec.strategy,
                "module": spec.module,
                "callable": spec.callable,
                "required_inputs": "|".join(spec.required_inputs),
                "available_inputs": "|".join(available),
                "missing_inputs": "|".join(missing),
                "capability_bucket": bucket,
                "reason": reason,
                "test_mode": test_mode,
            }
        )
    return pd.DataFrame(rows)


def _extract_signals(spec: StrategySpec, market: Mapping[str, Any], result: Any) -> list[NormalizedSignal]:
    if result is None:
        return []
    if hasattr(result, "generated_intents"):
        items = list(getattr(result, "generated_intents"))
    elif isinstance(result, Mapping) and "generated_intents" in result:
        items = list(result.get("generated_intents") or [])
    else:
        items = result if isinstance(result, (list, tuple)) else [result]
    out: list[NormalizedSignal] = []
    for item in items:
        advisory = False
        fallback = False
        direction = None
        score = None
        reason = ""
        if hasattr(item, "direction"):
            direction = getattr(item, "direction")
            score = getattr(item, "score", getattr(item, "raw_score", None))
            reason = getattr(item, "reason", getattr(item, "rank_reason", getattr(item, "trigger", "")))
            advisory = str(getattr(item, "status", "")).upper() in {"NO_TRADE", "BLOCKED_CANDIDATE"} or bool(getattr(item, "blockers", ()))
        elif isinstance(item, Mapping):
            direction = item.get("direction") or item.get("option_type")
            if direction in {"CE", "PE"}:
                direction = "BUY_CALL" if direction == "CE" else "BUY_PUT"
            score = item.get("score", item.get("confidence"))
            reason = item.get("reason") or item.get("confidence_reason") or item.get("setup_type") or ""
            advisory = bool(item.get("advisory_only") or item.get("soft_reject") or item.get("blockers"))
            fallback = bool(item.get("fallback_used") or item.get("recovered_fallback"))
        sig = normalize_signal(
            strategy=spec.strategy,
            instrument=str(market["symbol"]),
            timestamp=market["date"],
            direction=direction,
            score=score,
            reason=reason,
            advisory=advisory,
            fallback=fallback,
        )
        if sig is not None:
            out.append(sig)
    return out


def _run_movement_strategy(spec: StrategySpec, market: Mapping[str, Any]) -> Any:
    from core.movement_regime import MovementRegimeClassifier
    from strategies.movement.compression_breakout import generate_compression_breakout_candidates
    from strategies.movement.event_volatility_expansion import generate_event_volatility_expansion_candidates
    from strategies.movement.exhaustion_reversal import generate_exhaustion_reversal_candidates
    from strategies.movement.failed_breakout_trap import generate_failed_breakout_trap_candidates
    from strategies.movement.late_day_momentum import generate_late_day_momentum_candidates
    from strategies.movement.mean_reversion_extension import generate_mean_reversion_extension_candidates
    from strategies.movement.no_trade_chop import generate_no_trade_candidates
    from strategies.movement.opening_drive import generate_opening_drive_candidates
    from strategies.movement.opening_range_breakout import generate_opening_range_retest_candidates
    from strategies.movement.option_pressure import generate_option_pressure_candidates
    from strategies.movement.trend_pullback import generate_trend_pullback_candidates
    from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates

    funcs = {
        "movement.opening_drive_v1": generate_opening_drive_candidates,
        "movement.opening_range_retest_v1": generate_opening_range_retest_candidates,
        "movement.compression_breakout_v1": generate_compression_breakout_candidates,
        "movement.trend_pullback_v1": generate_trend_pullback_candidates,
        "movement.vwap_reclaim_rejection_v1": generate_vwap_reclaim_rejection_candidates,
        "movement.failed_breakout_trap_v1": generate_failed_breakout_trap_candidates,
        "movement.exhaustion_reversal_v1": generate_exhaustion_reversal_candidates,
        "movement.mean_reversion_extension_v1": generate_mean_reversion_extension_candidates,
        "movement.event_volatility_expansion_v1": generate_event_volatility_expansion_candidates,
        "movement.option_pressure_confirmation_v1": generate_option_pressure_candidates,
        "movement.late_day_momentum_v1": generate_late_day_momentum_candidates,
        "movement.no_trade_engine_v1": generate_no_trade_candidates,
    }
    ctx = _strategy_context(market)
    regime = MovementRegimeClassifier().classify(ctx)
    return funcs[spec.strategy](ctx, regime)


def _run_pairs_strategy(frames: Mapping[str, pd.DataFrame], idx: int) -> list[NormalizedSignal]:
    from strategies.pairs_arbitrage import generate_signal as pairs_signal

    if "NIFTY" not in frames or "BANKNIFTY" not in frames:
        return []
    n = min(len(frames["NIFTY"]), len(frames["BANKNIFTY"]))
    if idx < 30 or idx >= n:
        return []
    a = frames["NIFTY"]
    b = frames["BANKNIFTY"]
    result = pairs_signal(
        float(a.loc[idx, "close"]),
        float(b.loc[idx, "close"]),
        a.loc[max(0, idx - 30): idx - 1, "close"].tolist(),
        b.loc[max(0, idx - 30): idx - 1, "close"].tolist(),
        min_zscore=1.5,
    )
    if not isinstance(result, Mapping):
        return []
    sig = normalize_signal(
        strategy="pairs_arbitrage.generate_signal",
        instrument="NIFTY/BANKNIFTY",
        timestamp=a.loc[idx, "date"],
        direction=result.get("direction"),
        score=result.get("score"),
        reason=result.get("reason"),
    )
    return [] if sig is None else [sig]


def _proxy_trade_rows(signal: NormalizedSignal, frames: Mapping[str, pd.DataFrame], idx_by_instrument: Mapping[str, dict[str, int]]) -> list[dict[str, Any]]:
    if signal.instrument not in frames:
        return []
    frame = frames[signal.instrument]
    idx = idx_by_instrument[signal.instrument].get(signal.timestamp)
    if idx is None:
        return []
    entry_row = frame.loc[idx]
    session_day = pd.Timestamp(entry_row.date).normalize()
    session_rows = frame[pd.to_datetime(frame["date"]).dt.normalize() == session_day].reset_index(drop=True)
    session_idx = int(session_rows.index[session_rows["date"] == entry_row.date][0]) if not session_rows.empty else None
    if session_idx is None:
        return []
    future_rows = session_rows.iloc[session_idx + 1 :].reset_index(drop=True)
    if future_rows.empty:
        return []
    rows: list[dict[str, Any]] = []
    entry = float(entry_row.close)
    for horizon in EXIT_HORIZONS:
        horizon_idx = int(horizon) - 1
        if horizon_idx < len(future_rows):
            exit_row = future_rows.iloc[horizon_idx]
        else:
            exit_row = future_rows.iloc[-1]
        exit_price = float(exit_row.close)
        gross_bps = ((exit_price / entry) - 1.0) * 10000.0 * int(signal.side)
        for cost in COST_BPS:
            net_bps = gross_bps - float(cost)
            rows.append(
                {
                    "strategy": signal.strategy,
                    "instrument": signal.instrument,
                    "timestamp": signal.timestamp,
                    "entry_rule": ENTRY_RULE,
                    "exit_horizon_min": int(horizon),
                    "cost_bps": float(cost),
                    "direction": signal.direction,
                    "side": "LONG" if signal.side > 0 else "SHORT",
                    "score": signal.score,
                    "reason": signal.reason,
                    "entry_underlying": entry,
                    "exit_underlying": exit_price,
                    "gross_bps": gross_bps,
                    "net_bps": net_bps,
                    "net_points": entry * net_bps / 10000.0,
                    "win": bool(net_bps > 0),
                    "executable": False,
                    "verdict": FINAL_VERDICT,
                    "entry_session": str(session_day.date()),
                    "exit_session": str(pd.Timestamp(exit_row.date).normalize().date()),
                    "entry_timestamp": pd.Timestamp(entry_row.date).isoformat(),
                    "exit_timestamp": pd.Timestamp(exit_row.date).isoformat(),
                }
            )
    return rows


def _max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    curve = values.cumsum()
    drawdown = curve - curve.cummax()
    return float(drawdown.min())


def _profit_factor(values: pd.Series) -> float:
    gains = float(values[values > 0].sum())
    losses = abs(float(values[values < 0].sum()))
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _time_bucket(timestamp: str) -> str:
    ts = pd.Timestamp(timestamp)
    minute = ts.hour * 60 + ts.minute
    if minute < 10 * 60:
        return "open_0915_0959"
    if minute < 12 * 60:
        return "mid_morning_1000_1159"
    if minute < 14 * 60:
        return "midday_1200_1359"
    return "late_1400_close"


def _summarize_proxy(trades: pd.DataFrame, candle_counts: Mapping[str, int] | None = None) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(
            columns=[
                "strategy", "exit_horizon_min", "cost_bps", "trade_count", "win_rate",
                "avg_gross_bps", "avg_net_bps", "total_net_points", "expectancy",
                "max_drawdown_proxy", "profit_factor_proxy", "median_return_bps",
                "p25_return_bps", "p75_return_bps", "long_count", "short_count",
                "instrument_breakdown", "time_of_day_breakdown", "spam_flags",
            ]
        )
    rows = []
    trades = trades.copy()
    trades["time_bucket"] = trades["timestamp"].map(_time_bucket)
    for keys, group in trades.groupby(["strategy", "exit_horizon_min", "cost_bps"], dropna=False):
        strategy, horizon, cost = keys
        net = group["net_points"].astype(float)
        net_bps = group["net_bps"].astype(float)
        instrument_counts = group["instrument"].value_counts().sort_index().to_dict()
        time_counts = group["time_bucket"].value_counts().sort_index().to_dict()
        per_instrument = group.groupby("instrument").size()
        spam_flags = _spam_flags(group, per_instrument, candle_counts or {})
        rows.append(
            {
                "strategy": strategy,
                "exit_horizon_min": int(horizon),
                "cost_bps": float(cost),
                "trade_count": int(len(group)),
                "win_rate": round(float(group["win"].mean()), 6),
                "avg_gross_bps": round(float(group["gross_bps"].mean()), 6),
                "avg_net_bps": round(float(net_bps.mean()), 6),
                "total_net_points": round(float(net.sum()), 6),
                "expectancy": round(float(net.mean()), 6),
                "max_drawdown_proxy": round(_max_drawdown(net), 6),
                "profit_factor_proxy": round(_profit_factor(net), 6),
                "median_return_bps": round(float(net_bps.median()), 6),
                "p25_return_bps": round(float(net_bps.quantile(0.25)), 6),
                "p75_return_bps": round(float(net_bps.quantile(0.75)), 6),
                "long_count": int((group["side"] == "LONG").sum()),
                "short_count": int((group["side"] == "SHORT").sum()),
                "instrument_breakdown": json.dumps(instrument_counts, sort_keys=True),
                "time_of_day_breakdown": json.dumps(time_counts, sort_keys=True),
                "spam_flags": "|".join(spam_flags),
            }
        )
    return pd.DataFrame(rows).sort_values(["cost_bps", "exit_horizon_min", "total_net_points"], ascending=[True, True, False])


def _spam_flags(group: pd.DataFrame, per_instrument: pd.Series, candle_counts: Mapping[str, int]) -> list[str]:
    flags: list[str] = []
    if any(int(count) > 100 for count in per_instrument.to_dict().values()):
        flags.append("SIGNAL_SPAM_RISK:MORE_THAN_100_TRADES_PER_DAY_PER_INSTRUMENT")
    for instrument, count in per_instrument.to_dict().items():
        total = int(candle_counts.get(str(instrument), 375))
        if total and int(count) / total > 0.5:
            flags.append("SIGNAL_SPAM_RISK:MORE_THAN_50_PERCENT_CANDLES")
            break
    ordered = group.sort_values(["instrument", "timestamp"])
    for _instrument, inst_group in ordered.groupby("instrument"):
        same_direction_run = 1
        previous = None
        for side in inst_group["side"]:
            if side == previous:
                same_direction_run += 1
                if same_direction_run >= 5:
                    flags.append("SIGNAL_SPAM_RISK:REPEATED_SAME_DIRECTION_WITHOUT_COOLDOWN")
                    return list(dict.fromkeys(flags))
            else:
                same_direction_run = 1
                previous = side
    return list(dict.fromkeys(flags))


def _summarize_signals(signals: list[NormalizedSignal]) -> pd.DataFrame:
    if not signals:
        return pd.DataFrame(columns=["strategy", "signal_count", "direction_distribution", "instrument_breakdown", "time_of_day_breakdown"])
    frame = pd.DataFrame([signal.__dict__ for signal in signals])
    frame["time_bucket"] = frame["timestamp"].map(_time_bucket)
    rows = []
    for strategy, group in frame.groupby("strategy"):
        rows.append(
            {
                "strategy": strategy,
                "signal_count": int(len(group)),
                "direction_distribution": json.dumps(group["direction"].value_counts().sort_index().to_dict(), sort_keys=True),
                "instrument_breakdown": json.dumps(group["instrument"].value_counts().sort_index().to_dict(), sort_keys=True),
                "time_of_day_breakdown": json.dumps(group["time_bucket"].value_counts().sort_index().to_dict(), sort_keys=True),
            }
        )
    return pd.DataFrame(rows).sort_values("signal_count", ascending=False)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return ""
    columns = [str(col) for col in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame.astype(object).where(pd.notna(frame), "").itertuples(index=False, name=None):
        values = [str(value).replace("|", "\\|").replace("\n", " ") for value in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _write_report(
    *,
    out_dir: Path,
    trade_date: str,
    inspection: DatasetInspection,
    matrix: pd.DataFrame,
    proxy_summary: pd.DataFrame,
    signal_summary: pd.DataFrame,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    proxy_positive = []
    proxy_negative = []
    if not proxy_summary.empty:
        base = proxy_summary[(proxy_summary["exit_horizon_min"] == 15) & (proxy_summary["cost_bps"] == 2.0)]
        proxy_positive = sorted(base.loc[base["avg_net_bps"] > 0, "strategy"].unique().tolist())
        proxy_negative = sorted(base.loc[base["avg_net_bps"] <= 0, "strategy"].unique().tolist())
    unsupported = matrix.loc[matrix["capability_bucket"] == "UNSUPPORTED_EXECUTABLE", "strategy"].tolist()
    invalid_volume = matrix.loc[matrix["test_mode"] == "INVALID_VOLUME_PROXY", "strategy"].tolist()
    spam = []
    if not proxy_summary.empty and "spam_flags" in proxy_summary.columns:
        spam = sorted(proxy_summary.loc[proxy_summary["spam_flags"].fillna("") != "", "strategy"].unique().tolist())
    payload = {
        "date": trade_date,
        "verdict": FINAL_VERDICT,
        "entry_rule": ENTRY_RULE,
        "entry_timing_note": ENTRY_TIMING_NOTE,
        "pnl_claim_scope": "underlying_index_directional_proxy_only_no_option_pnl_claim",
        "exit_horizons": list(EXIT_HORIZONS),
        "cost_bps": list(COST_BPS),
        "inspection": inspection.__dict__,
        "safety": {
            "read_only": True,
            "broker_api_called": False,
            "is_order_action": False,
            "allowed_for_live_execution": False,
        },
        "proxy_positive": proxy_positive,
        "proxy_negative": proxy_negative,
        "unsupported_due_to_missing_option_data": unsupported,
        "invalid_volume_or_vwap_assumption": invalid_volume,
        "signal_spam": spam,
        "error_count": len(errors),
    }
    (out_dir / f"all_strategy_report_{trade_date.replace('-', '')}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    lines = [
        f"# All-Strategy Available-Data Backtest {trade_date}",
        "",
        f"Final verdict: **{FINAL_VERDICT}**",
        "",
        "## What Was Actually Tested",
        "",
        f"- Data columns: `{', '.join(inspection.columns)}`",
        f"- Instruments: `{', '.join(inspection.instruments)}`",
        f"- Timestamp range: `{inspection.timestamp_start}` to `{inspection.timestamp_end}`",
        f"- Volume quality: `{inspection.volume_quality}`",
        f"- Entry rule: `{ENTRY_RULE}`",
        f"- Entry timing note: {ENTRY_TIMING_NOTE}",
        f"- Exit horizons: `{', '.join(map(str, EXIT_HORIZONS))}` minutes",
        f"- Costs: `{', '.join(map(str, COST_BPS))}` bps",
        "- PnL metric: underlying index directional proxy only.",
        "- This report does not prove option PnL, option executability, fill quality, spread cost, depth, OI, Greeks, or IV edge.",
        "",
        "## What Was Skipped And Why",
        "",
    ]
    skipped = matrix[matrix["capability_bucket"] == "UNSUPPORTED_EXECUTABLE"][["strategy", "missing_inputs", "reason"]]
    lines.append(_markdown_table(skipped) if not skipped.empty else "No unsupported executable strategies.")
    lines.extend(["", "## Proxy-Positive Strategies", ""])
    lines.append("\n".join(f"- {item}" for item in proxy_positive) if proxy_positive else "None at 15m / 2 bps.")
    lines.extend(["", "## Proxy-Negative Strategies", ""])
    lines.append("\n".join(f"- {item}" for item in proxy_negative) if proxy_negative else "None at 15m / 2 bps.")
    lines.extend(["", "## Unsupported Due To Missing Option Data", ""])
    lines.append("\n".join(f"- {item}" for item in unsupported) if unsupported else "None.")
    lines.extend(["", "## Signal Spam", ""])
    lines.append("\n".join(f"- {item}" for item in spam) if spam else "None.")
    lines.extend(["", "## Invalid Volume / VWAP Assumptions", ""])
    lines.append("\n".join(f"- {item}" for item in invalid_volume) if invalid_volume else "None.")
    lines.extend(["", "## Top Proxy Rows At 15m / 2bps", ""])
    top = proxy_summary[(proxy_summary["exit_horizon_min"] == 15) & (proxy_summary["cost_bps"] == 2.0)].head(20)
    lines.append(_markdown_table(top) if not top.empty else "No proxy rows.")
    lines.extend(["", "## Safety", "", "- broker_api_called=false", "- is_order_action=false", "- allowed_for_live_execution=false", "- read_only=true"])
    (out_dir / f"all_strategy_report_{trade_date.replace('-', '')}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def run_backtest(
    *,
    data_path: Path | str,
    out_dir: Path | str,
    trade_date: str,
    extra_strategies: Iterable[StrategySpec] | None = None,
) -> dict[str, Any]:
    _forbidden_broker_call_sentinel  # keep the no-call sentinel visible to tests.
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    data = load_dataset(data_path)
    inspection = inspect_dataset(data)
    specs = discover_strategy_specs() + list(extra_strategies or ())
    matrix = build_capability_matrix(inspection, specs)
    frames = _prepare_frames(data)
    idx_by_instrument = {
        instrument: {pd.Timestamp(row.date).isoformat(): int(idx) for idx, row in frame.iterrows()}
        for instrument, frame in frames.items()
    }

    errors: list[dict[str, Any]] = []
    all_signals: list[NormalizedSignal] = []
    signal_only: list[NormalizedSignal] = []
    proxy_trades: list[dict[str, Any]] = []
    capability_by_strategy = matrix.set_index("strategy").to_dict("index")

    for spec in specs:
        cap = capability_by_strategy.get(spec.strategy, {})
        bucket = cap.get("capability_bucket", "ERROR")
        test_mode = cap.get("test_mode", "ERROR")
        if bucket == "UNSUPPORTED_EXECUTABLE":
            continue
        instruments = TRADEABLE_INSTRUMENTS
        if spec.strategy == "pairs_arbitrage.generate_signal":
            for idx in range(30, min(len(frames.get("NIFTY", [])), len(frames.get("BANKNIFTY", []))) - max(EXIT_HORIZONS)):
                try:
                    signals = _run_pairs_strategy(frames, idx)
                    all_signals.extend(signals)
                    for signal in signals:
                        if bucket == "SIGNAL_ONLY" or signal.signal_only:
                            signal_only.append(signal)
                        else:
                            # Pairs are signal-only in this harness because multi-leg spread point accounting is not comparable.
                            signal_only.append(signal)
                except Exception as exc:
                    errors.append({"strategy": spec.strategy, "module": spec.module, "callable": spec.callable, "error": repr(exc), "traceback": traceback.format_exc(limit=4)})
            continue
        for instrument in instruments:
            if instrument not in frames:
                continue
            frame = frames[instrument]
            warmup = 30 if len(frame) > (30 + max(EXIT_HORIZONS)) else 0
            for idx in range(warmup, max(warmup, len(frame) - max(EXIT_HORIZONS))):
                market = _market_row(frames, instrument, idx)
                try:
                    if spec.strategy.startswith("movement."):
                        result = _run_movement_strategy(spec, market)
                    elif spec.runner is not None:
                        result = spec.runner(market)
                    else:
                        result = None
                    signals = _extract_signals(spec, market, result)
                    all_signals.extend(signals)
                    for signal in signals:
                        if bucket == "SIGNAL_ONLY" or signal.signal_only or test_mode == "SKIP_PNL":
                            signal_only.append(signal)
                        elif bucket in {"SUPPORTED_PROXY", "PARTIAL_PROXY"}:
                            proxy_trades.extend(_proxy_trade_rows(signal, frames, idx_by_instrument))
                except Exception as exc:
                    errors.append({"strategy": spec.strategy, "module": spec.module, "callable": spec.callable, "error": repr(exc), "traceback": traceback.format_exc(limit=4)})

    proxy_trades_df = pd.DataFrame(proxy_trades)
    candle_counts = {instrument: int(len(frame)) for instrument, frame in frames.items()}
    proxy_summary = _summarize_proxy(proxy_trades_df, candle_counts)
    signal_summary = _summarize_signals(signal_only)
    errors_df = pd.DataFrame(errors, columns=["strategy", "module", "callable", "error", "traceback"])

    matrix.to_csv(out_path / "strategy_data_capability_matrix.csv", index=False)
    proxy_trades_df.to_csv(out_path / "all_strategy_proxy_trades.csv", index=False)
    proxy_summary.to_csv(out_path / "all_strategy_proxy_summary.csv", index=False)
    signal_summary.to_csv(out_path / "all_strategy_signal_only_summary.csv", index=False)
    errors_df.to_csv(out_path / "strategy_errors.csv", index=False)
    payload = _write_report(
        out_dir=out_path,
        trade_date=trade_date,
        inspection=inspection,
        matrix=matrix,
        proxy_summary=proxy_summary,
        signal_summary=signal_summary,
        errors=errors,
    )
    payload["error_count"] = len(errors)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline all-strategy available-data proxy backtest.")
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    result = run_backtest(data_path=args.data, out_dir=args.out, trade_date=args.date)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
