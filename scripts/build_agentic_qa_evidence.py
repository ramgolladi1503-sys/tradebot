from __future__ import annotations

import argparse

from core.agentic_qa.adapter import write_agentic_qa_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Build fail-closed Agentic QA evidence from an existing certification bundle.")
    parser.add_argument("bundle")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(write_agentic_qa_evidence(args.bundle, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
