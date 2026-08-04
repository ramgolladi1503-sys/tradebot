from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aixion_trade_intelligence.rag_ingestion import ingest_evidence_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic Aixion evidence chunks.")
    parser.add_argument("paths", nargs="+", help="Evidence files to ingest")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-characters-per-chunk", required=True, type=int)
    args = parser.parse_args()
    chunks = ingest_evidence_paths(
        [Path(value) for value in args.paths],
        document_type_by_suffix={
            ".json": "STRUCTURED_EVIDENCE",
            ".md": "MARKDOWN_EVIDENCE",
            ".txt": "TEXT_EVIDENCE",
        },
        max_characters_per_chunk=args.max_characters_per_chunk,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk.to_record(), sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"chunks": len(chunks), "output": output.as_posix()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
