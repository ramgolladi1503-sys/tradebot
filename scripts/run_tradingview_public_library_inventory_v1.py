from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow.parquet as pq

from research.tradingview_public_library_benchmark_v1.inventory import write_inventory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-file", required=False)
    args = parser.parse_args()

    out = Path(args.output)
    payload = write_inventory(out)
    print(json.dumps({
        "unique_script_count": payload["unique_script_count"],
        "status_counts": payload["status_counts"],
        "visibility_counts": payload["visibility_counts"],
        "publication_type_counts": payload["publication_type_counts"],
        "semantic_sha256": payload["semantic_sha256"],
    }, indent=2, sort_keys=True))

    if args.source_file:
        source = Path(args.source_file)
        schema = pq.ParquetFile(source).schema_arrow
        schema_payload = {
            "path": str(source),
            "columns": [
                {"name": field.name, "type": str(field.type)} for field in schema
            ],
        }
        schema_path = out.parent / "evidence_schema.json"
        schema_path.write_text(json.dumps(schema_payload, indent=2, sort_keys=True) + "\n")
        print(json.dumps(schema_payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
