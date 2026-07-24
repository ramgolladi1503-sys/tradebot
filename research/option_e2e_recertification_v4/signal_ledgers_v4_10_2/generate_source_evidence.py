from __future__ import annotations

import argparse
import json
from pathlib import Path

from .source_search_manifest import generate_source_search_evidence, semantic_hash


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")


def generate(repo_root: Path, output_dir: Path, max_candidates_per_root: int) -> dict[str, object]:
    evidence = generate_source_search_evidence(
        repo_root,
        max_candidates_per_root=max_candidates_per_root,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    diagnostics = dict(evidence.get("diagnostics", {}))
    semantic_payload = {key: value for key, value in evidence.items() if key != "diagnostics"}
    semantic_payload["semantic_sha256"] = semantic_hash(
        {key: value for key, value in semantic_payload.items() if key != "semantic_sha256"}
    )

    _write_json(output_dir / "source_search_manifest.json", semantic_payload)
    (output_dir / "source_search_manifest.json.sha256").write_text(
        f"{semantic_payload['semantic_sha256']}  source_search_manifest.json\n",
        encoding="utf-8",
    )
    _write_json(output_dir / "root_inventory.json", semantic_payload["root_inventory"])
    _write_json(output_dir / "git_search_manifest.json", semantic_payload["git_searches"])
    _write_jsonl(output_dir / "candidate_inventory.jsonl", semantic_payload["candidate_inventory"])
    _write_json(output_dir / "local_diagnostics.json", diagnostics)

    summary = {
        "conclusion": semantic_payload["conclusion"],
        "reason_codes": semantic_payload["reason_codes"],
        "candidate_count": semantic_payload["candidate_count"],
        "accepted_candidate_count": semantic_payload["accepted_candidate_count"],
        "unresolved_candidate_count": semantic_payload["unresolved_candidate_count"],
        "truncated": semantic_payload["truncated"],
        "semantic_sha256": semantic_payload["semantic_sha256"],
        "output_dir": str(output_dir),
    }
    _write_json(output_dir / "source_search_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate offline VWAP source-search evidence.")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-candidates-per-root", type=int, default=10000)
    args = parser.parse_args()

    summary = generate(
        args.repo.resolve(),
        args.output.resolve(),
        args.max_candidates_per_root,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
