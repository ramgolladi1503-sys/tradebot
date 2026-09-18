#!/usr/bin/env python3
"""CLI for generating authoritative repository release dependency evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.release_dependency_evidence import (
    dependency_graph_digest,
    scan_repository_dependencies,
    serialize_dependency_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate authoritative repository release dependency evidence")
    parser.add_argument("--repo", type=Path, default=Path("."), help="Repository root path")
    parser.add_argument("--candidate", required=True, help="Candidate commit SHA")
    parser.add_argument("--output", type=Path, required=True, help="Path to output DEPENDENCY_GRAPH.json")
    parser.add_argument("--metadata", type=Path, help="Optional path to output analysis metadata JSON")
    args = parser.parse_args()

    repo = args.repo.resolve()
    evidence, metadata = scan_repository_dependencies(repo, args.candidate)
    serialized = serialize_dependency_evidence(evidence)
    digest_val = dependency_graph_digest(evidence)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(serialized, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.metadata:
        metadata_payload = {**metadata, "dependency_graph_sha256": digest_val}
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        args.metadata.write_text(json.dumps(metadata_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": "SUCCESS",
        "candidate_sha": args.candidate,
        "complete": evidence.complete,
        "unresolved_count": len(evidence.unresolved),
        "dependency_graph_sha256": digest_val,
        "output_path": str(args.output),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
