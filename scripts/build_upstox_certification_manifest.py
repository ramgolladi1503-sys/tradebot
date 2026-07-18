from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.ai_certification.upstox_corpus import (
    CorpusError,
    build_upstox_corpus_manifest,
    write_upstox_corpus_manifest,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify an Upstox replay directory or ZIP into conservative certification evidence lanes."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        manifest = build_upstox_corpus_manifest(args.source)
        output = write_upstox_corpus_manifest(manifest, args.output)
    except (CorpusError, OSError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, sort_keys=True))
        return 2
    payload = manifest.to_dict()
    print(
        json.dumps(
            {
                "status": "CLASSIFIED",
                "output": str(output),
                "files_scanned": payload["files_scanned"],
                "summary": payload["summary"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
