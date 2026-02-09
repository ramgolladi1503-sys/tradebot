import json
import sys
from collections import defaultdict
from pathlib import Path

from config import config as cfg


def _read_jsonl(path: Path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def main():
    path = Path(getattr(cfg, "META_SHADOW_LOG_PATH", "logs/meta_shadow.jsonl"))
    rows = _read_jsonl(path)
    if not rows:
        print(f"Meta shadow log missing or empty: {path}")
        sys.exit(2)

    deltas = [r.get("weight_delta") for r in rows if r.get("weight_delta") is not None]
    avg_delta = sum(deltas) / len(deltas) if deltas else 0.0
    by_regime = defaultdict(list)
    by_strategy = defaultdict(list)
    by_predictor = defaultdict(list)
    for r in rows:
        reg = r.get("primary_regime") or "UNKNOWN"
        strat = r.get("strategy") or "UNKNOWN"
        pred = r.get("suggested_predictor") or "UNKNOWN"
        if r.get("weight_delta") is not None:
            by_regime[reg].append(r["weight_delta"])
            by_strategy[strat].append(r["weight_delta"])
            by_predictor[pred].append(r["weight_delta"])

    print(f"Meta shadow rows: {len(rows)}")
    print(f"Average weight delta: {avg_delta:.4f}")
    print("By regime:")
    for reg, vals in sorted(by_regime.items()):
        if not vals:
            continue
        print(f"  {reg}: avg_delta={sum(vals)/len(vals):.4f} n={len(vals)}")
    print("By predictor:")
    for pred, vals in sorted(by_predictor.items()):
        if not vals:
            continue
        print(f"  {pred}: avg_delta={sum(vals)/len(vals):.4f} n={len(vals)}")
    print("By strategy (top 10):")
    top = sorted(by_strategy.items(), key=lambda x: len(x[1]), reverse=True)[:10]
    for strat, vals in top:
        if not vals:
            continue
        print(f"  {strat}: avg_delta={sum(vals)/len(vals):.4f} n={len(vals)}")

    sys.exit(0)


if __name__ == "__main__":
    main()
