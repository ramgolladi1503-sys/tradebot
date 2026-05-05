import pandas as pd
from config import config as cfg
from core.market_context import derive_market_context
from core.liquidity_truth import assess_liquidity_quality
from core.option_entry import get_option_ltp_sla_sec
from core.time_utils import now_ist
from core.feature_contract import FeatureContract


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add common indicators to an OHLCV dataframe.
    Required columns: ['open','high','low','close','volume']
    """
    df = df.copy()
    df["sma_10"] = df["close"].rolling(10).mean()
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()

    # RSI 14
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-9)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # ATR 14
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()

    # VWAP (cumulative)
    pv = df["close"] * df["volume"]
    df["vwap"] = (pv.cumsum() / df["volume"].replace(0, 1).cumsum())
    df["vwap_slope"] = df["vwap"].diff(3)

    # Returns
    df["return_1"] = df["close"].pct_change(1)

    # RSI momentum
    df["rsi_mom"] = df["rsi_14"].diff(3)

    # Simple volume profile proxy: z-score of volume
    vol_mean = df["volume"].rolling(20).mean()
    vol_std = df["volume"].rolling(20).std().replace(0, 1)
    df["vol_z"] = (df["volume"] - vol_mean) / vol_std

    # ADX proxy
    df["adx_14"] = _adx(df)

    return df


def _adx(df, period=14):
    high = df["high"]
    low = df["low"]
    close = df["close"]
    plus_dm = high.diff()
    minus_dm = low.diff() * -1
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    denom = (plus_di + minus_di).replace(0, 1e-9)
    dx = (abs(plus_di - minus_di) / denom) * 100
    dx = dx.replace([float("inf"), float("-inf")], 0).fillna(0)
    return dx.rolling(period).mean().fillna(0)


def _time_bucket(ts):
    try:
        h = ts.hour
    except Exception:
        h = now_ist().hour
    if h < 11:
        return "OPEN"
    if h < 14:
        return "MID"
    return "CLOSE"


def _regime_label(regime):
    r = str(regime or "").upper()
    mapping = {
        "TREND": "TREND",
        "RANGE": "RANGE",
        "RANGE_VOLATILE": "RANGE_VOLATILE",
        "EVENT": "EVENT",
        "PANIC": "PANIC",
    }
    return mapping.get(r, "NEUTRAL")


def _vol_quartile(vol_z):
    try:
        v = float(vol_z)
    except Exception:
        return 2
    if v <= -0.5:
        return 1
    if v <= 0.5:
        return 2
    if v <= 1.5:
        return 3
    return 4


def build_trade_features(market_data, opt):
    """
    Build a feature dict for ML scoring.
    """
    ltp = market_data.get("ltp", 0)
    vwap = market_data.get("vwap", ltp)
    atr = market_data.get("atr", 0)

    spread = max(opt["ask"] - opt["bid"], 0)
    spread_pct = spread / opt["ltp"] if opt["ltp"] else 0
    moneyness = (ltp - opt["strike"]) / ltp if ltp else 0
    vwap_dist = (ltp - vwap) / vwap if vwap else 0

    regime = market_data.get("primary_regime") or market_data.get("regime")
    time_bucket = market_data.get("time_bucket") or _time_bucket(market_data.get("timestamp", now_ist()))
    is_expiry = market_data.get("day_type") in ("EXPIRY_DAY",)
    vol_q = market_data.get("vol_quartile")
    if vol_q is None:
        vol_q = _vol_quartile(market_data.get("vol_z", 0))

    fx_ret_5m = market_data.get("fx_ret_5m")
    if fx_ret_5m is None:
        fx_ret_5m = market_data.get("x_usdinr_ret5") or market_data.get("x_fx_ret5")
    vix_z = market_data.get("vix_z")
    if vix_z is None:
        vix_z = market_data.get("x_india_vix_z") or market_data.get("x_vix_z")
    crude_ret_15m = market_data.get("crude_ret_15m")
    if crude_ret_15m is None:
        crude_ret_15m = market_data.get("x_crude_ret15") or market_data.get("x_crudeoil_ret15")
    corr_fx_nifty = market_data.get("corr_fx_nifty")
    if corr_fx_nifty is None:
        corr_fx_nifty = market_data.get("x_usdinr_corr_nifty") or market_data.get("x_fx_corr_nifty")

    feats = {
        "ltp": opt["ltp"],
        "bid": opt["bid"],
        "ask": opt["ask"],
        "spread_pct": spread_pct,
        "volume": opt.get("volume", 0),
        "atr": atr,
        "vwap_dist": vwap_dist,
        "moneyness": moneyness,
        "is_call": 1 if opt["type"] == "CE" else 0,
        "vwap_slope": market_data.get("vwap_slope", 0),
        "rsi_mom": market_data.get("rsi_mom", 0),
        "vol_z": market_data.get("vol_z", 0),
        "fx_ret_5m": 0.0 if fx_ret_5m is None else fx_ret_5m,
        "vix_z": 0.0 if vix_z is None else vix_z,
        "crude_ret_15m": 0.0 if crude_ret_15m is None else crude_ret_15m,
        "corr_fx_nifty": 0.0 if corr_fx_nifty is None else corr_fx_nifty,
        "seg_regime": _regime_label(regime),
        "seg_bucket": str(time_bucket).upper(),
        "seg_expiry": 1 if is_expiry else 0,
        "seg_vol_q": int(vol_q),
    }
    try:
        for k, v in (market_data or {}).items():
            if isinstance(k, str) and k.startswith("x_"):
                feats[k] = 0.0 if v is None else v
    except Exception:
        pass
    return feats


def validate_trade_features(features, required_features=None):
    contract = FeatureContract.from_model_metadata(
        model_features=required_features,
        fallback_features=[],
    )
    return contract.validate(features)


def _safe_float(value):
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _clamp01(value: float | None, *, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    return max(0.0, min(1.0, float(value)))


def _coalesce_float(*values):
    for value in values:
        out = _safe_float(value)
        if out is not None:
            return out
    return None


def _age_quality(age_sec: float | None, max_age_sec: float | None) -> float:
    if age_sec is None or max_age_sec in (None, 0):
        return 0.0
    return _clamp01(1.0 - (float(age_sec) / max(float(max_age_sec) * 2.0, 1e-6)), default=0.0)


def assess_trade_feature_quality(market_data, opt) -> dict:
    """
    Validate quote/liquidity readiness separately from ML feature-shape validation.
    This is additive and does not alter the model feature contract.
    """
    market_data = dict(market_data or {})
    opt = dict(opt or {})
    market_ctx = derive_market_context(market_data)
    quote_age_sec = _safe_float(opt.get("quote_age_sec"))
    quote_ok = bool(opt.get("quote_ok", market_data.get("quote_ok", True)))
    bid = _safe_float(opt.get("bid"))
    ask = _safe_float(opt.get("ask"))
    option_ltp = (
        _safe_float(opt.get("ltp"))
        or _safe_float(opt.get("last_price"))
        or _safe_float(opt.get("opt_ltp"))
        or _safe_float(market_data.get("opt_ltp"))
    )
    volume = max(
        _safe_float(opt.get("current_volume")) or 0.0,
        _safe_float(opt.get("volume")) or 0.0,
    )
    oi = max(
        _safe_float(opt.get("oi")) or 0.0,
        _safe_float(opt.get("open_interest")) or 0.0,
        _safe_float(market_data.get("oi")) or 0.0,
    )
    issues: list[str] = []
    require_book_for_fresh = bool(getattr(cfg, "DATA_TRUTH_REQUIRE_BOOK_FOR_FRESH", True))
    max_chain_age_sec = max(
        _safe_float(getattr(cfg, "DATA_TRUTH_MAX_CHAIN_SNAPSHOT_AGE_SEC", None)) or 0.0,
        _safe_float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", None)) or 0.0,
        0.0,
    )

    ltp_age_sec = _coalesce_float(
        opt.get("ltp_age_sec"),
        opt.get("option_ltp_age_sec"),
        market_data.get("ltp_age_sec"),
        market_data.get("option_ltp_age_sec"),
        quote_age_sec,
    )
    chain_snapshot_age_sec = _coalesce_float(
        opt.get("chain_snapshot_age_sec"),
        opt.get("liquidity_age_sec"),
        market_data.get("chain_snapshot_age_sec"),
        market_data.get("liquidity_age_sec"),
    )
    bid_age_sec = _coalesce_float(
        opt.get("bid_age_sec"),
        opt.get("best_bid_age_sec"),
        market_data.get("bid_age_sec"),
        chain_snapshot_age_sec if bid is not None else None,
        quote_age_sec if bid is not None else None,
    )
    ask_age_sec = _coalesce_float(
        opt.get("ask_age_sec"),
        opt.get("best_ask_age_sec"),
        market_data.get("ask_age_sec"),
        chain_snapshot_age_sec if ask is not None else None,
        quote_age_sec if ask is not None else None,
    )

    if option_ltp is None or option_ltp <= 0:
        issues.append("missing_option_ltp")
    if bid is None or ask is None:
        issues.append("missing_bid_ask")

    spread_pct = None
    if bid is not None and ask is not None and option_ltp not in (None, 0.0):
        spread_pct = max(0.0, ask - bid) / max(option_ltp, 1e-6)
    else:
        issues.append("missing_spread")
    spread_change_ratio = _coalesce_float(
        opt.get("spread_change_ratio"),
        market_data.get("spread_change_ratio"),
    )
    spread_stability_hint = _coalesce_float(
        opt.get("spread_stability_score"),
        market_data.get("spread_stability_score"),
    )

    if quote_age_sec is None:
        issues.append("missing_quote_age")
    if option_ltp is not None and ltp_age_sec is None:
        issues.append("missing_ltp_age")
    if bid is not None and bid_age_sec is None:
        issues.append("missing_bid_age")
    if ask is not None and ask_age_sec is None:
        issues.append("missing_ask_age")

    max_age_sec = get_option_ltp_sla_sec(
        market_ctx.mode,
        float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0)),
        allow_stale_quotes=bool(market_ctx.allow_stale_quotes),
        market_open=bool(market_ctx.is_market_open),
        expiry_lotto_mode=bool(getattr(cfg, "EXPIRY_LOTTO_MODE", False)),
    )
    quote_completeness = "MISSING"
    if option_ltp not in (None, 0.0) and bid is not None and ask is not None:
        quote_completeness = "FULL"
    elif option_ltp not in (None, 0.0) and (bid is not None or ask is not None):
        quote_completeness = "PARTIAL"
    elif option_ltp not in (None, 0.0):
        quote_completeness = "LTP_ONLY"
    elif bid is not None or ask is not None:
        quote_completeness = "BOOK_ONLY"

    quote_consistency_ok = True
    if bid is not None and ask is not None and bid > ask:
        quote_consistency_ok = False
        issues.append("inconsistent_bid_ask")
    drift_tol_pct = max(float(getattr(cfg, "DATA_TRUTH_LTP_BOOK_DRIFT_TOL_PCT", 0.03) or 0.03), 0.0)
    if (
        quote_consistency_ok
        and option_ltp not in (None, 0.0)
        and bid is not None
        and ask is not None
    ):
        lower = min(bid, ask) * max(0.0, 1.0 - drift_tol_pct)
        upper = max(bid, ask) * (1.0 + drift_tol_pct)
        if float(option_ltp) < lower or float(option_ltp) > upper:
            quote_consistency_ok = False
            issues.append("inconsistent_ltp_vs_book")

    critical_ages: list[float] = []
    if ltp_age_sec is not None:
        critical_ages.append(float(ltp_age_sec))
    if bid is not None and bid_age_sec is not None:
        critical_ages.append(float(bid_age_sec))
    if ask is not None and ask_age_sec is not None:
        critical_ages.append(float(ask_age_sec))
    if chain_snapshot_age_sec is not None and (bid is not None or ask is not None):
        critical_ages.append(float(chain_snapshot_age_sec))
    oldest_critical_quote_age_sec = max(critical_ages) if critical_ages else None

    data_state = "DATA_OK"
    if quote_completeness == "MISSING":
        data_state = "DATA_MISSING"
    elif not quote_consistency_ok:
        data_state = "DATA_INCONSISTENT"
    else:
        stale_components = []
        if oldest_critical_quote_age_sec is not None and float(oldest_critical_quote_age_sec) > float(max_age_sec):
            stale_components.append("critical_quote")
        if chain_snapshot_age_sec is not None and max_chain_age_sec > 0 and float(chain_snapshot_age_sec) > float(max_chain_age_sec):
            stale_components.append("chain_snapshot")
        if stale_components:
            data_state = "DATA_STALE"
            issues.append("stale_quote")
        elif quote_completeness != "FULL" or (require_book_for_fresh and (bid is None or ask is None)):
            data_state = "DATA_PARTIAL"

    if data_state == "DATA_PARTIAL" and quote_completeness == "LTP_ONLY":
        issues.append("ltp_only_quote")
    if data_state == "DATA_PARTIAL" and quote_completeness == "BOOK_ONLY":
        issues.append("book_only_quote")

    oldest_critical_age = oldest_critical_quote_age_sec
    fresh_quote_ok = bool(
        quote_ok
        and data_state == "DATA_OK"
        and oldest_critical_age is not None
        and float(oldest_critical_age) <= float(max_age_sec)
    )

    liquidity_validation_mode = "NONE"
    if bid is not None and ask is not None:
        liquidity_validation_mode = "CHAIN_CACHE" if opt.get("liquidity_cache_hit") else "LIVE_BOOK"
    elif option_ltp is not None:
        liquidity_validation_mode = "LTP_ONLY"

    liquidity_ok = bool(
        volume >= max(float(getattr(cfg, "MIN_VOLUME_FILTER", 1.0) or 1.0), 1.0)
        and data_state == "DATA_OK"
        and (chain_snapshot_age_sec is None or max_chain_age_sec <= 0 or float(chain_snapshot_age_sec) <= float(max_chain_age_sec))
    )
    if not liquidity_ok:
        issues.append("missing_liquidity_validation")

    max_spread_pct = max(float(getattr(cfg, "MAX_SPREAD_PCT", 0.03) or 0.03), 1e-6)
    spread_source = str(
        opt.get("spread_source")
        or opt.get("price_source")
        or opt.get("liquidity_source")
        or market_data.get("spread_source")
        or "none"
    ).strip().lower()
    if spread_change_ratio is not None and float(spread_change_ratio) > 0.5:
        issues.append("unstable_spread")
    spread_ok = bool(
        spread_pct is not None
        and data_state == "DATA_OK"
        and float(spread_pct) <= float(max_spread_pct)
        and quote_consistency_ok
        and (chain_snapshot_age_sec is None or max_chain_age_sec <= 0 or float(chain_snapshot_age_sec) <= float(max_chain_age_sec))
    )
    if spread_pct is None:
        spread_quality = 0.0
    else:
        spread_quality = _clamp01(1.0 - min(float(spread_pct) / max_spread_pct, 1.0), default=0.0)
    full_scale = max(float(getattr(cfg, "DATA_CONFIDENCE_SPREAD_CHANGE_FULL_SCALE", 1.0) or 1.0), 1e-6)
    if spread_stability_hint is not None:
        spread_stability_score = _clamp01(spread_stability_hint, default=0.0)
    elif spread_change_ratio is not None:
        spread_stability_score = _clamp01(
            1.0 - min(float(spread_change_ratio) / full_scale, 1.0),
            default=0.0,
        )
    elif spread_pct is None:
        spread_stability_score = 0.0
    else:
        spread_stability_score = _clamp01(0.65 + (0.35 * float(spread_quality)), default=0.0)
    spread_ok = bool(
        spread_ok
        and float(spread_stability_score)
        >= float(getattr(cfg, "DATA_CONFIDENCE_MIN_SPREAD_STABILITY_OK", 0.35) or 0.35)
    )

    book_freshness_score = _age_quality(oldest_critical_age, max_age_sec)
    freshness_quality = float(book_freshness_score)
    quote_completeness_score = {
        "FULL": 1.0,
        "PARTIAL": 0.65,
        "LTP_ONLY": 0.45,
        "BOOK_ONLY": 0.35,
        "MISSING": 0.0,
    }.get(quote_completeness, 0.0)
    quote_consistency_score = 1.0 if quote_consistency_ok else 0.05
    if data_state == "DATA_PARTIAL":
        freshness_quality *= 0.45
        spread_quality *= 0.6
    elif data_state == "DATA_STALE":
        freshness_quality = 0.0
        spread_quality *= 0.25
    elif data_state in {"DATA_INCONSISTENT", "DATA_MISSING"}:
        freshness_quality = 0.0
        spread_quality = 0.0
    if data_state == "DATA_PARTIAL":
        spread_stability_score *= 0.75
        quote_completeness_score *= 0.75
    elif data_state == "DATA_STALE":
        spread_stability_score *= 0.55
        quote_completeness_score *= 0.6
    elif data_state in {"DATA_INCONSISTENT", "DATA_MISSING"}:
        spread_stability_score *= 0.2
        quote_completeness_score *= 0.2
        quote_consistency_score = min(float(quote_consistency_score), 0.05)

    liquidity_quality_payload = assess_liquidity_quality(
        volume=volume,
        oi=oi,
        spread_pct=spread_pct,
        quote_consistency_score=quote_consistency_score,
        quote_ok=quote_ok,
    )
    liquidity_quality = float(liquidity_quality_payload["liquidity_score"])
    liquidity_flow_score = float(liquidity_quality_payload["liquidity_flow_score"] or 0.0)
    liquidity_book_score = float(liquidity_quality_payload["liquidity_book_score"] or 0.0)
    liquidity_spread_score = float(liquidity_quality_payload["liquidity_spread_score"] or 0.0)
    liquidity_volume_score = float(liquidity_quality_payload["liquidity_volume_score"] or 0.0)
    liquidity_oi_score = float(liquidity_quality_payload["liquidity_oi_score"] or 0.0)

    data_confidence = _clamp01(
        (
            (0.35 * float(book_freshness_score))
            + (0.25 * float(spread_stability_score))
            + (0.20 * float(quote_completeness_score))
            + (0.20 * float(quote_consistency_score))
        ),
        default=0.0,
    )
    if data_state == "DATA_PARTIAL":
        data_confidence *= 0.65
    elif data_state == "DATA_STALE":
        data_confidence *= 0.55
    elif data_state == "DATA_INCONSISTENT":
        data_confidence *= 0.15
    elif data_state == "DATA_MISSING":
        data_confidence *= 0.05
    min_spread_stability_ok = float(getattr(cfg, "DATA_CONFIDENCE_MIN_SPREAD_STABILITY_OK", 0.35) or 0.35)
    if float(spread_stability_score) < min_spread_stability_ok:
        data_confidence *= max(0.2, 0.5 + float(spread_stability_score))

    return {
        "issues": list(dict.fromkeys(issues)),
        "fresh_quote_ok": fresh_quote_ok,
        "liquidity_ok": liquidity_ok,
        "spread_ok": spread_ok,
        "quote_ok": quote_ok,
        "spread_pct": spread_pct,
        "quote_age_sec": quote_age_sec,
        "oldest_critical_quote_age_sec": oldest_critical_age,
        "ltp_age_sec": ltp_age_sec,
        "bid_age_sec": bid_age_sec,
        "ask_age_sec": ask_age_sec,
        "chain_snapshot_age_sec": chain_snapshot_age_sec,
        "max_quote_age_sec": float(max_age_sec),
        "volume": float(volume),
        "market_mode": market_ctx.mode,
        "quote_completeness": quote_completeness,
        "quote_consistency_ok": quote_consistency_ok,
        "data_state": data_state,
        "spread_source": spread_source,
        "liquidity_validation_mode": liquidity_validation_mode,
        "freshness_quality": freshness_quality,
        "liquidity_quality": liquidity_quality,
        "liquidity_flow_score": liquidity_flow_score,
        "liquidity_book_score": liquidity_book_score,
        "liquidity_spread_score": liquidity_spread_score,
        "liquidity_volume_score": liquidity_volume_score,
        "liquidity_oi_score": liquidity_oi_score,
        "spread_quality": spread_quality,
        "data_confidence": data_confidence,
        "spread_stability_score": spread_stability_score,
        "book_freshness_score": book_freshness_score,
        "quote_completeness_score": quote_completeness_score,
        "quote_consistency_score": quote_consistency_score,
        "spread_change_ratio": spread_change_ratio,
    }
