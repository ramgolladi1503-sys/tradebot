from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.trusted_option_data_joint_warehouse_v1.builder import BuildConfig, git, run_build


def main() -> int:
    parser = argparse.ArgumentParser(description="Build trusted option data coverage and joint warehouse V1 evidence.")
    parser.add_argument("--output-dir", type=Path, default=Path("research/trusted_option_data_joint_warehouse_v1"))
    parser.add_argument("--source-commit", default="151fe6b17900508b7b578aea482d55e4fdabbdf5")
    parser.add_argument("--source-branch", default="research/structural-edge-discovery-sprint-one-survivor")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    output_dir = args.output_dir if args.output_dir.is_absolute() else repo / args.output_dir
    result = run_build(BuildConfig(repo=repo, output_dir=output_dir, source_commit=args.source_commit, source_branch=args.source_branch, worktree_path=repo))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
