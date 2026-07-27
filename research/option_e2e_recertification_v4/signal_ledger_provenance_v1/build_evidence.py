from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from .audit import audit_signal_ledger
from .generate import publish_provenance_evidence
from .git_provenance import LEDGER_RELATIVE_PATH, derive_invalidation, derive_ownership
from .lineage import build_historical_binding
from .provenance_search import search_preexisting_non_outcome_provenance


def build_immutable_evidence(repo_root: Path, external_roots: Iterable[Path] = ()) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    binding = build_historical_binding(repo_root)
    ledger_bytes = (repo_root / LEDGER_RELATIVE_PATH).read_bytes()
    ownership = derive_ownership(ledger_bytes, binding["historical_inventory"])
    invalidation = derive_invalidation(repo_root, binding)
    search_records = search_preexisting_non_outcome_provenance(repo_root, external_roots)
    evidence = {
        "historical_binding": {
            "history": binding["history"],
            "historical_blobs": binding["historical_blobs"],
            "generator_output_binding": binding["generator_output_binding"],
        },
        "ownership": ownership,
        "invalidation": invalidation,
        "search_records": search_records,
    }
    result = audit_signal_ledger(ledger_bytes, evidence)
    sources = [
        {"category": "DISCOVERED_HISTORY", "finding": binding["history"]},
        {"category": "HISTORICAL_BLOBS", "finding": binding["historical_blobs"]},
        {"category": "GENERATOR_OUTPUT_BINDING", "finding": binding["generator_output_binding"]},
        {"category": "OWNERSHIP", "finding": ownership},
        {"category": "INVALIDATION", "finding": invalidation},
        {"category": "SEARCH_RECORDS", "finding": search_records},
        {"category": "PRIMARY_VERDICT", "finding": result["verdict"]},
    ]
    return evidence, sources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--external-root", action="append", type=Path, default=[])
    args = parser.parse_args()
    result = publish_provenance_evidence(args.repo_root.resolve(), args.output_dir, external_roots=args.external_root)
    print(json.dumps({"agreement": result["agreement"]["status"], "verdict": result["primary"]["verdict"], "semantic_manifest_sha256": result["semantic_manifest_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
