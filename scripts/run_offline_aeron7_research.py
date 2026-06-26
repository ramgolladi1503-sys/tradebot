#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_next_bar_labels import (
    build_multi_horizon_labels,
    build_next_bar_labels,
)
from scripts.build_regime_model_comparison import build_regime_model_comparison
from scripts.build_trade_ev_labels import build_trade_ev_labels
from scripts.convert_aeron7_intraday import convert_aeron7_intraday
from scripts.run_engineered_walk_forward import run_engineered_walk_forward
from scripts.train_segmented_offline_models import (
    train_segmented_offline_models,
)


def _json_safe(value: Any) -> Any:
    try:
        import pandas as pd

        if isinstance(value, pd.DataFrame):
            return {
                "__type__": "DataFrame",
                "rows": int(len(value)),
                "columns": list(value.columns),
            }
        if isinstance(value, pd.Series):
            return {
                "__type__": "Series",
                "rows": int(len(value)),
                "name": value.name,
            }
    except Exception:
        pass
    if isinstance(value, dict):
        return {str(key): _json_safe(subvalue) for key, subvalue in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def load_offline_research_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser()
    if not config_path.exists():
        raise FileNotFoundError(f"config_not_found:{config_path}")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return {
        "source_root": payload.get("source_root", ""),
        "work_dir": payload.get("work_dir", ".runtime/aeron7_research"),
        "symbols": list(payload.get("symbols") or ["NIFTY_F1"]),
        "horizons_bars": [int(v) for v in list(payload.get("horizons_bars") or [1])],
        "train_window_days": int(payload.get("train_window_days") or 60),
        "test_window_days": int(payload.get("test_window_days") or 10),
        "step_days": int(payload.get("step_days") or 10),
        "model_family": str(payload.get("model_family") or "random_forest"),
    }


def run_offline_aeron7_research(
    *,
    source_root: str | Path,
    work_dir: str | Path,
    symbols: list[str],
    horizons_bars: list[int],
    train_window_days: int,
    test_window_days: int,
    step_days: int,
    model_family: str,
    use_ml_overlay: bool = False,
) -> dict[str, Any]:
    src_root = Path(source_root).expanduser()
    if not src_root.exists():
        raise FileNotFoundError(f"source_root_not_found:{src_root}")

    work_root = Path(work_dir).expanduser()
    work_root.mkdir(parents=True, exist_ok=True)

    raw_dir = work_root / "canonical"
    label_dir = work_root / "labels"
    ev_dir = work_root / "ev_labels"
    model_dir = work_root / "models"
    wf_dir = work_root / "walk_forward"
    regime_dir = work_root / "regime_reports"
    summary_path = work_root / "summary.json"

    convert_report = convert_aeron7_intraday(
        source_root=src_root, output_dir=raw_dir, symbols=symbols
    )

    label_reports: list[dict[str, Any]] = []
    ev_reports: list[dict[str, Any]] = []

    written_files = convert_report.get("written_files", [])
    if not written_files:
        # Fallback to glob but filter by requested symbols if convert_report didn't return written_files
        for p in raw_dir.glob("*_intraday.csv"):
            if any(s.replace(" ", "_") in p.name for s in symbols):
                written_files.append(str(p))

    for symbol_path_str in sorted(list(set(written_files))):
        symbol_path = Path(symbol_path_str)
        symbol = symbol_path.stem.replace("_intraday", "")
        if len(horizons_bars) > 1:
            out_path = label_dir / f"{symbol}_multi_horizon.csv"
            report = build_multi_horizon_labels(
                input_csv=symbol_path,
                output_csv=out_path,
                horizons_bars=horizons_bars,
            )
        else:
            out_path = label_dir / f"{symbol}_labeled.csv"
            report = build_next_bar_labels(
                input_csv=symbol_path,
                output_csv=out_path,
                horizon_bars=horizons_bars[0] if horizons_bars else 1,
            )
        report["symbol"] = symbol
        label_reports.append(report)
        ev_out = ev_dir / f"{symbol}_ev.csv"
        ev_report = build_trade_ev_labels(
            input_csv=symbol_path,
            output_csv=ev_out,
            horizons_bars=horizons_bars if len(horizons_bars) > 1 else None,
            horizon_bars=horizons_bars[0] if horizons_bars else 1,
        )
        ev_report["symbol"] = symbol
        ev_reports.append(ev_report)

    segmented_report = None
    walk_forward_report = None
    regime_report = None
    if label_reports:
        first_label_path = Path(label_reports[0]["output_csv"])
        segmented_report = train_segmented_offline_models(
            input_csv=first_label_path,
            model_dir=model_dir,
            label_column=(
                "label_up"
                if len(horizons_bars) <= 1
                else f"label_up_{horizons_bars[0]}"
            ),
            model_family=model_family,
        )
        walk_forward_report = run_engineered_walk_forward(
            input_csv=Path(label_reports[0]["output_csv"]),
            output_dir=wf_dir,
            train_window_days=train_window_days,
            test_window_days=test_window_days,
            step_days=step_days,
            use_ml_overlay=use_ml_overlay,
        )
    if ev_reports:
        regime_report = build_regime_model_comparison(
            input_csv=Path(ev_reports[0]["output_csv"]),
            output_json=regime_dir / "regime_model_comparison.json",
            output_csv=regime_dir / "regime_model_comparison.csv",
            output_md=regime_dir / "regime_model_comparison.md",
            label_column=(
                "ev_positive"
                if len(horizons_bars) <= 1
                else f"ev_positive_{horizons_bars[0]}"
            ),
        )

    payload = {
        "source_root": str(src_root),
        "work_dir": str(work_root),
        "symbols": symbols,
        "horizons_bars": horizons_bars,
        "convert_report": _json_safe(convert_report),
        "label_reports": _json_safe(label_reports),
        "ev_reports": _json_safe(ev_reports),
        "segmented_report": _json_safe(segmented_report),
        "walk_forward_report": _json_safe(walk_forward_report),
        "regime_report": _json_safe(regime_report),
    }
    summary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return {**payload, "summary_path": str(summary_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the offline Aeron7 research pipeline end to end."
    )
    parser.add_argument("--config", default="", help="Optional JSON config path")
    parser.add_argument("--source-root", default="", help="Aeron7 dataset root")
    parser.add_argument(
        "--work-dir", default="", help="Workspace for generated artifacts"
    )
    parser.add_argument("--symbols", default="", help="Comma-separated Aeron7 symbols")
    parser.add_argument(
        "--horizons", default="", help="Comma-separated label horizons in bars"
    )
    parser.add_argument("--train-window-days", type=int, default=0)
    parser.add_argument("--test-window-days", type=int, default=0)
    parser.add_argument("--step-days", type=int, default=0)
    parser.add_argument(
        "--model-family", default="", choices=["", "logistic", "random_forest"]
    )
    parser.add_argument(
        "--use-ml-overlay",
        action="store_true",
        help="Apply ML acceptance gate during backtesting",
    )
    args = parser.parse_args(argv)

    config = (
        load_offline_research_config(args.config) if str(args.config).strip() else {}
    )
    source_root = args.source_root or config.get("source_root", "")
    work_dir = args.work_dir or config.get("work_dir", ".runtime/aeron7_research")
    symbols = [
        item.strip()
        for item in str(args.symbols or ",".join(config.get("symbols", []))).split(",")
        if item.strip()
    ]
    horizons = [
        int(item.strip())
        for item in str(
            args.horizons or ",".join(str(v) for v in config.get("horizons_bars", [1]))
        ).split(",")
        if item.strip()
    ]
    model_family = args.model_family or config.get("model_family", "random_forest")
    report = run_offline_aeron7_research(
        source_root=source_root,
        work_dir=work_dir,
        symbols=symbols,
        horizons_bars=horizons,
        train_window_days=args.train_window_days
        or int(config.get("train_window_days", 60)),
        test_window_days=args.test_window_days
        or int(config.get("test_window_days", 10)),
        step_days=args.step_days or int(config.get("step_days", 10)),
        model_family=model_family,
        use_ml_overlay=getattr(args, "use_ml_overlay", False),
    )
    print(f"summary={report['summary_path']}")
    print(f"converted_files={len(report['convert_report']['written_files'])}")
    print(f"label_files={len(report['label_reports'])}")
    print(f"ev_files={len(report['ev_reports'])}")
    if report.get("walk_forward_report"):
        print(
            f"walk_forward_windows={report['walk_forward_report']['config']['window_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
