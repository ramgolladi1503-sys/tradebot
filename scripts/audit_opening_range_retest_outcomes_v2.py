#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.opening_range_retest_outcomes_v2.audit import audit_outputs


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, default=PROJECT_ROOT / "docs" / "agent_reviews")
    parser.add_argument("--source-project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    base = args.artifact_dir
    paths = {
        "contract": base / "opening_range_retest_outcome_contract_v2.json",
        "ledger": base / "opening_range_retest_outcome_ledger_v2.json",
        "summary": base / "opening_range_retest_outcome_summary_v2.json",
        "overlap": base / "opening_range_retest_outcome_overlap_v2.json",
        "controls": base / "opening_range_retest_outcome_negative_controls_v2.json",
        "audit": base / "opening_range_retest_outcome_audit_v2.json",
        "certification": base / "opening_range_retest_outcome_certification_v2.md",
    }
    audit = audit_outputs(
        contract=_load_json(paths["contract"]),
        ledger=_load_json(paths["ledger"]),
        summary=_load_json(paths["summary"]),
        overlap=_load_json(paths["overlap"]),
        controls=_load_json(paths["controls"]),
        paths={k: v for k, v in paths.items() if k != "audit"},
        artifact_dir=base,
        source_project_root=args.source_project_root,
    )
    print(json.dumps(audit, sort_keys=True))
    return 0 if audit["verdict"] == "ORB_OUTCOMES_V2_AUDIT_CERTIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
