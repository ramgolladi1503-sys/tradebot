from __future__ import annotations

import argparse
from pathlib import Path

from .contract import build_manifests, legacy_reconstruction, write_json_with_sidecar
from .oracle import recompute_current_universe, recompute_legacy_disposition


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-worktree", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    legacy = legacy_reconstruction()
    legacy_oracle = recompute_legacy_disposition(legacy)
    manifests = build_manifests(campaign_worktree=args.campaign_worktree)
    current_oracle = recompute_current_universe(manifests["machine"], manifests["portable"])

    write_json_with_sidecar(args.output_dir / "legacy_root_reconstruction.json", legacy)
    write_json_with_sidecar(args.output_dir / "legacy_root_reconstruction_oracle.json", legacy_oracle)
    write_json_with_sidecar(args.output_dir / "current_source_universe_contract.json", manifests["portable"])
    write_json_with_sidecar(args.output_dir / "current_source_universe_machine_manifest.json", manifests["machine"])
    write_json_with_sidecar(args.output_dir / "current_source_universe_oracle.json", current_oracle)
    print(current_oracle["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
