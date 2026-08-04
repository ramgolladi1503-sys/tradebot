from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from .contracts import SAFETY_CONTRACT, SCHEMA_VERSION
from .dataset import validate_candidate_dataset


MARKET_CORPUS_LANE = "MARKET_RESPONSE_PRETRAINING_ONLY"
SUPPORTED_INDEX_KEYS = {
    "NSE_INDEX|NIFTY 50": "NIFTY",
    "NSE_INDEX|NIFTY BANK": "BANKNIFTY",
    "BSE_INDEX|SENSEX": "SENSEX",
}
REQUIRED_TICK_COLUMNS = ("timestamp", "instrument_key", "ltp")
PRETRAINING_REQUIRED_FEATURES = (
    "spread_pct",
    "quote_age_sec",
    "relative_volume",
    "distance_from_vwap_atr",
    "breadth_up_1",
    "breadth_down_1",
    "index_breadth_divergence",
    "option_return_1",
    "option_return_3",
)


@dataclass(frozen=True)
class MarketCorpusConfig:
    bar_frequency: str = "1min"
    horizon_bars: int = 5
    min_move_bps: float = 5.0
    friction_r: float = 0.10
    min_option_instruments_per_bar: int = 10
    max_spread_pct: float = 50.0
    symbols: tuple[str, ...] = ("NIFTY", "BANKNIFTY", "SENSEX")

    def __post_init__(self) -> None:
        if self.horizon_bars < 1:
            raise ValueError("market_corpus_horizon_invalid")
        if self.min_move_bps <= 0:
            raise ValueError("market_corpus_move_threshold_invalid")
        if self.min_option_instruments_per_bar < 1:
            raise ValueError("market_corpus_option_support_invalid")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _first_bytes(path: Path, count: int = 64) -> bytes:
    with path.open("rb") as handle:
        return handle.read(count)


def validate_materialized_parquet(path: str | Path) -> Path:
    source = Path(path)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"market_corpus_file_missing:{source}")
    prefix = _first_bytes(source)
    if prefix.startswith(b"version https://git-lfs.github.com/spec"):
        raise ValueError(f"market_corpus_lfs_pointer_not_materialized:{source}")
    if prefix[:4] != b"PAR1":
        raise ValueError(f"market_corpus_not_parquet:{source}")
    return source


def _timestamp_series(frame: pd.DataFrame) -> pd.Series:
    for column in ("ts", "timestamp", "timestamp_epoch_ms", "timestamp_epoch", "ts_epoch"):
        if column not in frame.columns:
            continue
        values = frame[column]
        if pd.api.types.is_numeric_dtype(values):
            numeric = pd.to_numeric(values, errors="coerce")
            finite = numeric.dropna()
            unit = "ms" if (not finite.empty and float(finite.abs().median()) > 10_000_000_000) else "s"
            return pd.to_datetime(numeric, unit=unit, errors="coerce", utc=True)
        return pd.to_datetime(values, errors="coerce", utc=True)
    raise ValueError("market_corpus_timestamp_column_missing")


def _select_numeric(frame: pd.DataFrame, names: Sequence[str]) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return pd.to_numeric(frame[name], errors="coerce")
    return pd.Series(np.nan, index=frame.index, dtype=float)


def _select_text(frame: pd.DataFrame, names: Sequence[str]) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name].astype(str).str.strip()
    return pd.Series("", index=frame.index, dtype=object)


def normalize_tick_frame(frame: pd.DataFrame, *, source_file: str = "") -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=REQUIRED_TICK_COLUMNS)
    out = pd.DataFrame(index=frame.index)
    out["timestamp"] = _timestamp_series(frame)
    out["instrument_key"] = _select_text(frame, ("instrument_key", "instrument", "symbol", "tradingsymbol"))
    out["ltp"] = _select_numeric(frame, ("ltp", "last_price", "close"))
    out["bid_price"] = _select_numeric(frame, ("bid_price", "bid", "best_bid"))
    out["ask_price"] = _select_numeric(frame, ("ask_price", "ask", "best_ask"))
    out["volume"] = _select_numeric(frame, ("volume", "vol", "cumulative_volume"))
    out["oi"] = _select_numeric(frame, ("oi", "open_interest"))
    out["iv"] = _select_numeric(frame, ("iv", "implied_volatility"))
    out["delta"] = _select_numeric(frame, ("delta",))
    out["theta"] = _select_numeric(frame, ("theta",))
    out["gamma"] = _select_numeric(frame, ("gamma",))
    out["vega"] = _select_numeric(frame, ("vega",))
    out["source_file"] = str(source_file)
    out = out.dropna(subset=["timestamp", "ltp"])
    out = out[out["instrument_key"].astype(str).str.len() > 0]
    out = out[np.isfinite(out["ltp"]) & (out["ltp"] > 0)]
    return out.sort_values(["timestamp", "instrument_key"], kind="stable").reset_index(drop=True)


def load_market_tick_corpus(paths: Iterable[str | Path]) -> tuple[pd.DataFrame, dict[str, Any]]:
    frames: list[pd.DataFrame] = []
    evidence: list[dict[str, Any]] = []
    for raw_path in sorted({str(Path(item)) for item in paths}):
        path = validate_materialized_parquet(raw_path)
        payload = path.read_bytes()
        raw = pd.read_parquet(path)
        normalized = normalize_tick_frame(raw, source_file=str(path))
        evidence.append(
            {
                "path": str(path),
                "sha256": sha256(payload).hexdigest(),
                "bytes": int(path.stat().st_size),
                "raw_rows": int(raw.shape[0]),
                "normalized_rows": int(normalized.shape[0]),
                "columns": sorted(str(column) for column in raw.columns),
            }
        )
        if not normalized.empty:
            frames.append(normalized)
    if not frames:
        raise ValueError("market_corpus_no_readable_rows")
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=["timestamp", "instrument_key", "ltp"], keep="last")
    combined = combined.sort_values(["timestamp", "instrument_key"], kind="stable").reset_index(drop=True)
    manifest = {
        "lane": MARKET_CORPUS_LANE,
        "schema_version": SCHEMA_VERSION,
        "source_files": evidence,
        "source_file_count": int(len(evidence)),
        "normalized_rows": int(combined.shape[0]),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "append": False,
    }
    contract_payload = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    manifest["source_contract_sha256"] = sha256(contract_payload.encode("utf-8")).hexdigest()
    return combined, manifest


def _symbol_for_key(value: Any) -> str | None:
    key = str(value or "").strip().upper()
    if key in SUPPORTED_INDEX_KEYS:
        return SUPPORTED_INDEX_KEYS[key]
    if "NIFTY BANK" in key or "BANKNIFTY" in key:
        return "BANKNIFTY"
    if "NIFTY 50" in key or key.endswith("|NIFTY"):
        return "NIFTY"
    if "SENSEX" in key and "INDEX" in key:
        return "SENSEX"
    return None


def _is_option_key(value: Any) -> bool:
    key = str(value or "").strip().upper()
    return "_FO|" in key or key.startswith("NSE_FO|") or key.startswith("BSE_FO|")


def audit_market_tick_corpus(frame: pd.DataFrame, config: MarketCorpusConfig | None = None) -> dict[str, Any]:
    cfg = config or MarketCorpusConfig()
    source = frame.copy()
    source["symbol"] = source["instrument_key"].map(_symbol_for_key)
    source["is_option"] = source["instrument_key"].map(_is_option_key)
    source["session_date"] = source["timestamp"].dt.tz_convert("Asia/Kolkata").dt.date.astype(str)
    index_rows = source[source["symbol"].isin(set(cfg.symbols))]
    option_rows = source[source["is_option"]]
    option_metadata_columns = {
        "option_type",
        "strike",
        "expiry",
        "expiry_date",
        "trading_symbol",
        "tradingsymbol",
    }
    available = set(str(column) for column in frame.columns)
    return {
        "lane": MARKET_CORPUS_LANE,
        "verdict": "REAL_MARKET_CORPUS_AVAILABLE" if not index_rows.empty and not option_rows.empty else "MARKET_CORPUS_INCOMPLETE",
        "raw_rows": int(source.shape[0]),
        "index_rows": int(index_rows.shape[0]),
        "option_rows": int(option_rows.shape[0]),
        "sessions": int(source["session_date"].nunique()),
        "first_timestamp": source["timestamp"].min().isoformat() if not source.empty else None,
        "last_timestamp": source["timestamp"].max().isoformat() if not source.empty else None,
        "symbols": sorted(str(item) for item in index_rows["symbol"].dropna().unique()),
        "instrument_count": int(source["instrument_key"].nunique()),
        "option_contract_metadata_available": bool(option_metadata_columns.intersection(available)),
        "candidate_lineage_available": False,
        "candidate_edge_certification_allowed": False,
        "pretraining_allowed": bool(not index_rows.empty and not option_rows.empty),
        "reason": "Raw market response can pretrain a state model; it cannot prove which historical TradeBot candidates were emitted.",
        "config": cfg.to_dict(),
        **SAFETY_CONTRACT,
    }


def _option_minute_features(option_rows: pd.DataFrame, config: MarketCorpusConfig) -> pd.DataFrame:
    if option_rows.empty:
        return pd.DataFrame()
    work = option_rows.copy()
    work["minute"] = work["timestamp"].dt.floor(config.bar_frequency)
    work = work.sort_values(["instrument_key", "timestamp"], kind="stable")
    work["option_return_1_raw"] = work.groupby("instrument_key", sort=False)["ltp"].pct_change(1)
    work["option_return_3_raw"] = work.groupby("instrument_key", sort=False)["ltp"].pct_change(3)
    valid_quote = (work["bid_price"] > 0) & (work["ask_price"] >= work["bid_price"])
    midpoint = (work["bid_price"] + work["ask_price"]) / 2.0
    work["spread_pct_raw"] = np.where(valid_quote & (midpoint > 0), (work["ask_price"] - work["bid_price"]) / midpoint * 100.0, np.nan)
    work.loc[work["spread_pct_raw"] > config.max_spread_pct, "spread_pct_raw"] = np.nan
    minute_end = work["minute"] + pd.Timedelta(config.bar_frequency)
    work["quote_age_raw"] = (minute_end - work["timestamp"]).dt.total_seconds().clip(lower=0.0)
    grouped = work.groupby("minute", sort=True)
    out = grouped.agg(
        option_instrument_count=("instrument_key", "nunique"),
        option_return_1=("option_return_1_raw", "median"),
        option_return_3=("option_return_3_raw", "median"),
        option_return_dispersion=("option_return_1_raw", "std"),
        spread_pct=("spread_pct_raw", "median"),
        quote_age_sec=("quote_age_raw", "max"),
        option_volume=("volume", "sum"),
        option_oi=("oi", "sum"),
        option_iv_median=("iv", "median"),
        option_abs_delta_median=("delta", lambda values: values.abs().median()),
        option_gamma_median=("gamma", "median"),
        option_theta_median=("theta", "median"),
        option_vega_median=("vega", "median"),
    ).reset_index()
    breadth = grouped["option_return_1_raw"].agg(
        breadth_up_1=lambda values: float((values > 0).mean()) if values.notna().any() else np.nan,
        breadth_down_1=lambda values: float((values < 0).mean()) if values.notna().any() else np.nan,
    ).reset_index()
    out = out.merge(breadth, on="minute", how="left", validate="one_to_one")
    out["relative_volume"] = out["option_volume"] / out["option_volume"].rolling(20, min_periods=5).median().replace(0, np.nan)
    return out


def _index_minute_bars(index_rows: pd.DataFrame, config: MarketCorpusConfig) -> pd.DataFrame:
    work = index_rows.copy()
    work["minute"] = work["timestamp"].dt.floor(config.bar_frequency)
    grouped = work.groupby(["symbol", "minute"], sort=True)
    bars = grouped.agg(
        open=("ltp", "first"),
        high=("ltp", "max"),
        low=("ltp", "min"),
        close=("ltp", "last"),
        index_volume=("volume", "max"),
    ).reset_index()
    return bars.sort_values(["symbol", "minute"], kind="stable").reset_index(drop=True)


def build_market_state_frame(frame: pd.DataFrame, config: MarketCorpusConfig | None = None) -> pd.DataFrame:
    cfg = config or MarketCorpusConfig()
    source = frame.copy()
    source["symbol"] = source["instrument_key"].map(_symbol_for_key)
    index_rows = source[source["symbol"].isin(set(cfg.symbols))].copy()
    option_rows = source[source["instrument_key"].map(_is_option_key)].copy()
    if index_rows.empty:
        raise ValueError("market_corpus_supported_index_rows_missing")
    if option_rows.empty:
        raise ValueError("market_corpus_option_rows_missing")
    bars = _index_minute_bars(index_rows, cfg)
    option_features = _option_minute_features(option_rows, cfg)
    if option_features.empty:
        raise ValueError("market_corpus_option_features_empty")
    states = bars.merge(option_features, on="minute", how="left", validate="many_to_one")
    states = states[states["option_instrument_count"].fillna(0) >= cfg.min_option_instruments_per_bar].copy()
    if states.empty:
        raise ValueError("market_corpus_option_support_below_minimum")
    states["session_date"] = states["minute"].dt.tz_convert("Asia/Kolkata").dt.date.astype(str)
    states = states.sort_values(["symbol", "minute"], kind="stable")
    by_symbol_session = states.groupby(["symbol", "session_date"], sort=False)
    states["index_return_1"] = by_symbol_session["close"].pct_change(1)
    states["index_return_3"] = by_symbol_session["close"].pct_change(3)
    states["index_return_5"] = by_symbol_session["close"].pct_change(5)
    states["realized_vol_5"] = by_symbol_session["index_return_1"].rolling(5, min_periods=3).std().reset_index(level=[0, 1], drop=True)
    states["realized_vol_15"] = by_symbol_session["index_return_1"].rolling(15, min_periods=5).std().reset_index(level=[0, 1], drop=True)
    previous_close = by_symbol_session["close"].shift(1)
    true_range = pd.concat(
        [
            states["high"] - states["low"],
            (states["high"] - previous_close).abs(),
            (states["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    states["atr"] = true_range.groupby([states["symbol"], states["session_date"]]).rolling(14, min_periods=5).mean().reset_index(level=[0, 1], drop=True)
    typical = (states["high"] + states["low"] + states["close"]) / 3.0
    proxy_volume = states["index_volume"].where(states["index_volume"] > 0, 1.0).fillna(1.0)
    cumulative_pv = (typical * proxy_volume).groupby([states["symbol"], states["session_date"]]).cumsum()
    cumulative_volume = proxy_volume.groupby([states["symbol"], states["session_date"]]).cumsum().replace(0, np.nan)
    states["vwap"] = cumulative_pv / cumulative_volume
    states["distance_from_vwap_atr"] = (states["close"] - states["vwap"]) / states["atr"].replace(0, np.nan)
    states["index_breadth_divergence"] = states["index_return_1"] - states["option_return_1"]
    local = states["minute"].dt.tz_convert("Asia/Kolkata")
    minutes = local.dt.hour * 60 + local.dt.minute
    states["minutes_since_open"] = (minutes - (9 * 60 + 15)).clip(lower=0)
    states["minutes_to_close"] = ((15 * 60 + 30) - minutes).clip(lower=0)
    angle = 2.0 * math.pi * states["minutes_since_open"] / 375.0
    states["time_sin"] = np.sin(angle)
    states["time_cos"] = np.cos(angle)
    return states.reset_index(drop=True)


def build_market_response_pretraining_dataset(
    frame: pd.DataFrame,
    config: MarketCorpusConfig | None = None,
) -> pd.DataFrame:
    cfg = config or MarketCorpusConfig()
    states = build_market_state_frame(frame, cfg)
    states = states.sort_values(["symbol", "minute"], kind="stable").reset_index(drop=True)
    groups = states.groupby(["symbol", "session_date"], sort=False)
    states["response_return"] = groups["close"].shift(-cfg.horizon_bars) / states["close"] - 1.0
    states["response_ts"] = groups["minute"].shift(-cfg.horizon_bars)
    threshold = float(cfg.min_move_bps) / 10_000.0
    rows: list[dict[str, Any]] = []
    feature_columns = [
        "spread_pct",
        "quote_age_sec",
        "relative_volume",
        "distance_from_vwap_atr",
        "breadth_up_1",
        "breadth_down_1",
        "index_breadth_divergence",
        "option_return_1",
        "option_return_3",
        "option_return_dispersion",
        "option_instrument_count",
        "option_iv_median",
        "option_abs_delta_median",
        "option_gamma_median",
        "option_theta_median",
        "option_vega_median",
        "index_return_1",
        "index_return_3",
        "index_return_5",
        "realized_vol_5",
        "realized_vol_15",
        "minutes_since_open",
        "minutes_to_close",
        "time_sin",
        "time_cos",
    ]
    for _, source in states.dropna(subset=["response_return", "response_ts"]).iterrows():
        decision_ms = int(pd.Timestamp(source["minute"]).timestamp() * 1000)
        response_ms = int(pd.Timestamp(source["response_ts"]).timestamp() * 1000)
        scale = max(float(source.get("realized_vol_15") or 0.0), threshold)
        for direction, sign, option_type in (("LONG", 1.0, "CE"), ("SHORT", -1.0, "PE")):
            directional_return = sign * float(source["response_return"])
            event_seed = f"{source['symbol']}|{decision_ms}|{direction}|{cfg.horizon_bars}"
            event_id = sha256(event_seed.encode("utf-8")).hexdigest()[:24]
            payload: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "event_id": event_id,
                "trade_key": event_id,
                "strategy_id": f"MARKET_RESPONSE_{direction}",
                "symbol": str(source["symbol"]),
                "option_type": option_type,
                "decision_ts_epoch_ms": decision_ms,
                "feature_cutoff_ts_epoch_ms": decision_ms,
                "outcome_ts_epoch_ms": response_ms,
                "session_date": str(source["session_date"]),
                "target": int(directional_return >= threshold),
                "stop_hit": int(directional_return <= -threshold),
                "exec_feasible": 0,
                "future_mfe_points": np.nan,
                "future_mae_points": np.nan,
                "future_net_r": directional_return / scale - float(cfg.friction_r),
                "friction_r": float(cfg.friction_r),
                **SAFETY_CONTRACT,
            }
            for column in feature_columns:
                payload[column] = source.get(column)
            rows.append(payload)
    if not rows:
        raise ValueError("market_response_pretraining_dataset_empty")
    dataset = pd.DataFrame(rows).sort_values(["decision_ts_epoch_ms", "event_id"], kind="stable").reset_index(drop=True)
    validate_candidate_dataset(dataset)
    return dataset


def market_corpus_summary(dataset: pd.DataFrame, audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "lane": MARKET_CORPUS_LANE,
        "dataset_rows": int(dataset.shape[0]),
        "sessions": int(dataset["session_date"].nunique()),
        "symbols": sorted(str(value) for value in dataset["symbol"].dropna().unique()),
        "strategies": {str(key): int(value) for key, value in dataset["strategy_id"].value_counts().to_dict().items()},
        "positive_rate": float(dataset["target"].mean()),
        "candidate_lineage_available": False,
        "candidate_edge_certification_allowed": False,
        "model_authority": "PRETRAINING_ONLY",
        "audit": audit,
        "required_features": list(PRETRAINING_REQUIRED_FEATURES),
        **SAFETY_CONTRACT,
    }


__all__ = [
    "MARKET_CORPUS_LANE",
    "PRETRAINING_REQUIRED_FEATURES",
    "MarketCorpusConfig",
    "audit_market_tick_corpus",
    "build_market_response_pretraining_dataset",
    "build_market_state_frame",
    "load_market_tick_corpus",
    "market_corpus_summary",
    "normalize_tick_frame",
    "validate_materialized_parquet",
]
