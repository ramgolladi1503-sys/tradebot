from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.structural_edge_discovery_sprint.sprint import SprintConfig, run_sprint


def main() -> int:
    parser = argparse.ArgumentParser(description="Run large structural edge discovery sprint.")
    parser.add_argument("--output-dir", type=Path, default=Path("research/structural_edge_discovery_sprint"))
    parser.add_argument("--raw-target", type=int, default=25000)
    parser.add_argument("--replay-limit", type=int, default=250)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    output_dir = args.output_dir if args.output_dir.is_absolute() else repo / args.output_dir
    result = run_sprint(SprintConfig(repo=repo, output_dir=output_dir, raw_target=args.raw_target, replay_limit=args.replay_limit))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

