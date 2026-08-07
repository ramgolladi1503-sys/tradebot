from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.autonomous_structural_edge_exhaustion_v1.common import stable_write
from research.zscore_regime_displacement_v1.core import run_development


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run frozen Z-score regime-displacement development certification."
    )
    parser.add_argument("--source-file", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()

    output = Path(args.output_root)
    output.mkdir(parents=True, exist_ok=True)
    stages = run_development(args.source_file)
    for name, payload in stages.items():
        stable_write(output / f"{name}.json", payload)

    final = stages["final_authority"]
    print(json.dumps(final, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
