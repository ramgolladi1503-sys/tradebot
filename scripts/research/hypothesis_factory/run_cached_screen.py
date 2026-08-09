#!/usr/bin/env python3
"""Screen hypotheses from a previously built canonical corpus cache.

This avoids rescanning raw corpus files. It is research-only and never certifies
edge or grants runtime/broker authority. Cached screening uses strict semantics:
no overlapping trades and unsupported exit rules fail closed.

A reconciled manifest may be supplied explicitly. The runner never silently
switches datasets because dataset identity is part of the evidence chain.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


hf = load_module("hypothesis_factory", HERE / "hypothesis_factory.py")
strict = load_module("strict_screen_engine", HERE / "strict_screen_engine.py")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache-dir", default="research/hypotheses/corpus_cache")
    p.add_argument("--reconciled-manifest", default="", help="Explicit reconciled_manifest.json; if omitted use v1 canonical cache")
    p.add_argument("--instrument", required=True)
    p.add_argument("--output-dir", default="research/hypotheses/cached_screen_runs")
    p.add_argument("--min-trades", type=int, default=20)
    p.add_argument("--cost-bps", type=float, default=8.0)
    p.add_argument("--spread-max-pct", type=float, default=0.02)
    p.add_argument("--run-id", default="")
    args = p.parse_args(argv)

    instrument = args.instrument.strip().upper()
    cache_dir = Path(args.cache_dir)

    if args.reconciled_manifest:
        source_manifest_path = Path(args.reconciled_manifest)
        if not source_manifest_path.exists():
            raise SystemExit(f"reconciled manifest missing: {source_manifest_path}")
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        canonical = source_manifest.get("outputs", {}).get(instrument)
        dataset_kind = "RECONCILED_CANONICAL"
    else:
        source_manifest_path = cache_dir / "cache_manifest.json"
        if not source_manifest_path.exists():
            raise SystemExit(f"cache manifest missing: {source_manifest_path}")
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        canonical = source_manifest.get("canonical_outputs", {}).get(instrument)
        dataset_kind = "CANONICAL_V1"

    if not canonical:
        raise SystemExit(f"no cache data for instrument={instrument}")
    data_path = Path(canonical["path"])
    if not data_path.exists():
        raise SystemExit(f"canonical data missing: {data_path}")

    hypotheses = hf.generate_hypotheses(instruments=[instrument])
    rows = hf.load_rows(data_path)
    cfg = hf.ScreenConfig(min_trades=args.min_trades, cost_bps=args.cost_bps, spread_max_pct=args.spread_max_pct)
    results = strict.screen_hypotheses_strict(hypotheses, rows, cfg)

    run_id = args.run_id or datetime.now(timezone.utc).strftime("CACHED-STRICT-%Y%m%dT%H%M%SZ")
    out = Path(args.output_dir) / run_id
    out.mkdir(parents=True, exist_ok=True)
    hf.write_json(out / "generated_hypotheses.json", hypotheses)
    hf.write_json(out / "screen_results.json", results)
    hf.write_csv(out / "leaderboard.csv", results)

    manifest = {
        "schema_version": "tradebot-cached-strict-screen-run-v1",
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "instrument": instrument,
        "dataset_kind": dataset_kind,
        "source_manifest": str(source_manifest_path),
        "cache_data": str(data_path),
        "cache_data_sha256": canonical.get("sha256"),
        "loaded_rows": len(rows),
        "hypotheses": len(hypotheses),
        "promising_not_certified": sum(r.get("status") == "PROMISING_NOT_CERTIFIED" for r in results),
        "unsupported_exit_rule_count": sum(r.get("screen_rejection_reason") == "UNSUPPORTED_EXIT_RULE" for r in results),
        "min_trades": args.min_trades,
        "cost_bps": args.cost_bps,
        "spread_max_pct": args.spread_max_pct,
        "screen_semantics": {
            "overlapping_trades_allowed": False,
            "supported_exit_rules": sorted(strict.SUPPORTED_EXIT_RULES),
            "pnl_semantics": "UNDERLYING_DIRECTION_PROXY_BPS",
            "option_pnl_claimed": False,
        },
        "certification": "NOT_CERTIFIED",
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
    }
    hf.write_json(out / "run_manifest.json", manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
