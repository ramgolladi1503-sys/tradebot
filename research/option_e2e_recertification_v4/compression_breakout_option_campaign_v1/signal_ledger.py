from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any

import pandas as pd

from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeClassifier
from strategies.movement.compression_breakout import (
    STRATEGY_ID,
    generate_compression_breakout_candidates,
)

from .splits import build_chronological_split_manifest


_TIMESTAMP_COLUMNS = ("timestamp", "date", "ts")
_SYMBOL_COLUMNS = ("symbol", "instrument", "underlying")
_REQUIRED_PRICE_COLUMNS = ("open", "high", "low", "close")


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _first_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for name in candidates:
        if name in frame.columns:
            return name
    return None


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


@dataclass(frozen=True)
class CompressionLedgerConfig:
    timezone: str = "Asia/Kolkata"
    timestamp_semantics: str = "START"
    bar_interval_minutes: int = 1
    compression_window_bars: int = 15
    orb_bars: int = 15
    atr_short_bars: int = 5
    atr_long_bars: int = 30
    volume_z_window_bars: int = 60
    allow_typical_price_vwap_proxy: bool = True
    adapter_version: str = "compression_breakout_causal_context_v1"

    def __post_init__(self) -> None:
        semantics = str(self.timestamp_semantics).strip().upper()
        if semantics not in {"START", "END"}:
            raise ValueError("timestamp_semantics_must_be_START_or_END")
        object.__setattr__(self, "timestamp_semantics", semantics)
        for name in (
            "bar_interval_minutes",
            "compression_window_bars",
            "orb_bars",
            "atr_short_bars",
            "atr_long_bars",
            "volume_z_window_bars",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name}_must_be_positive")
        if self.atr_short_bars >= self.atr_long_bars:
            raise ValueError("atr_short_must_be_less_than_atr_long")


@dataclass(frozen=True)
class CompressionSignalLedgerResult:
    signals: pd.DataFrame
    rejections: pd.DataFrame
    split_manifest: dict[str, object]
    summary: dict[str, object]
    normalized_sessions: tuple[str, ...] = field(default_factory=tuple)


def _normalize_underlying_bars(
    frame: pd.DataFrame,
    config: CompressionLedgerConfig,
) -> pd.DataFrame:
    timestamp_column = _first_column(frame, _TIMESTAMP_COLUMNS)
    symbol_column = _first_column(frame, _SYMBOL_COLUMNS)
    if timestamp_column is None:
        raise ValueError("missing_underlying_timestamp_column")
    if symbol_column is None:
        raise ValueError("missing_underlying_symbol_column")

    missing = [name for name in _REQUIRED_PRICE_COLUMNS if name not in frame.columns]
    if missing:
        raise ValueError(f"missing_underlying_price_columns:{','.join(missing)}")

    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data[timestamp_column], errors="coerce")
    if data["timestamp"].isna().any():
        raise ValueError("invalid_underlying_timestamp_rows")
    if getattr(data["timestamp"].dt, "tz", None) is None:
        data["timestamp"] = data["timestamp"].dt.tz_localize(config.timezone)
    else:
        data["timestamp"] = data["timestamp"].dt.tz_convert(config.timezone)

    data["symbol"] = data[symbol_column].astype(str).str.strip().str.upper()
    if (data["symbol"] == "").any():
        raise ValueError("empty_underlying_symbol_rows")

    for name in (*_REQUIRED_PRICE_COLUMNS, "volume"):
        if name not in data.columns:
            if name == "volume":
                data[name] = 0.0
            else:
                raise ValueError(f"missing_underlying_column:{name}")
        data[name] = pd.to_numeric(data[name], errors="coerce")
        if data[name].isna().any():
            raise ValueError(f"invalid_underlying_numeric_rows:{name}")
    if (data[list(_REQUIRED_PRICE_COLUMNS)] <= 0).any().any():
        raise ValueError("nonpositive_underlying_price_rows")
    if (data["volume"] < 0).any():
        raise ValueError("negative_underlying_volume_rows")

    invalid_geometry = (
        (data["high"] < data[["open", "close", "low"]].max(axis=1))
        | (data["low"] > data[["open", "close", "high"]].min(axis=1))
        | (data["low"] > data["high"])
    )
    if invalid_geometry.any():
        raise ValueError("invalid_underlying_ohlc_geometry")

    data["session_date"] = data["timestamp"].dt.date.astype(str)
    duplicate = data.duplicated(["symbol", "timestamp"], keep=False)
    if duplicate.any():
        raise ValueError("duplicate_underlying_symbol_timestamp_rows")

    return data.sort_values(
        ["symbol", "session_date", "timestamp"],
        kind="mergesort",
    ).reset_index(drop=True)


def _prepare_session(
    session: pd.DataFrame,
    config: CompressionLedgerConfig,
) -> tuple[pd.DataFrame, str]:
    rows = session.copy().reset_index(drop=True)
    typical = (rows["high"] + rows["low"] + rows["close"]) / 3.0
    positive_volume = rows["volume"].where(rows["volume"] > 0.0, 0.0)
    cumulative_volume = positive_volume.cumsum()
    weighted = (typical * positive_volume).cumsum()
    if float(cumulative_volume.iloc[-1]) > 0.0:
        rows["vwap"] = weighted.div(cumulative_volume.where(cumulative_volume > 0.0))
        rows["vwap"] = rows["vwap"].fillna(typical.expanding().mean())
        vwap_authority = "SESSION_VOLUME_WEIGHTED"
    else:
        if not config.allow_typical_price_vwap_proxy:
            raise ValueError("session_volume_missing_for_vwap")
        rows["vwap"] = typical.expanding().mean()
        vwap_authority = "SESSION_TYPICAL_PRICE_PROXY"

    previous_close = rows["close"].shift(1)
    true_range = pd.concat(
        [
            (rows["high"] - rows["low"]).abs(),
            (rows["high"] - previous_close).abs(),
            (rows["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    rows["atr_short"] = true_range.rolling(
        config.atr_short_bars,
        min_periods=config.atr_short_bars,
    ).mean()
    rows["atr_long"] = true_range.rolling(
        config.atr_long_bars,
        min_periods=config.atr_long_bars,
    ).mean()

    volume_mean = rows["volume"].rolling(
        config.volume_z_window_bars,
        min_periods=min(10, config.volume_z_window_bars),
    ).mean()
    volume_std = rows["volume"].rolling(
        config.volume_z_window_bars,
        min_periods=min(10, config.volume_z_window_bars),
    ).std().replace(0.0, pd.NA)
    rows["volume_z"] = ((rows["volume"] - volume_mean) / volume_std).fillna(0.0)

    if len(rows) >= config.orb_bars:
        rows.attrs["orb_high"] = float(rows.iloc[: config.orb_bars]["high"].max())
        rows.attrs["orb_low"] = float(rows.iloc[: config.orb_bars]["low"].min())
    else:
        rows.attrs["orb_high"] = None
        rows.attrs["orb_low"] = None
    rows.attrs["vwap_authority"] = vwap_authority
    return rows, vwap_authority


def _feature_cutoff(
    timestamp: pd.Timestamp,
    config: CompressionLedgerConfig,
) -> pd.Timestamp:
    if config.timestamp_semantics == "START":
        return timestamp + pd.Timedelta(minutes=config.bar_interval_minutes)
    return timestamp


def _signal_identity(payload: dict[str, object]) -> str:
    identity = {
        "strategy_id": payload["strategy_id"],
        "underlying": payload["underlying"],
        "signal_ts": payload["signal_ts"],
        "feature_cutoff_ts": payload["feature_cutoff_ts"],
        "direction": payload["direction"],
        "source_dataset_hash": payload["source_dataset_hash"],
        "params_hash": payload["params_hash"],
        "adapter_version": payload["adapter_version"],
    }
    return _canonical_hash(identity)[:24]


def _partition_lookup(split_manifest: dict[str, object]) -> dict[str, str]:
    partitions = split_manifest["partitions"]
    if not isinstance(partitions, dict):
        raise ValueError("invalid_split_manifest_partitions")
    lookup: dict[str, str] = {}
    for partition, dates in partitions.items():
        for date in list(dates):
            if str(date) in lookup:
                raise ValueError("split_manifest_overlap")
            lookup[str(date)] = str(partition)
    return lookup


def build_compression_signal_ledger(
    underlying_bars: pd.DataFrame,
    *,
    config: CompressionLedgerConfig | None = None,
    source_dataset_hash: str = "UNBOUND_SOURCE_HASH",
) -> CompressionSignalLedgerResult:
    cfg = config or CompressionLedgerConfig()
    data = _normalize_underlying_bars(underlying_bars, cfg)
    sessions = tuple(sorted(data["session_date"].unique().tolist()))
    split_manifest = build_chronological_split_manifest(sessions)
    partition_by_date = _partition_lookup(split_manifest)

    signals: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    classifier = MovementRegimeClassifier()
    warmup = max(cfg.atr_long_bars, cfg.compression_window_bars, cfg.orb_bars)

    for (symbol, session_date), raw_session in data.groupby(
        ["symbol", "session_date"], sort=True, observed=True
    ):
        try:
            session, vwap_authority = _prepare_session(raw_session, cfg)
        except ValueError as exc:
            rejections.append(
                {
                    "symbol": symbol,
                    "session_date": session_date,
                    "reason": str(exc),
                    "source_row_index": None,
                }
            )
            continue

        if len(session) <= warmup:
            rejections.append(
                {
                    "symbol": symbol,
                    "session_date": session_date,
                    "reason": "insufficient_session_warmup",
                    "source_row_index": None,
                }
            )
            continue

        orb_high = session.attrs.get("orb_high")
        orb_low = session.attrs.get("orb_low")
        for index in range(warmup, len(session)):
            current = session.iloc[index]
            pre = session.iloc[index - cfg.compression_window_bars : index]
            prior_atr_short = _finite(session.iloc[index - 1]["atr_short"])
            prior_atr_long = _finite(session.iloc[index - 1]["atr_long"])
            if prior_atr_short is None or prior_atr_long is None:
                rejections.append(
                    {
                        "symbol": symbol,
                        "session_date": session_date,
                        "reason": "atr_warmup_incomplete",
                        "source_row_index": int(index),
                    }
                )
                continue

            prior_close = float(pre.iloc[-1]["close"])
            resistance = float(pre["high"].max())
            support = float(pre["low"].min())
            range_width_pct = (resistance - support) / max(abs(prior_close), 1e-12)
            bar_ts = pd.Timestamp(current["timestamp"])
            cutoff = _feature_cutoff(bar_ts, cfg)
            history = session.iloc[: index + 1][
                ["timestamp", "open", "high", "low", "close", "volume"]
            ].tail(cfg.atr_long_bars)

            context = StrategyContext(
                symbol=str(symbol),
                ts_epoch=float(cutoff.timestamp()),
                spot_ltp=float(current["close"]),
                open_price=float(current["open"]),
                vwap=float(current["vwap"]),
                vwap_slope=float(
                    session["vwap"].iloc[index]
                    - session["vwap"].iloc[max(0, index - 5)]
                ),
                day_high=float(session.iloc[:index]["high"].max()),
                day_low=float(session.iloc[:index]["low"].min()),
                orb_high=_finite(orb_high),
                orb_low=_finite(orb_low),
                previous_completed_close=prior_close,
                nearest_support=support,
                nearest_resistance=resistance,
                completed_bar_history=tuple(
                    {
                        **row,
                        "timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
                    }
                    for row in history.to_dict("records")
                ),
                atr=prior_atr_short,
                atr_short=prior_atr_short,
                atr_long=prior_atr_long,
                range_width_pct=float(range_width_pct),
                volume_z=float(current["volume_z"]),
                quote_source="HISTORICAL_UNDERLYING_OHLCV_NO_OPTION_QUOTE",
                fallback_used=False,
                time_of_day=cutoff.strftime("%H:%M"),
                minutes_since_open=int(index),
                minutes_to_close=max(int(len(session) - index - 1), 0),
                expiry_context=False,
                metadata={
                    "adapter_version": cfg.adapter_version,
                    "timestamp_semantics": cfg.timestamp_semantics,
                    "source_bar_start": bar_ts.isoformat(),
                    "feature_cutoff_ts": cutoff.isoformat(),
                    "pre_breakout_window_bars": cfg.compression_window_bars,
                    "vwap_authority": vwap_authority,
                    "source_dataset_hash": source_dataset_hash,
                    "option_quote_fields_used": False,
                },
            )
            regime = classifier.classify(context)
            candidates = generate_compression_breakout_candidates(context, regime)
            if not candidates:
                rejections.append(
                    {
                        "symbol": symbol,
                        "session_date": session_date,
                        "reason": "no_candidate_from_production_generator",
                        "source_row_index": int(index),
                        "signal_ts": bar_ts.isoformat(),
                    }
                )
                continue

            candidate_rows: list[dict[str, object]] = []
            for candidate in candidates:
                direction = "BULLISH" if candidate.direction == "BUY_CALL" else "BEARISH"
                params_hash = str(candidate.lineage.get("params_hash") or "")
                payload: dict[str, object] = {
                    "strategy_id": STRATEGY_ID,
                    "strategy_version": str(candidate.lineage.get("strategy_version") or "v1"),
                    "underlying": str(symbol),
                    "underlying_price": float(current["close"]),
                    "direction": direction,
                    "signal_ts": bar_ts.isoformat(),
                    "feature_cutoff_ts": cutoff.isoformat(),
                    "earliest_entry_ts": cutoff.isoformat(),
                    "session_date": str(session_date),
                    "sample_partition": partition_by_date[str(session_date)],
                    "raw_strategy_score": float(candidate.raw_score),
                    "confidence_score": float(candidate.confidence_score),
                    "execution_quality_score": None,
                    "rank_score": float(candidate.raw_score),
                    "rank_scope": "STRATEGY_ONLY_NO_EXECUTION_QUALITY",
                    "selected_for_execution": True,
                    "candidate_status": candidate.status,
                    "candidate_direction": candidate.direction,
                    "params_hash": params_hash,
                    "params_used": candidate.lineage.get("params_used") or {},
                    "source_dataset_hash": source_dataset_hash,
                    "adapter_version": cfg.adapter_version,
                    "timestamp_semantics": cfg.timestamp_semantics,
                    "vwap_authority": vwap_authority,
                    "range_width_pct": float(range_width_pct),
                    "atr_short": float(prior_atr_short),
                    "atr_long": float(prior_atr_long),
                    "breakout_level": candidate.evidence.get("breakout_level"),
                    "breakout_distance_pct": candidate.evidence.get("breakout_distance_pct"),
                    "research_only": True,
                    "is_order_action": False,
                    "broker_api_called": False,
                    "allowed_for_live_execution": False,
                }
                payload["signal_id"] = _signal_identity(payload)
                candidate_rows.append(payload)

            candidate_rows.sort(
                key=lambda row: (
                    -float(row["rank_score"]),
                    str(row["direction"]),
                    str(row["signal_id"]),
                )
            )
            for rank, row in enumerate(candidate_rows, start=1):
                row["rank_global"] = rank
                row["selected_for_execution"] = rank == 1
                signals.append(row)

    signal_frame = pd.DataFrame(signals)
    if not signal_frame.empty:
        signal_frame = signal_frame.sort_values(
            ["signal_ts", "underlying", "rank_global", "signal_id"],
            kind="mergesort",
        ).reset_index(drop=True)
        if signal_frame["signal_id"].duplicated().any():
            raise ValueError("duplicate_signal_identity")

    rejection_frame = pd.DataFrame(rejections)
    proxy_count = (
        int((signal_frame["vwap_authority"] != "SESSION_VOLUME_WEIGHTED").sum())
        if not signal_frame.empty
        else 0
    )
    directions = (
        signal_frame["direction"].value_counts().sort_index().to_dict()
        if not signal_frame.empty
        else {}
    )
    summary: dict[str, object] = {
        "schema_version": "compression_breakout_signal_ledger_summary_v1",
        "strategy_id": STRATEGY_ID,
        "adapter_version": cfg.adapter_version,
        "source_dataset_hash": source_dataset_hash,
        "session_count": len(sessions),
        "context_rows_evaluated": int(
            sum(
                max(len(group) - warmup, 0)
                for _, group in data.groupby(
                    ["symbol", "session_date"], sort=True, observed=True
                )
            )
        ),
        "signal_count": int(len(signal_frame)),
        "selected_signal_count": (
            int(signal_frame["selected_for_execution"].sum())
            if not signal_frame.empty
            else 0
        ),
        "direction_counts": {str(key): int(value) for key, value in directions.items()},
        "rejection_count": int(len(rejection_frame)),
        "vwap_proxy_signal_count": proxy_count,
        "split_manifest_hash": split_manifest["manifest_hash"],
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
        "option_prices_read": False,
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    summary["ledger_semantic_hash"] = _canonical_hash(signal_frame.to_dict("records"))
    return CompressionSignalLedgerResult(
        signals=signal_frame,
        rejections=rejection_frame,
        split_manifest=split_manifest,
        summary=summary,
        normalized_sessions=sessions,
    )
