from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aixion_trade_intelligence.campaign import SessionEvidence, summarize_campaign


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate real Aixion session evidence.")
    parser.add_argument("reports", nargs="+")
    parser.add_argument("--output", required=True)
    parser.add_argument("--minimum-valid-sessions", required=True, type=int)
    parser.add_argument("--minimum-expiry-sessions", required=True, type=int)
    parser.add_argument("--minimum-non-expiry-sessions", required=True, type=int)
    parser.add_argument("--require-all-diagnosis-ready", action="store_true")
    parser.add_argument("--require-live-shadow-for-all-valid", action="store_true")
    args = parser.parse_args()
    sessions = [SessionEvidence.from_report(path) for path in args.reports]
    summary = summarize_campaign(
        sessions,
        minimum_valid_sessions=args.minimum_valid_sessions,
        minimum_expiry_sessions=args.minimum_expiry_sessions,
        minimum_non_expiry_sessions=args.minimum_non_expiry_sessions,
        require_all_diagnosis_ready=args.require_all_diagnosis_ready,
        require_live_shadow_for_all_valid=args.require_live_shadow_for_all_valid,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary.to_record(), indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps(summary.to_record(), sort_keys=True))
    return 0 if summary.ready_for_multi_session_review else 2


if __name__ == "__main__":
    raise SystemExit(main())
