from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.autonomous_structural_edge_exhaustion_v1.common import stable_write
from research.tradingview_public_library_benchmark_v1.normalized_benchmark import run_from_normalized
from research.tradingview_public_library_benchmark_v1.parameter_guard import install as install_parameter_guard
from research.tradingview_public_library_benchmark_v1.performance_guard import install as install_performance_guard


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--inventory", required=True)
    p.add_argument("--normalized-aeron", required=True)
    p.add_argument("--output-root", required=True)
    args = p.parse_args()

    # Freeze parameter interpretation and install semantics-preserving bookkeeping before
    # the market outcome engine is invoked.
    install_parameter_guard()
    install_performance_guard()

    inventory = json.loads(Path(args.inventory).read_text())
    root = Path(args.output_root)
    root.mkdir(parents=True, exist_ok=True)
    result = run_from_normalized(inventory, Path(args.normalized_aeron))

    stable_write(root / "mapping.json", result["mapping"])
    stable_write(root / "source_authority.json", result["source_authority"])
    stable_write(root / "bar_authority.json", result["bar_authority"])
    stable_write(root / "split_counts.json", result["split_counts"])
    stable_write(root / "nifty_outcomes.json", result["nifty_outcomes"])
    stable_write(root / "banknifty_outcomes.json", result["banknifty_outcomes"])
    stable_write(root / "structural_screen.json", result["structural_screen"])
    stable_write(root / "validation_wfa.json", result["validation_wfa"])
    stable_write(root / "robustness.json", result["robustness"])
    stable_write(root / "final_holdout.json", result["final_holdout"])
    stable_write(root / "final_authority.json", result["final_authority"])
    stable_write(root / "campaign_digest.json", {"semantic_sha256": result["semantic_sha256"]})
    print(json.dumps(result["final_authority"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
