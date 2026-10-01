#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.cross_sectional_diffusion_direction_v1.campaign import (
    CAMPAIGN_ID,
    add_forward_returns,
    build_feature_frame,
    load_membership,
    load_price_table,
    sha256_path,
    summarize_result,
)
from research.cross_sectional_diffusion_direction_v1.session_wfa import (
    SessionCampaignConfig,
    assess_session_terminal_verdict,
    run_session_walk_forward,
)

PRE_HOLDOUT_END = date(2026, 2, 26)
HOLDOUT_START = date(2026, 2, 27)
EXPECTED_ALIGNED_PANEL_SHA256 = "2311981231d3fb847a216c9165ef73c3e7b788ab354d6de493ab1a5edb32e7a9"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=CAMPAIGN_ID)
    p.add_argument(
        "--aligned-panel",
        help="Preferred authoritative NIFTY_SPOT_FUTURES_ALIGNED_V1.parquet; exact known SHA is auto-verified",
    )
    p.add_argument("--index", help="Fallback NIFTY minute CSV/Parquet when aligned panel is unavailable")
    p.add_argument("--execution", help="Fallback tradable execution minute CSV/Parquet")
    p.add_argument("--constituents", required=True, help="Long-format constituent minute CSV/Parquet or directory")
    p.add_argument("--membership", required=True, help="Historical membership/weights CSV/Parquet")
    p.add_argument("--roundtrip-cost-bps", type=float, required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--membership-authoritative", action="store_true")
    p.add_argument(
        "--execution-authoritative",
        action="store_true",
        help="Fallback mode only; aligned-panel mode derives authority from the exact frozen panel SHA",
    )
    return p.parse_args()


def _canonical_ts(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    if ts.isna().any():
        raise ValueError("aligned_panel_timestamp_parse_failure")
    if getattr(ts.dt, "tz", None) is None:
        return ts.dt.tz_localize("Asia/Kolkata")
    return ts.dt.tz_convert("Asia/Kolkata")


def _load_frozen_aligned_panel(path: str | Path):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    if p.suffix.lower() in {".parquet", ".pq"}:
        raw = pd.read_parquet(p)
    elif p.suffix.lower() == ".csv":
        raw = pd.read_csv(p)
    else:
        raise ValueError("aligned_panel_must_be_csv_or_parquet")

    required = {
        "timestamp",
        "spot_open",
        "spot_close",
        "futures_open",
        "futures_close",
        "alignment_valid",
    }
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"aligned_panel_missing_columns:{','.join(missing)}")

    raw = raw[raw["alignment_valid"].astype(bool)].copy()
    ts = _canonical_ts(raw["timestamp"])
    index = pd.DataFrame(
        {
            "timestamp": ts,
            "open": pd.to_numeric(raw["spot_open"], errors="coerce"),
            "close": pd.to_numeric(raw["spot_close"], errors="coerce"),
        }
    ).dropna()
    execution = pd.DataFrame(
        {
            "timestamp": ts,
            "open": pd.to_numeric(raw["futures_open"], errors="coerce"),
            "close": pd.to_numeric(raw["futures_close"], errors="coerce"),
        }
    ).dropna()
    if index.duplicated("timestamp").any() or execution.duplicated("timestamp").any():
        raise ValueError("aligned_panel_duplicate_timestamps")

    actual_sha = sha256_path(p)
    authority = actual_sha == EXPECTED_ALIGNED_PANEL_SHA256
    return (
        index.sort_values("timestamp").reset_index(drop=True),
        execution.sort_values("timestamp").reset_index(drop=True),
        actual_sha,
        authority,
    )


def _pre_holdout(df: pd.DataFrame) -> pd.DataFrame:
    session_date = df["timestamp"].dt.tz_convert("Asia/Kolkata").dt.date
    return df[session_date <= PRE_HOLDOUT_END].copy()


def main() -> int:
    args = parse_args()
    if args.roundtrip_cost_bps <= 0:
        raise SystemExit("roundtrip cost must be > 0 bps")
    if not args.aligned_panel and not (args.index and args.execution):
        raise SystemExit("provide --aligned-panel, or both --index and --execution")
    if args.aligned_panel and (args.index or args.execution):
        raise SystemExit("use either --aligned-panel or fallback --index/--execution, not both")

    cfg = SessionCampaignConfig()
    aligned_sha = None
    aligned_authority = False
    if args.aligned_panel:
        index_all, execution_all, aligned_sha, aligned_authority = _load_frozen_aligned_panel(args.aligned_panel)
        execution_authoritative = aligned_authority
    else:
        index_all = load_price_table(args.index)
        execution_all = load_price_table(args.execution)
        execution_authoritative = bool(args.execution_authoritative)

    constituents_all = load_price_table(args.constituents, require_symbol=True)
    membership = load_membership(args.membership)

    # V1.2 is deliberately pre-holdout only. The existing REC-MD HOLDOUT begins
    # 2026-02-27 and is not used to select, tune, or score this campaign here.
    index = _pre_holdout(index_all)
    constituents = _pre_holdout(constituents_all)
    execution = _pre_holdout(execution_all)
    if index.empty or constituents.empty or execution.empty:
        raise SystemExit("no pre-holdout data available through 2026-02-26")

    features = build_feature_frame(
        index,
        constituents,
        membership,
        lookback_minutes=cfg.lookback_minutes,
        min_coverage=cfg.min_coverage,
    )
    frame = add_forward_returns(
        features,
        execution,
        (cfg.primary_horizon_minutes, cfg.secondary_horizon_minutes),
    )

    results = {}
    for horizon in (cfg.primary_horizon_minutes, cfg.secondary_horizon_minutes):
        result = run_session_walk_forward(
            frame,
            horizon=horizon,
            cost_bps=args.roundtrip_cost_bps,
            cfg=cfg,
        )
        verdict, blockers = assess_session_terminal_verdict(
            result,
            cfg=cfg,
            membership_authoritative=args.membership_authoritative,
            execution_authoritative=execution_authoritative,
        )
        results[str(horizon)] = {
            **summarize_result(result),
            "verdict": verdict,
            "blockers": blockers,
        }

    primary = results[str(cfg.primary_horizon_minutes)]
    evaluated_min = str(min(frame["session"])) if not frame.empty else None
    evaluated_max = str(max(frame["session"])) if not frame.empty else None
    if evaluated_max is not None and date.fromisoformat(evaluated_max) >= HOLDOUT_START:
        raise RuntimeError("holdout_boundary_violation")

    if args.aligned_panel:
        input_sha = {
            "aligned_spot_futures_panel": aligned_sha,
            "constituents": sha256_path(args.constituents),
            "membership": sha256_path(args.membership),
        }
    else:
        input_sha = {
            "index": sha256_path(args.index),
            "constituents": sha256_path(args.constituents),
            "membership": sha256_path(args.membership),
            "execution": sha256_path(args.execution),
        }

    payload = {
        "campaign_id": CAMPAIGN_ID,
        "spec_version": "1.2.0",
        "stage": "PRE_HOLDOUT_WALK_FORWARD",
        "evaluation_claim": "AFTER_COST_CANDLE_PROXY_NOT_EXACT_FILL_CERTIFICATION",
        "config_sha256": cfg.digest(),
        "primary_horizon_minutes": cfg.primary_horizon_minutes,
        "secondary_horizon_minutes": cfg.secondary_horizon_minutes,
        "roundtrip_cost_bps": args.roundtrip_cost_bps,
        "research_window": {
            "evaluated_min_session": evaluated_min,
            "evaluated_max_session": evaluated_max,
            "pre_holdout_end": str(PRE_HOLDOUT_END),
            "holdout_start": str(HOLDOUT_START),
            "holdout_evaluated": False,
        },
        "aligned_panel_expected_sha256": EXPECTED_ALIGNED_PANEL_SHA256 if args.aligned_panel else None,
        "aligned_panel_sha256_match": aligned_authority if args.aligned_panel else None,
        "input_sha256": input_sha,
        "membership_authoritative": bool(args.membership_authoritative),
        "execution_authoritative": execution_authoritative,
        "primary_verdict": primary["verdict"],
        "primary_blockers": primary["blockers"],
        "results": results,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0 if primary["verdict"] == "PRE_HOLDOUT_DIRECTIONAL_SURVIVOR" else 2


if __name__ == "__main__":
    raise SystemExit(main())
