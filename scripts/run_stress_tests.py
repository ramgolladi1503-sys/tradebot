import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg
from core.risk_state import RiskState
from core.stress_generator import (
    spread_widen,
    depth_thin,
    quote_stale_burst,
    gap_open,
    iv_spike,
    regime_flip_storm,
)
from ml.truth_dataset import build_truth_dataset
from core.synthetic_market import SyntheticSessionConfig, generate_ohlcv_session


def _load_truth_dataset() -> pd.DataFrame:
    path = Path("data/truth_dataset.parquet")
    if path.exists():
        return pd.read_parquet(path)
    df, _ = build_truth_dataset()
    return df


def _synthetic_df(date_str: str, regime: str, bars: int, seed: int, symbol: str) -> pd.DataFrame:
    cfg = SyntheticSessionConfig(
        symbol=symbol,
        date=date_str,
        regime=regime,
        bars=bars,
        seed=seed,
    )
    bars_data = generate_ohlcv_session(cfg)
    df = pd.DataFrame(bars_data)
    df["symbol"] = symbol
    df["primary_regime"] = regime.upper()
    # Provide required fields for stress checks
    df["quote_age_sec"] = 0.5
    df["spread_pct"] = 0.005
    df["regime_entropy"] = 0.8 if regime.upper() != "EVENT" else 1.0
    df["filled_bool"] = False
    return df


def _apply_to_selected(df: pd.DataFrame, idx: pd.Index, fn, **kwargs) -> pd.DataFrame:
    if len(idx) == 0:
        return df.copy()
    df2 = pd.concat([df.loc[idx], df.drop(idx)])
    df2 = fn(df2, duration=len(idx), **kwargs)
    return df2.loc[df.index]


def _summarize(df: pd.DataFrame) -> dict:
    max_quote_age = float(getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0))
    max_spread_pct = float(getattr(cfg, "MAX_SPREAD_PCT", 0.03))
    entropy_soft = float(getattr(cfg, "RISK_ENTROPY_SOFT", 1.3))

    quote_age = df.get("quote_age_sec")
    spread = df.get("spread_pct")
    regime_entropy = df.get("regime_entropy")

    data_quality_fail = pd.Series(False, index=df.index)
    if quote_age is not None:
        data_quality_fail = data_quality_fail | quote_age.isna() | (quote_age > max_quote_age)
    else:
        data_quality_fail = pd.Series(True, index=df.index)
    if spread is not None:
        data_quality_fail = data_quality_fail | spread.isna()
    else:
        data_quality_fail = pd.Series(True, index=df.index)

    exec_guard_block = pd.Series(False, index=df.index)
    if spread is not None:
        exec_guard_block = exec_guard_block | (spread > max_spread_pct)

    entropy_gate = pd.Series(False, index=df.index)
    if regime_entropy is not None:
        entropy_gate = entropy_gate | (regime_entropy.fillna(0.0) >= entropy_soft)

    no_trade = data_quality_fail | exec_guard_block | entropy_gate

    filled = df.get("filled_bool")
    if filled is not None:
        filled_ok = filled.fillna(False) & (~no_trade)
    else:
        filled_ok = pd.Series(False, index=df.index)

    pnl_series = None
    if "pnl_15m" in df.columns:
        pnl_series = df["pnl_15m"]
    elif "realized_pnl" in df.columns:
        pnl_series = df["realized_pnl"]
    if pnl_series is not None:
        pnl_vals = pnl_series.dropna().astype(float)
    else:
        pnl_vals = pd.Series([], dtype=float)
    max_loss = float(pnl_vals.min()) if not pnl_vals.empty else None
    tail_loss_proxy = None
    if not pnl_vals.empty:
        k = max(1, int(len(pnl_vals) * 0.05))
        tail_loss_proxy = float(pnl_vals.nsmallest(k).mean())

    # RiskState entropy gate count
    rs = RiskState(start_capital=float(getattr(cfg, "CAPITAL", 100000)))
    halt_count = 0
    for row in df.itertuples():
        md = {
            "primary_regime": getattr(row, "primary_regime", None) or getattr(row, "regime", None),
            "regime_entropy": getattr(row, "regime_entropy", None),
            "shock_score": getattr(row, "shock_score", None),
        }
        rs.update_market(getattr(row, "symbol", None), md)
        if rs.mode in ("SOFT_HALT", "HARD_HALT"):
            halt_count += 1

    return {
        "total": int(len(df)),
        "no_trade": int(no_trade.sum()),
        "data_quality_fail": int(data_quality_fail.sum()),
        "exec_guard_block": int(exec_guard_block.sum()),
        "entropy_gate": int(entropy_gate.sum()),
        "halt_count": int(halt_count),
        "filled": int(filled_ok.sum()),
        "missed": int((~filled_ok & ~no_trade).sum()),
        "max_loss": max_loss,
        "tail_loss_proxy": tail_loss_proxy,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic", action="store_true", help="Use synthetic session for stress tests")
    parser.add_argument("--synthetic-regime", default="RANGE")
    parser.add_argument("--synthetic-bars", type=int, default=360)
    parser.add_argument("--synthetic-seed", type=int, default=1)
    parser.add_argument("--synthetic-symbol", default="NIFTY")
    args = parser.parse_args()

    df = _load_truth_dataset()
    source = "truth_dataset"
    if args.synthetic or df.empty:
        df = _synthetic_df(
            date_str=datetime.now().date().isoformat(),
            regime=args.synthetic_regime,
            bars=args.synthetic_bars,
            seed=args.synthetic_seed,
            symbol=args.synthetic_symbol,
        )
        source = "synthetic"
    if df.empty:
        raise RuntimeError("truth_dataset is empty; cannot run stress tests.")

    max_quote_age = float(getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0))
    max_spread_pct = float(getattr(cfg, "MAX_SPREAD_PCT", 0.03))
    entropy_soft = float(getattr(cfg, "RISK_ENTROPY_SOFT", 1.3))
    min_valid_rows = int(getattr(cfg, "STRESS_MIN_VALID_ROWS", 1))

    valid_quote = df.get("quote_age_sec")
    if valid_quote is None or valid_quote.isna().all():
        if "quote_ts_epoch" in df.columns:
            try:
                now_epoch = datetime.utcnow().timestamp()
                valid_quote = (now_epoch - pd.to_numeric(df["quote_ts_epoch"], errors="coerce"))
                df["quote_age_sec"] = valid_quote
            except Exception:
                valid_quote = None
        if valid_quote is None:
            valid_quote = pd.Series([], dtype=float)
    if isinstance(valid_quote, pd.Series) and not valid_quote.empty:
        valid_quote_idx = df[(valid_quote.notna()) & (valid_quote <= max_quote_age)].index
    else:
        valid_quote_idx = pd.Index([])

    valid_spread = df.get("spread_pct")
    if valid_spread is not None:
        valid_spread_idx = df[(valid_spread.notna()) & (valid_spread <= max_spread_pct)].index
    else:
        valid_spread_idx = pd.Index([])

    valid_entropy = df.get("regime_entropy")
    if valid_entropy is not None:
        valid_entropy_idx = df[(valid_entropy.notna()) & (valid_entropy < entropy_soft)].index
    else:
        valid_entropy_idx = pd.Index([])

    if len(valid_quote_idx) < min_valid_rows:
        raise RuntimeError("Insufficient valid quote_age_sec rows to stress quote staleness. Ensure DecisionEvents include quote_ts_epoch or quote_age_sec.")
    if len(valid_spread_idx) < min_valid_rows:
        raise RuntimeError("Insufficient valid spread_pct rows to stress spread widening.")
    if len(valid_entropy_idx) < min_valid_rows:
        raise RuntimeError("Insufficient valid regime_entropy rows to stress regime flip storm.")

    baseline = _summarize(df)

    df_quote = _apply_to_selected(
        df, valid_quote_idx[:min_valid_rows], quote_stale_burst, max_age_sec=max_quote_age
    )
    quote_summary = _summarize(df_quote)

    df_spread = _apply_to_selected(
        df, valid_spread_idx[:min_valid_rows], spread_widen, multiplier=3.0
    )
    spread_summary = _summarize(df_spread)

    df_regime = _apply_to_selected(
        df, valid_entropy_idx[:min_valid_rows], regime_flip_storm, flips_per_window=3
    )
    regime_summary = _summarize(df_regime)

    # Optional additional scenarios (non-asserted)
    df_depth = depth_thin(df, multiplier=0.3, duration=min_valid_rows)
    df_gap = gap_open(df, size_pct=0.02, duration=min_valid_rows)
    df_iv = iv_spike(df, multiplier=1.5, duration=min_valid_rows)

    depth_summary = _summarize(df_depth)
    gap_summary = _summarize(df_gap)
    iv_summary = _summarize(df_iv)

    # Assertions
    assert quote_summary["no_trade"] > baseline["no_trade"], "quote_stale_burst did not increase NO_TRADE count"
    assert quote_summary["data_quality_fail"] > baseline["data_quality_fail"], "quote_stale_burst did not increase data-quality failures"
    assert spread_summary["exec_guard_block"] > baseline["exec_guard_block"], "spread_widen did not increase execution guard blocks"
    assert regime_summary["entropy_gate"] > baseline["entropy_gate"] or regime_summary["halt_count"] > baseline["halt_count"], "regime_flip_storm did not increase entropy gating"

    report = {
        "timestamp": datetime.now().isoformat(),
        "source": source,
        "baseline": baseline,
        "scenarios": {
            "quote_stale_burst": quote_summary,
            "spread_widen": spread_summary,
            "regime_flip_storm": regime_summary,
            "depth_thin": depth_summary,
            "gap_open": gap_summary,
            "iv_spike": iv_summary,
        },
        "coverage": {
            "valid_quote_rows": int(len(valid_quote_idx)),
            "valid_spread_rows": int(len(valid_spread_idx)),
            "valid_entropy_rows": int(len(valid_entropy_idx)),
            "min_valid_rows_used": int(min_valid_rows),
        },
    }

    out = Path("logs") / f"stress_report_{datetime.now().date().isoformat()}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"Stress report: {out}")


if __name__ == "__main__":
    main()
