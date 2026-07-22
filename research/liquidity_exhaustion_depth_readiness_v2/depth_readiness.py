from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


REQUIRED_QUOTE_COLUMNS = ("ts", "token", "symbol", "ltp", "bid", "ask")


@dataclass(frozen=True)
class DepthReadinessContract:
    minimum_development_sessions: int = 60
    minimum_future_holdout_sessions: int = 20
    minimum_session_span_minutes: float = 300.0
    maximum_median_gap_seconds: float = 5.0
    maximum_p95_gap_seconds: float = 30.0
    maximum_crossed_market_rate: float = 0.001
    requires_bid_and_ask_size_or_structured_depth: bool = True

    def validate(self) -> None:
        if self.minimum_development_sessions <= 0:
            raise ValueError("minimum_development_sessions must be positive")
        if self.minimum_future_holdout_sessions <= 0:
            raise ValueError("minimum_future_holdout_sessions must be positive")
        if self.minimum_session_span_minutes <= 0:
            raise ValueError("minimum_session_span_minutes must be positive")
        if self.maximum_median_gap_seconds <= 0:
            raise ValueError("maximum_median_gap_seconds must be positive")
        if self.maximum_p95_gap_seconds < self.maximum_median_gap_seconds:
            raise ValueError("maximum_p95_gap_seconds cannot be below the median limit")
        if not 0 <= self.maximum_crossed_market_rate <= 1:
            raise ValueError("maximum_crossed_market_rate must be between zero and one")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_quote_timestamps(values: pd.Series) -> pd.Series:
    if values.empty:
        return pd.Series([], dtype="datetime64[ns, UTC]", index=values.index)

    numeric = pd.to_numeric(values, errors="coerce")
    numeric_share = float(numeric.notna().mean())
    if numeric_share == 1.0:
        magnitude = float(numeric.abs().median())
        if magnitude >= 1e17:
            unit = "ns"
        elif magnitude >= 1e14:
            unit = "us"
        elif magnitude >= 1e11:
            unit = "ms"
        else:
            unit = "s"
        parsed = pd.to_datetime(numeric, unit=unit, utc=True, errors="coerce")
    else:
        parsed = pd.to_datetime(values, utc=True, errors="coerce")

    if parsed.isna().any():
        raise ValueError("quote timestamps contain unparseable values")
    return pd.Series(parsed, index=values.index)


def detect_depth_capability(columns: Iterable[object], frame: pd.DataFrame | None = None) -> dict[str, Any]:
    names = [str(column) for column in columns]
    lowered = {name: name.lower() for name in names}
    size_tokens = ("qty", "quantity", "size")
    bid_size = sorted(
        name for name, lower in lowered.items() if "bid" in lower and any(token in lower for token in size_tokens)
    )
    ask_size = sorted(
        name for name, lower in lowered.items() if "ask" in lower and any(token in lower for token in size_tokens)
    )
    structured = sorted(
        name for name, lower in lowered.items() if "depth" in lower or "order_book" in lower or "orderbook" in lower
    )
    structured_non_null = False
    if frame is not None:
        for name in structured:
            if name in frame.columns and frame[name].notna().any():
                structured_non_null = True
                break
    usable = bool((bid_size and ask_size) or structured_non_null)
    return {
        "bid_size_columns": bid_size,
        "ask_size_columns": ask_size,
        "structured_depth_columns": structured,
        "structured_depth_non_null": structured_non_null,
        "supports_imbalance_or_replenishment": usable,
    }


def audit_quote_frame(
    frame: pd.DataFrame,
    *,
    source: str,
    date_key: str,
) -> dict[str, Any]:
    missing = [column for column in REQUIRED_QUOTE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"{source} missing quote columns {missing}")
    if frame.empty:
        raise ValueError(f"{source} is empty")

    parsed_ts = parse_quote_timestamps(frame["ts"])
    source_order_ns = parsed_ts.astype("int64").to_numpy()
    out_of_order_count = int(np.sum(np.diff(source_order_ns) < 0))
    duplicate_ts_count = int(parsed_ts.duplicated().sum())
    ordered_ts = parsed_ts.sort_values(kind="mergesort")
    gaps = ordered_ts.diff().dt.total_seconds().dropna()

    ltp = pd.to_numeric(frame["ltp"], errors="coerce")
    bid = pd.to_numeric(frame["bid"], errors="coerce")
    ask = pd.to_numeric(frame["ask"], errors="coerce")
    missing_price_count = int((ltp.isna() | bid.isna() | ask.isna()).sum())
    if missing_price_count:
        raise ValueError(f"{source} contains missing/non-numeric top-of-book prices")
    if (ltp <= 0).any() or (bid < 0).any() or (ask < 0).any():
        raise ValueError(f"{source} contains invalid nonpositive prices")

    active = (bid > 0) & (ask > 0)
    crossed = active & (bid > ask)
    locked = active & (bid == ask)
    midpoint = (bid + ask) / 2.0
    spread_bps = ((ask - bid) / midpoint * 10000.0).where(active & ~crossed)

    symbols = sorted({str(value).strip() for value in frame["symbol"].dropna() if str(value).strip()})
    tokens = sorted({str(value).strip() for value in frame["token"].dropna() if str(value).strip()})
    if not symbols or not tokens:
        raise ValueError(f"{source} contains no symbol/token authority")

    capability = detect_depth_capability(frame.columns, frame)
    start = ordered_ts.iloc[0]
    end = ordered_ts.iloc[-1]
    duration_minutes = float((end - start).total_seconds() / 60.0)
    row_count = int(len(frame))

    return {
        "source": source,
        "date_key": date_key,
        "row_count": row_count,
        "column_count": int(len(frame.columns)),
        "columns": sorted(str(column) for column in frame.columns),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "token_count": len(tokens),
        "tokens": tokens,
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "duration_minutes": duration_minutes,
        "duplicate_timestamp_count": duplicate_ts_count,
        "out_of_order_transition_count": out_of_order_count,
        "median_gap_seconds": float(gaps.median()) if not gaps.empty else None,
        "p95_gap_seconds": float(gaps.quantile(0.95)) if not gaps.empty else None,
        "maximum_gap_seconds": float(gaps.max()) if not gaps.empty else None,
        "active_top_of_book_rows": int(active.sum()),
        "crossed_market_count": int(crossed.sum()),
        "crossed_market_rate": float(crossed.sum() / max(int(active.sum()), 1)),
        "locked_market_count": int(locked.sum()),
        "spread_bps_median": float(spread_bps.median()) if spread_bps.notna().any() else None,
        "spread_bps_p95": float(spread_bps.quantile(0.95)) if spread_bps.notna().any() else None,
        "depth_capability": capability,
    }


def summarize_depth_readiness(
    file_audits: list[dict[str, Any]],
    *,
    candle_dates: set[str],
    contract: DepthReadinessContract = DepthReadinessContract(),
) -> dict[str, Any]:
    contract.validate()
    if not file_audits:
        return {
            "classification": "DEPTH_DATA_NOT_READY_FOR_EXHAUSTION_DISCOVERY",
            "blockers": ["NO_QUOTE_DEPTH_FILES"],
            "contract": contract.as_dict(),
        }

    dates = sorted({str(item["date_key"]) for item in file_audits})
    date_groups: dict[str, list[dict[str, Any]]] = {}
    for date_key in dates:
        date_groups[date_key] = [item for item in file_audits if item["date_key"] == date_key]

    session_spans: dict[str, float] = {}
    for date_key, items in date_groups.items():
        starts = [pd.Timestamp(item["start_utc"]) for item in items]
        ends = [pd.Timestamp(item["end_utc"]) for item in items]
        session_spans[date_key] = float((max(ends) - min(starts)).total_seconds() / 60.0)

    median_gaps = [item["median_gap_seconds"] for item in file_audits if item["median_gap_seconds"] is not None]
    p95_gaps = [item["p95_gap_seconds"] for item in file_audits if item["p95_gap_seconds"] is not None]
    crossed_rows = sum(int(item["crossed_market_count"]) for item in file_audits)
    active_rows = sum(int(item["active_top_of_book_rows"]) for item in file_audits)
    crossed_rate = float(crossed_rows / max(active_rows, 1))
    depth_ready_files = sum(
        bool(item["depth_capability"]["supports_imbalance_or_replenishment"])
        for item in file_audits
    )

    blockers: list[str] = []
    if len(dates) < contract.minimum_development_sessions:
        blockers.append(
            f"DEVELOPMENT_SESSION_COUNT_BELOW_MINIMUM:{len(dates)}<{contract.minimum_development_sessions}"
        )
    short_sessions = sorted(
        date_key
        for date_key, span in session_spans.items()
        if span < contract.minimum_session_span_minutes
    )
    if short_sessions:
        blockers.append(f"SESSION_SPAN_BELOW_MINIMUM:{','.join(short_sessions)}")
    aggregate_median_gap = float(np.median(median_gaps)) if median_gaps else None
    aggregate_p95_gap = float(np.quantile(p95_gaps, 0.95)) if p95_gaps else None
    if aggregate_median_gap is None or aggregate_median_gap > contract.maximum_median_gap_seconds:
        blockers.append("MEDIAN_QUOTE_GAP_TOO_LARGE_OR_MISSING")
    if aggregate_p95_gap is None or aggregate_p95_gap > contract.maximum_p95_gap_seconds:
        blockers.append("P95_QUOTE_GAP_TOO_LARGE_OR_MISSING")
    if crossed_rate > contract.maximum_crossed_market_rate:
        blockers.append("CROSSED_MARKET_RATE_TOO_HIGH")
    if contract.requires_bid_and_ask_size_or_structured_depth and depth_ready_files != len(file_audits):
        blockers.append(
            f"BID_ASK_SIZE_OR_STRUCTURED_DEPTH_MISSING:{depth_ready_files}/{len(file_audits)}"
        )
    missing_candle_dates = sorted(set(dates) - set(candle_dates))
    if missing_candle_dates:
        blockers.append(f"QUOTE_DATES_WITHOUT_CANDLE_AUTHORITY:{','.join(missing_candle_dates)}")

    unique_symbols = sorted({symbol for item in file_audits for symbol in item["symbols"]})
    unique_tokens = sorted({token for item in file_audits for token in item["tokens"]})
    classification = (
        "DEPTH_DATA_READY_FOR_EXHAUSTION_DISCOVERY"
        if not blockers
        else "DEPTH_DATA_NOT_READY_FOR_EXHAUSTION_DISCOVERY"
    )
    return {
        "classification": classification,
        "blockers": blockers,
        "contract": contract.as_dict(),
        "quote_depth_files": len(file_audits),
        "quote_depth_sessions": len(dates),
        "quote_depth_dates": dates,
        "session_spans_minutes": session_spans,
        "aggregate_median_gap_seconds": aggregate_median_gap,
        "aggregate_p95_gap_seconds": aggregate_p95_gap,
        "crossed_market_rate": crossed_rate,
        "depth_capable_file_count": depth_ready_files,
        "unique_symbol_count": len(unique_symbols),
        "unique_token_count": len(unique_tokens),
        "quote_dates_with_candle_authority": sorted(set(dates).intersection(candle_dates)),
        "future_holdout_sessions_required": contract.minimum_future_holdout_sessions,
        "strategy_created": False,
        "edge_claim_allowed": False,
        "execution_allowed": False,
    }
