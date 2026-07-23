#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

EXPECTED_KITE_HASH = "f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d"
IST = "Asia/Kolkata"


def canonical_hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def dataframe_hash(df: pd.DataFrame) -> str:
    return canonical_hash(df.sort_index(axis=1).to_dict("records"))


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(message: str) -> int:
    print(json.dumps({"status": "FAIL", "error": message}, indent=2), file=sys.stderr)
    return 2


def load_sample_bars(archive: Path, session: str, symbol: str) -> pd.DataFrame:
    with zipfile.ZipFile(archive) as zf:
        for name in sorted(zf.namelist()):
            if "/underlying/" not in name or not name.endswith(".parquet"):
                continue
            if not Path(name).name.upper().startswith(symbol):
                continue
            data = pd.read_parquet(io.BytesIO(zf.read(name)))
            if str(data["fetch_date"].iloc[0]) != session:
                continue
            out = data.copy()
            out["interval_start"] = pd.to_datetime(out["date"], utc=True).dt.tz_convert(IST)
            out["interval_end"] = out["interval_start"] + pd.Timedelta(minutes=5)
            return out.sort_values("interval_start")
    raise RuntimeError(f"sample bars not found: {session} {symbol}")


def verify(root: Path, archive: Path) -> int:
    for sidecar in root.rglob("*.sha256"):
        target = sidecar.with_name(sidecar.name[:-7])
        if target.is_file():
            expected = sidecar.read_text().split()[0]
            if file_sha256(target) != expected:
                return fail(f"sidecar hash mismatch: {target.relative_to(root)}")
    if file_sha256(archive) != EXPECTED_KITE_HASH:
        return fail("archive hash mismatch")
    source = json.loads((root / "source/source_authority.json").read_text())
    if source.get("actual_sha256") != EXPECTED_KITE_HASH:
        return fail("stored source hash mismatch")
    verdict = json.loads((root / "audit/final_verdict.json").read_text())
    if "mutation" in verdict:
        return fail(f"mutation marker detected: {verdict['mutation']}")
    features = pd.read_parquet(root / "features/feature_matrix.parquet")
    outcomes = pd.read_parquet(root / "features/outcome_matrix.parquet")
    hashes = json.loads((root / "features/matrix_hashes.json").read_text())
    if dataframe_hash(features) != hashes.get("feature_matrix_hash"):
        return fail("feature matrix hash mismatch")
    if dataframe_hash(outcomes) != hashes.get("outcome_matrix_hash"):
        return fail("outcome matrix hash mismatch")
    split = json.loads((root / "folds/discovery_validation_split.json").read_text())
    validation_sessions = set(split["final_retrospective_validation_block"])
    outer = json.loads((root / "folds/outer_folds.json").read_text())["folds"]
    for fold in outer:
        train = set(fold["train_sessions"])
        test = set(fold["test_sessions"])
        if train & test:
            return fail("outer fold train/test overlap")
        if validation_sessions & (train | test):
            return fail("validation session leaked into discovery fold")
        if not fold["train_end"] < fold["test_start"]:
            return fail("outer fold not chronological")
    guard = json.loads((root / "folds/validation_access_guard.json").read_text())
    if guard.get("validation_outcomes_materialized_but_access_blocked_until_freeze") is not True:
        return fail("validation access guard missing")
    ledger = pd.read_parquet(root / "discovery/complete_hypothesis_ledger.parquet")
    required_targets = {"CONTINUATION", "REVERSAL", "ABSOLUTE_EXPANSION", "RAW_LONG", "RAW_SHORT"}
    if set(ledger["target_family"].unique()) != required_targets:
        return fail("target family coverage mismatch")
    sample = features.iloc[min(10, len(features) - 1)]
    if pd.Timestamp(sample["entry_timestamp"]) < pd.Timestamp(sample["decision_timestamp"]):
        return fail("entry before decision")
    peer = load_sample_bars(archive, sample["session"], sample["peer_symbol"])
    own = load_sample_bars(archive, sample["session"], sample["symbol"])
    cutoff = pd.Timestamp(sample["decision_timestamp"])
    own_used = own[own["interval_end"] <= cutoff]
    peer_used = peer[peer["interval_end"] <= cutoff]
    if own_used.empty or peer_used.empty:
        return fail("sample cutoff has no completed bars")
    if not bool(features["allowed_for_live_execution"].eq(False).all()):
        return fail("feature rows are live eligible")
    if not bool(outcomes["broker_api_called"].eq(False).all()):
        return fail("outcome rows claim broker calls")
    outcome_sample = outcomes[outcomes["row_id"] == sample["row_id"]].iloc[0]
    ent = pd.Timestamp(sample["entry_timestamp"])
    own_future = own[own["interval_start"] >= ent]
    horizon = own[own["interval_end"] == ent + pd.Timedelta(minutes=30)]
    if horizon.empty or own_future.empty:
        return fail("sample 30m horizon missing")
    calc = (float(horizon.iloc[-1].close) / float(own_future.iloc[0].open) - 1.0) * 10000.0
    if abs(calc - float(outcome_sample["raw_30m_return_bps"])) > 1e-9:
        return fail("sample 30m outcome mismatch")
    freeze = json.loads((root / "freeze/pre_validation_candidate_bundle.json").read_text())
    bundle_hash_path = root / "freeze/pre_validation_candidate_bundle.sha256"
    if bundle_hash_path.is_file():
        expected = bundle_hash_path.read_text().split()[0]
        if hashlib.sha256((json.dumps(freeze, indent=2, sort_keys=True, default=str) + "\n").encode()).hexdigest() != expected:
            return fail("candidate bundle hash mismatch")
    matched = pd.read_parquet(root / "evaluation/matched_controls.parquet")
    if len(matched) and not {"candidate_row_id", "control_row_id", "outer_fold"}.issubset(matched.columns):
        return fail("matched control ownership columns missing")
    print(json.dumps({"status": "PASS", "feature_rows": int(len(features)), "outcome_rows": int(len(outcomes)), "validation_sessions": len(validation_sessions)}, indent=2))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args(argv)
    return verify(args.root, args.archive)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
