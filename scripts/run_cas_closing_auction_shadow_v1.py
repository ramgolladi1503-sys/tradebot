#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

IST = "Asia/Kolkata"
EXACT_NIFTY_INDEX_IDENTITIES = (
    "NSE_INDEX|Nifty 50",
    "Nifty 50",
    "NIFTY 50",
)


@dataclass(frozen=True)
class CasWindowContract:
    normal_start: str = "14:45:00"
    normal_end: str = "15:15:00"
    cas_reference_end: str = "15:20:00"
    cas_order_end: str = "15:30:00"
    cas_match_end: str = "15:35:00"
    derivative_end: str = "15:40:00"
    max_top3_share: float = 0.65
    minimum_breadth_count: int = 30


def _parquet_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.parquet"))


def _read_parquets(root: Path) -> pd.DataFrame:
    files = _parquet_files(root)
    if not files:
        raise FileNotFoundError(f"no_parquet_files_under={root}")
    return pd.concat(
        [pd.read_parquet(path) for path in files],
        ignore_index=True,
        sort=False,
    )


def _timestamp_column(frame: pd.DataFrame) -> str:
    for name in (
        "receive_wall_ts_utc",
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
    for name in (
        "instrument_key",
        "trading_symbol",
        "tradingsymbol",
        "symbol",
        "instrument_name",
    ):
        if name in frame.columns:
            return name
    raise ValueError("missing_symbol_column")


def _parse_timestamp(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    numeric_fraction = float(numeric.notna().mean()) if len(series) else 0.0
    if numeric_fraction >= 0.95:
        finite = numeric.dropna().abs()
        if finite.empty:
            parsed = pd.to_datetime(series, utc=True, errors="coerce")
        else:
            magnitude = float(finite.median())
            if magnitude < 1e11:
                unit = "s"
            elif magnitude < 1e14:
                unit = "ms"
            elif magnitude < 1e17:
                unit = "us"
            else:
                unit = "ns"
            parsed = pd.to_datetime(numeric, unit=unit, utc=True, errors="coerce")
    else:
        parsed = pd.to_datetime(series, utc=True, errors="coerce")
    return parsed.dt.tz_convert(IST)


def normalize_ticks(frame: pd.DataFrame) -> pd.DataFrame:
    ts_col = _timestamp_column(frame)
    px_col = _price_column(frame)
    symbol_col = _symbol_column(frame)
    out = pd.DataFrame(
        {
            "timestamp": _parse_timestamp(frame[ts_col]),
            "price": pd.to_numeric(frame[px_col], errors="coerce"),
            "symbol": frame[symbol_col].astype(str),
        }
    )
    out = out.dropna(subset=["timestamp", "price"])
    out = out[out.price > 0]
    return out.sort_values(["symbol", "timestamp"]).reset_index(drop=True)


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


def select_exact_nifty_index_symbol(frame: pd.DataFrame) -> str:
    candidates = set(frame.symbol.dropna().astype(str).unique())
    for exact in EXACT_NIFTY_INDEX_IDENTITIES:
        if exact in candidates:
            return exact
    raise ValueError(
        "exact_nifty_index_identity_not_found; "
        "option_or_future_substring_matches_are_not_authoritative"
    )


def build_index_timeline(frame: pd.DataFrame, contract: CasWindowContract) -> pd.DataFrame:
    symbol = select_exact_nifty_index_symbol(frame)
    index = resample_last(frame[frame.symbol == symbol].copy())
    index["phase"] = index.timestamp.map(lambda value: classify_phase(value, contract))
    index = index[index.phase != "OUTSIDE_CAS_STUDY"].copy()
    index["return_from_1515_bps"] = np.nan
    pre = index[index.timestamp.dt.strftime("%H:%M:%S") < contract.normal_end]
    if not pre.empty:
        anchor = float(pre.iloc[-1].price)
        index["return_from_1515_bps"] = (index.price / anchor - 1.0) * 10000.0
    index.attrs["selected_symbol"] = symbol
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
                "move_bps": float(
                    (group.price.iloc[-1] / group.price.iloc[0] - 1.0) * 10000.0
                ),
                "high": float(group.price.max()),
                "low": float(group.price.min()),
                "observations": int(len(group)),
            }
        )
    return records


def _study_date(frame: pd.DataFrame) -> str:
    dates = sorted(frame.timestamp.dt.date.astype(str).unique())
    if len(dates) != 1:
        raise ValueError(f"expected_one_session_date={dates}")
    return dates[0]


def constituent_breadth(ticks: pd.DataFrame, contract: CasWindowContract) -> dict:
    try:
        frame = normalize_ticks(ticks)
    except ValueError as exc:
        return {"available": False, "reason": str(exc)}
    date = _study_date(frame)
    pre_cutoff = pd.Timestamp(f"{date} {contract.normal_end}", tz=IST)
    end_cutoff = pd.Timestamp(f"{date} {contract.cas_match_end}", tz=IST)
    before = frame[frame.timestamp < pre_cutoff]
    after = frame[frame.timestamp <= end_cutoff]
    if before.empty or after.empty:
        return {"available": False, "reason": "insufficient_cas_constituent_coverage"}
    start = (
        before.sort_values("timestamp")
        .groupby("symbol")
        .tail(1)
        .set_index("symbol")
        .price
    )
    end = (
        after.sort_values("timestamp")
        .groupby("symbol")
        .tail(1)
        .set_index("symbol")
        .price
    )
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
        "unchanged_count": int((joined["return"] == 0).sum()),
        "positive_fraction": float(positive / len(joined)),
        "median_return_bps": float(joined["return"].median() * 10000.0),
        "equal_weight_mean_bps": float(joined["return"].mean() * 10000.0),
        "top3_absolute_move_share": top3_share,
        "broad_move": bool(
            len(joined) >= contract.minimum_breadth_count
            and top3_share <= contract.max_top3_share
        ),
    }


def _latest_before(frame: pd.DataFrame, cutoff: pd.Timestamp) -> pd.Series | None:
    rows = frame[frame.timestamp <= cutoff]
    return None if rows.empty else rows.iloc[-1]


def _load_instrument_master(path: Path) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("instrument_master_must_be_list")
    return payload


def analyze_frozen_atm_pair(
    raw: pd.DataFrame,
    index: pd.DataFrame,
    master_path: Path,
    expiry_date: str,
    contract: CasWindowContract,
) -> dict:
    if "instrument_key" not in raw.columns:
        return {"available": False, "reason": "instrument_key_missing"}
    date = _study_date(index)
    anchor_cutoff = pd.Timestamp(f"{date} 15:14:59", tz=IST)
    end_cutoff = pd.Timestamp(f"{date} {contract.cas_match_end}", tz=IST)
    anchor_row = _latest_before(index, anchor_cutoff)
    if anchor_row is None:
        return {"available": False, "reason": "missing_pre_1515_index_anchor"}
    strike = int(round(float(anchor_row.price) / 50.0) * 50)
    master = _load_instrument_master(master_path)
    selected: dict[str, dict] = {}
    for row in master:
        if row.get("underlying_symbol") != "NIFTY":
            continue
        option_type = row.get("instrument_type")
        if option_type not in {"CE", "PE"}:
            continue
        if float(row.get("strike_price", -1)) != float(strike):
            continue
        expiry_ms = row.get("expiry")
        if expiry_ms is None:
            continue
        expiry = (
            pd.to_datetime(expiry_ms, unit="ms", utc=True)
            .tz_convert(IST)
            .date()
            .isoformat()
        )
        if expiry == expiry_date:
            selected[option_type] = row
    if set(selected) != {"CE", "PE"}:
        return {
            "available": False,
            "reason": "exact_atm_pair_not_found",
            "strike": strike,
            "expiry": expiry_date,
        }

    normalized = normalize_ticks(raw)
    outcomes: dict[str, dict] = {}
    for option_type, identity in selected.items():
        key = str(identity["instrument_key"])
        path = normalized[normalized.symbol == key].sort_values("timestamp")
        start = _latest_before(path, anchor_cutoff)
        end = _latest_before(path, end_cutoff)
        if start is None or end is None:
            outcomes[option_type] = {"available": False, "reason": "path_incomplete"}
            continue
        outcomes[option_type] = {
            "available": True,
            "instrument_key": key,
            "trading_symbol": identity.get("trading_symbol"),
            "start_timestamp": start.timestamp.isoformat(),
            "end_timestamp": end.timestamp.isoformat(),
            "start_ltp": float(start.price),
            "end_ltp": float(end.price),
            "move_points": float(end.price - start.price),
            "move_pct": float((end.price / start.price - 1.0) * 100.0),
        }
    return {
        "available": all(outcome.get("available") for outcome in outcomes.values()),
        "authority": "LTP_PATH_ONLY_NOT_EXECUTABLE",
        "anchor_index": float(anchor_row.price),
        "strike": strike,
        "expiry": expiry_date,
        "outcomes": outcomes,
    }


def run(
    tick_root: Path,
    constituent_root: Path | None,
    output_dir: Path,
    instrument_master: Path | None = None,
    option_expiry: str | None = None,
) -> dict:
    contract = CasWindowContract()
    raw = _read_parquets(tick_root)
    normalized = normalize_ticks(raw)
    index = build_index_timeline(normalized, contract)
    if index.empty:
        raise ValueError("no_nifty_rows_in_cas_window")

    breadth = {"available": False, "reason": "constituent_root_not_supplied"}
    if constituent_root is not None:
        breadth = constituent_breadth(_read_parquets(constituent_root), contract)

    option_response = {"available": False, "reason": "option_inputs_not_supplied"}
    if instrument_master is not None and option_expiry is not None:
        option_response = analyze_frozen_atm_pair(
            raw, index, instrument_master, option_expiry, contract
        )

    coverage_end = index.timestamp.max()
    complete_through_derivative_close = (
        coverage_end.strftime("%H:%M:%S") >= contract.derivative_end
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    index.to_csv(output_dir / "nifty_cas_timeline.csv", index=False)
    report = {
        "study_id": "CAS_CLOSING_AUCTION_SHADOW_V1",
        "contract": asdict(contract),
        "selected_index_identity": index.attrs.get("selected_symbol"),
        "coverage": {
            "first_timestamp": index.timestamp.min().isoformat(),
            "last_timestamp": coverage_end.isoformat(),
            "complete_through_1540": complete_through_derivative_close,
            "derivative_convergence_observations": int(
                (index.phase == "DERIVATIVE_CONVERGENCE").sum()
            ),
        },
        "phase_summary": summarize_phases(index),
        "constituent_breadth": breadth,
        "frozen_atm_option_response": option_response,
        "claim_boundary": {
            "research_only": True,
            "shadow_only": True,
            "strategy_integration": False,
            "broker_api_called": False,
            "order_action": False,
            "two_sessions_can_establish_edge": False,
            "indicative_close_available_in_upstox_archive": False,
            "option_ltp_is_execution_evidence": False,
        },
        "verdict": "CAS_STRUCTURE_OBSERVED_NOT_EDGE_VALIDATED",
    }
    (output_dir / "cas_shadow_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tick-root", type=Path, required=True)
    parser.add_argument("--constituent-root", type=Path)
    parser.add_argument("--constituent-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--instrument-master", type=Path)
    parser.add_argument("--option-expiry")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    constituent_root = args.constituent_root or args.constituent_file
    report = run(
        args.tick_root,
        constituent_root,
        args.output_dir,
        args.instrument_master,
        args.option_expiry,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
