from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Mapping

from core.observability.evidence_bundle import write_observability_evidence_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Tradebot observability evidence bundle from JSONL events.")
    parser.add_argument("--input", required=True, help="Path to a JSONL file containing serialized observability events.")
    parser.add_argument("--output-dir", default="runtime/evidence", help="Directory where evidence JSON files are written.")
    args = parser.parse_args()

    events = list(_read_jsonl(Path(args.input)))
    written = write_observability_evidence_bundle(events, output_dir=args.output_dir)
    for name in sorted(written):
        print(f"{name}: {written[name]}")
    return 0


def _read_jsonl(path: Path) -> Iterable[Mapping[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number} is not a JSON object")
            yield payload


if __name__ == "__main__":
    raise SystemExit(main())
