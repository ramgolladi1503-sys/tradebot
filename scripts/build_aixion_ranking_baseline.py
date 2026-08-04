#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aixion_trade_intelligence.baseline_builder import build_ranking_baseline


def _read_policy(path: Path) -> tuple[str, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("baseline_policy_must_be_object")
    score_policy = payload.get("score_policy")
    if not isinstance(score_policy, Mapping):
        raise ValueError("baseline_policy_score_policy_missing")
    metrics = score_policy.get("metrics")
    if not isinstance(metrics, Mapping) or not metrics:
        raise ValueError("baseline_policy_score_metrics_missing")
    return tuple(str(name) for name in metrics)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic empirical ranking baseline.")
    parser.add_argument("lineage_files", nargs="+", type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    metric_names = _read_policy(args.policy)
    baseline = build_ranking_baseline(args.lineage_files, metric_names=metric_names)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(baseline.to_record(), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"baseline_id": baseline.baseline_id, "output": args.output.as_posix()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
