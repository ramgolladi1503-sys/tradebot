from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.architecture_golden_master import compare_snapshot_files, load_snapshot_rows
from core.execution_ranking_authority import prove_ranking_authority
from core.execution_shadow_cycle import compare_execution_cycle
from core.helper_parity_proof import prove_helper_parity


def _candidate_files(root: Path) -> list[Path]:
    patterns = (
        "**/*suggestion*.jsonl",
        "**/*candidate*.jsonl",
        "**/*snapshot*.jsonl",
        "**/*suggestion*.json",
        "**/*candidate*.json",
        "**/*snapshot*.json",
    )
    files: set[Path] = set()
    for pattern in patterns:
        files.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(files)


def _flatten_rows(payload: Any) -> list[dict[str, Any]]:
    rows = payload if isinstance(payload, list) else [payload]
    flattened: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidates = row.get("candidates") or row.get("suggestions") or row.get("rows")
        if isinstance(candidates, list):
            flattened.extend(item for item in candidates if isinstance(item, dict))
        else:
            flattened.append(row)
    return flattened


def run_campaign(root: Path, output: Path, manifest: Path | None = None) -> dict[str, Any]:
    files = _candidate_files(root)
    corpus: list[dict[str, Any]] = []
    file_reports: list[dict[str, Any]] = []

    for path in files:
        try:
            rows = _flatten_rows(load_snapshot_rows(path))
        except Exception as exc:
            file_reports.append({"path": str(path), "loaded": False, "error": repr(exc)})
            continue
        corpus.extend(rows)
        file_reports.append({"path": str(path), "loaded": True, "rows": len(rows)})

    helper = prove_helper_parity(corpus).to_dict() if corpus else {
        "rows": 0, "matched": 0, "mismatched": 0, "parity_rate": 0.0, "mismatches": []
    }
    shadow = compare_execution_cycle(corpus).to_dict() if corpus else {
        "rows": 0, "matched": 0, "mismatched": 0, "parity_rate": 0.0, "state_counts": {}, "mismatches": []
    }

    golden: list[dict[str, Any]] = []
    if manifest is not None and manifest.exists():
        entries = json.loads(manifest.read_text(encoding="utf-8"))
        for entry in entries:
            expected = root / entry["expected"]
            actual = root / entry["actual"]
            result = compare_snapshot_files(expected, actual).to_dict()
            golden.append({"name": entry.get("name") or expected.name, **result})

    authority = prove_ranking_authority(
        root / "core" / "orchestrator.py",
        root / "strategies" / "trade_builder.py",
        root / "core" / "runtime_snapshot_producer.py",
        root / "core" / "ranking_orchestrator.py",
    ).to_dict()

    verdict = {
        "corpus_present": bool(corpus),
        "helper_parity": bool(corpus) and helper["mismatched"] == 0,
        "shadow_parity": bool(corpus) and shadow["mismatched"] == 0,
        "golden_master": all(item["matched"] for item in golden) if golden else None,
        "ranking_execution_authority_proven": authority["execution_authority_proven"],
    }
    payload = {
        "root": str(root),
        "files_scanned": len(files),
        "rows_scanned": len(corpus),
        "files": file_reports,
        "helper_parity": helper,
        "shadow_cycle": shadow,
        "golden_master": golden,
        "ranking_authority": authority,
        "verdict": verdict,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("artifacts/architecture_hardening_campaign.json"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--require-corpus", action="store_true")
    parser.add_argument("--require-zero-shadow-mismatches", action="store_true")
    parser.add_argument("--require-zero-helper-mismatches", action="store_true")
    args = parser.parse_args()

    payload = run_campaign(args.root.resolve(), args.output, args.manifest)
    print(json.dumps(payload["verdict"], sort_keys=True))

    if args.require_corpus and not payload["verdict"]["corpus_present"]:
        return 2
    if args.require_zero_shadow_mismatches and not payload["verdict"]["shadow_parity"]:
        return 3
    if args.require_zero_helper_mismatches and not payload["verdict"]["helper_parity"]:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
