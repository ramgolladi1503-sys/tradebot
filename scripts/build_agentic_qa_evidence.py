from __future__ import annotations

import argparse

from core.agentic_qa.adapter import build_agentic_qa_bundle


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build an immutable Agentic QA sidecar bundle from an existing frozen certification bundle."
    )
    parser.add_argument("bundle", help="Existing frozen TradeBot certification bundle")
    parser.add_argument("--output-dir", required=True, help="New or empty output directory")
    args = parser.parse_args()
    print(build_agentic_qa_bundle(args.bundle, args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
