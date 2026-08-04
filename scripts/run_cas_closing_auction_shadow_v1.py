#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

IST = "Asia/Kolkata"


@dataclass(frozen=True)
class CasWindowContract:
    normal_start: str = "14:45:00"
    normal_end: str = "15:15:00"
    cas_reference_end: str = "15:20:00"
    cas_order_end: str = "15:30:00"
    cas_match_end: str = "15:35:00"
    derivative_end: str = "15:40:00"
    stale_seconds: float = 5.0
    max_top3_share: float = 0.65
    minimum_breadth_count: int = 30


def _read_parquets(root: Path) -> pd.DataFrame:
    files = sorted(root.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no_parquet_files_under={root}")
    frames = [pd.read_parquet(path) for path in files]
    frame = pd.concat(frames, ignore_index=True, sort=False)
    return frame


def _timestamp_column(frame: pd.DataFrame) -> str:
    for name in (
        "timestamp",
        "exchange_timestamp",
        "source_timestamp",
        "tick_timestamp",
        "ts",
    ):
        if name in frame.columns:
            return name
    raise ValueError("missing_timestamp_column")


def _price_column(frame: pd.DataFrame) -> str:
    for name in ("ltp", "last_price", "price", "close"):
        if name in frame.columns:
            return name
    raise ValueError("missing_price_column")


def _symbol_column(frame: pd.DataFrame) -> str:
    for name in ("trading_symbol", "tradingsymbol", "symbol", "instrument_name"):
        if name in frame.columns:
            return name
    raise ValueError("missing_symbol_column")


def normalize_ticks(frame: pd.DataFrame) -> pd.DataFrame:
    ts_col = _timestamp_column(frame)
    px_col = _price_column(frame)
    symbol_col = _symbol_column(frame)
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out[ts_col], utc=True, errors="coerce").dt.tz_convert(IST)
    out["price"] = pd.to_numeric(out[px_col], errors="coerce")
    out["symbol"] = out[symbol_col].astype(str)
    out = out.dropna(subset=["timestamp", "price"])
    out = out[out.price > 0].sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    return out


def classify_phase(timestamp: pd.Timestamp, contract: CasWindowContract) -> str:
    value = timestamp.strftime("%H:%M:%S")
    if contract.normal_start <= value < contract.normal_end:
        return "NORMAL_LATE_SESSION"
    if contract.normal_end <= value < contract.cas_reference_end:
        return "CAS_REFERENCE_TRANSITION"
    if contract.cas_reference_end <= value < contract.cas_order_end:
        return "CAS_ORDER_DISCOVERY"
    if contract.cas_order_end <= value < contract.cas_match_end:
        return "CAS_MATCHING"
    if contract.cas_match_end <= value <= contract.derivative_end:
        return "DERIVATIVE_CONVERGENCE"
    return "OUTSIDE_CAS_STUDY"


def resample_last(frame: pd.DataFrame, frequency: str = "1min") -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for symbol, group in frame.groupby("symbol", sort=False):
        series = (
            group.set_index("timestamp")["price"]
            .resample(frequency)
            .last()
            .dropna()
            .rename("price")
            .to_frame()
            .reset_index()
        )
        series["symbol"] = symbol
        rows.append(series)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _pick_symbol(frame: pd.DataFrame, tokens: Iterable[str]) -> str | None:
    candidates = frame.symbol.drop_duplicates().tolist()
    upper = [(symbol, symbol.upper()) for symbol in candidates]
    for token in tokens:
        for symbol, normalized in upper:
            if token in normalized:
                return symbol
    return None


def build_index_timeline(frame: pd.DataFrame, contract: CasWindowContract) -> pd.DataFrame:
    symbol = _pick_symbol(frame, ("NIFTY 50", "NIFTY50", "NIFTY"))
    if symbol is None:
        raise ValueError("nifty_symbol_not_found")
    index = frame[frame.symbol == symbol].copy()
    index = resample_last(index)
    index["phase"] = index.timestamp.map(lambda value: classify_phase(value, contract))
    index = index[index.phase != "OUTSIDE_CAS_STUDY"].copy()
    index["return_from_1515_bps"] = np.nan
    pre = index[index.timestamp.dt.strftime("%H:%M:%S") < contract.normal_end]
    if not pre.empty:
        anchor = float(pre.iloc[-1].price)
        index["return_from_1515_bps"] = (index.price / anchor - 1.0) * 10000.0
    return index


def summarize_phases(index: pd.DataFrame) -> list[dict]:
    records: list[dict] = []
    for phase, group in index.groupby("phase", sort=False):
        group = group.sort_values("timestamp")
        records.append(
            {
                "phase": phase,
                "start": group.timestamp.iloc[0].isoformat(),
                "end": group.timestamp.iloc[-1].isoformat(),
                "open": float(group.price.iloc[0]),
                "close": float(group.price.iloc[-1]),
                "move_points": float(group.price.iloc[-1] - group.price.iloc[0]),
                "move_bps": float((group.price.iloc[-1] / group.price.iloc[0] - 1.0) * 10000.0),
                "high": float(group.price.max()),
                "low": float(group.price.min()),
                "observations": int(len(group)),
            }
        )
    return records


def constituent_breadth(bars: pd.DataFrame, contract: CasWindowContract) -> dict:
    required = {"timestamp", "symbol", "close"}
    if not required.issubset(bars.columns):
        return {"available": False, "reason": "constituent_bar_schema_missing"}
    frame = bars.copy()
    frame["timestamp"] = pd.to_datetime(frame.timestamp, utc=True, errors="coerce").dt.tz_convert(IST)
    frame["close"] = pd.to_numeric(frame.close, errors="coerce")
    frame = frame.dropna(subset=["timestamp", "close", "symbol"])
    before = frame[frame.timestamp.dt.strftime("%H:%M:%S") <= contract.normal_end]
    after = frame[frame.timestamp.dt.strftime("%H:%M:%S") <= contract.cas_match_end]
    if before.empty or after.empty:
        return {"available": False, "reason": "insufficient_cas_constituent_coverage"}
    start = before.sort_values("timestamp").groupby("symbol").tail(1).set_index("symbol").close
    end = after.sort_values("timestamp").groupby("symbol").tail(1).set_index("symbol").close
    joined = pd.concat([start.rename("start"), end.rename("end")], axis=1).dropna()
    joined = joined[(joined.start > 0) & (joined.end > 0)]
    if joined.empty:
        return {"available": False, "reason": "no_joined_constituents"}
    joined["return"] = joined.end / joined.start - 1.0
    absolute = joined["return"].abs().sort_values(ascending=False)
    total_abs = float(absolute.sum())
    top3_share = float(absolute.head(3).sum() / total_abs) if total_abs > 0 else 0.0
    positive = int((joined["return"] > 0).sum())
    negative = int((joined["return"] < 0).sum())
    return {
        "available": True,
        "constituent_count": int(len(joined)),
        "positive_count": positive,
        "negative_count": negative,
        "positive_fraction": float(positive / len(joined)),
        "median_return_bps": float(joined["return"].median() * 10000.0),
        "top3_absolute_move_share": top3_share,
        "broad_move": bool(
            len(joined) >= contract.minimum_breadth_count
            and top3_share <= contract.max_top3_share
        ),
    }


def run(tick_root: Path, constituent_file: Path | None, output_dir: Path) -> dict:
    contract = CasWindowContract()
    raw = _read_parquets(tick_root)
    normalized = normalize_ticks(raw)
    index = build_index_timeline(normalized, contract)
    if index.empty:
        raise ValueError("no_nifty_rows_in_cas_window")

    breadth = {"available": False, "reason": "constituent_file_not_supplied"}
    if constituent_file is not None:
        breadth = constituent_breadth(pd.read_parquet(constituent_file), contract)

    phase_summary = summarize_phases(index)
    convergence = index[index.phase == "DERIVATIVE_CONVERGENCE"]
    coverage_end = index.timestamp.max()
    complete_through_derivative_close = coverage_end.strftime("%H:%M:%S") >= contract.derivative_end

    output_dir.mkdir(parents=True, exist_ok=True)
    index.to_csv(output_dir / "nifty_cas_timeline.csv", index=False)
    report = {
        "study_id": "CAS_CLOSING_AUCTION_SHADOW_V1",
        "contract": asdict(contract),
        "coverage": {
            "first_timestamp": index.timestamp.min().isoformat(),
            "last_timestamp": coverage_end.isoformat(),
            "complete_through_1540": complete_through_derivative_close,
            "derivative_convergence_observations": int(len(convergence)),
        },
        "phase_summary": phase_summary,
        "constituent_breadth": breadth,
        "claim_boundary": {
            "research_only": True,
            "shadow_only": True,
            "strategy_integration": False,
            "broker_api_called": False,
            "order_action": False,
            "two_sessions_can_establish_edge": False,
            "indicative_close_available_in_upstox_archive": False,
        },
        "verdict": "CAS_STRUCTURE_OBSERVED_NOT_EDGE_VALIDATED",
    }
    (output_dir / "cas_shadow_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tick-root", type=Path, required=True)
    parser.add_argument("--constituent-file", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.tick_root, args.constituent_file, args.output_dir)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
