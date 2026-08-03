#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from core.qa_certification.meg_shadow_system import FAILED_VERDICT, assemble_system_certificate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline-report", required=True)
    parser.add_argument("--post-market-certificate")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    certificate = assemble_system_certificate(
        offline_report=args.offline_report,
        post_market_certificate=args.post_market_certificate,
        output_dir=args.output_dir,
    )
    print(json.dumps(certificate, indent=2, sort_keys=True))
    return 1 if certificate["verdict"] == FAILED_VERDICT else 0


if __name__ == "__main__":
    raise SystemExit(main())
