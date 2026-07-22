#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

EXPECTED_KITE_HASH = "f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d"


def canonical_hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def dataframe_hash(df: pd.DataFrame) -> str:
    return canonical_hash(df.sort_index(axis=1).to_dict("records"))


def fail(message: str) -> int:
    print(json.dumps({"status": "FAIL", "error": message}, indent=2), file=sys.stderr)
    return 2


def verify(root: Path) -> int:
    source = json.loads((root / "source/source_authority.json").read_text())
    if source.get("actual_sha256") != EXPECTED_KITE_HASH:
        return fail("source hash altered")
    features = pd.read_parquet(root / "features/feature_matrix.parquet")
    outcomes = pd.read_parquet(root / "features/outcome_matrix.parquet")
    matrix_hashes = json.loads((root / "features/matrix_hashes.json").read_text())
    if dataframe_hash(features) != matrix_hashes.get("feature_matrix_hash"):
        return fail("feature matrix hash mismatch")
    if dataframe_hash(outcomes) != matrix_hashes.get("outcome_matrix_hash"):
        return fail("outcome matrix hash mismatch")
    decision = pd.to_datetime(features["decision_timestamp"])
    entry = pd.to_datetime(features["entry_timestamp"])
    if not bool((entry >= decision).all()):
        return fail("entry precedes completed decision timestamp")
    if not bool(features["allowed_for_live_execution"].eq(False).all()):
        return fail("feature rows are live eligible")
    outer = json.loads((root / "evaluation/chronological_outer_folds.json").read_text())["folds"]
    for fold in outer:
        train = set(fold["train_sessions"])
        test = set(fold["test_sessions"])
        if train & test:
            return fail("fold train/test overlap")
        if not fold["train_end"] < fold["test_start"]:
            return fail("fold is not chronological")
    verdict = json.loads((root / "audit/final_verdict.json").read_text())
    if verdict.get("allowed_for_live_execution") is not False:
        return fail("verdict is live eligible")
    print(json.dumps({"status": "PASS", "feature_rows": int(len(features)), "outcome_rows": int(len(outcomes))}, indent=2))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    return verify(args.root)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
