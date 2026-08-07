from __future__ import annotations

import argparse
from pathlib import Path

from research.history_first_pattern_miner_v1.miner import run_discovery, write_discovery


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()

    result = run_discovery(Path(args.source_file))
    write_discovery(Path(args.output_root), result)
    print(result["day_archetypes"]["principal_verdict"])
    print(result["prefix_divergence"]["principal_verdict"])
    print(result["branch_discriminators"]["principal_verdict"])
    print(result["semantic_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
