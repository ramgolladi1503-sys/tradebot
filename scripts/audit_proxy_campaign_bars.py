#!/usr/bin/env python3
"""Data-only normalized-bar and explicit trading-session policy audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_session_policy(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text())
    if not payload.get("source"):
        raise ValueError("session policy missing source")
    if payload.get("timezone") != "Asia/Kolkata":
        raise ValueError("session policy timezone must be Asia/Kolkata")
    grid = payload.get("regular_grid") or {}
    if grid.get("start") != "09:15" or grid.get("end") != "15:25" or int(grid.get("frequency_minutes", 0)) != 5:
        raise ValueError("session policy regular grid mismatch")
    if not isinstance(payload.get("sessions"), dict):
        raise ValueError("session policy missing sessions mapping")
    return payload


def audit_frame(df: pd.DataFrame, policy: dict[str, object], decision_times: list[str]) -> tuple[pd.DataFrame, dict[str, object]]:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    sessions = sorted(df.loc[df["symbol"].eq("NIFTY"), "session"].astype(str).unique())
    policy_sessions = {str(k): str(v) for k, v in dict(policy["sessions"]).items()}
    grid_rows: list[dict[str, object]] = []
    for session in sessions:
        nifty = df[(df["session"].astype(str) == session) & (df["symbol"] == "NIFTY")].sort_values("timestamp")
        declared = policy_sessions.get(session)
        expected = pd.date_range(
            pd.Timestamp(f"{session} 09:15", tz="Asia/Kolkata").tz_convert("UTC"),
            pd.Timestamp(f"{session} 15:25", tz="Asia/Kolkata").tz_convert("UTC"),
            freq="5min",
        )
        have = set(nifty["timestamp"])
        missing = [ts.isoformat() for ts in expected if ts not in have]
        cutoffs = {time: pd.Timestamp(f"{session} {time}", tz="Asia/Kolkata").tz_convert("UTC") in have for time in decision_times}
        if declared == "SPECIAL":
            classification = "SPECIAL_SESSION_OUT_OF_FROZEN_CONTRACT"
            completed = False
            rejection_reason = "special_session_excluded_by_frozen_policy"
        elif declared == "REGULAR":
            completed = not missing and all(cutoffs.values())
            classification = "REGULAR_SESSION_COMPLETE" if completed else "REGULAR_SESSION_PARTIAL"
            rejection_reason = None if completed else ("missing_regular_grid_timestamps" if missing else "missing_decision_cutoff")
        else:
            classification = "MISSING_REQUIRED_INDEX_GRID"
            completed = False
            rejection_reason = "session_absent_from_frozen_calendar_policy"
        grid_rows.append({
            "session": session,
            "declared_session_type": declared,
            "session_classification": classification,
            "nifty_first_timestamp": nifty["timestamp"].min().isoformat() if len(nifty) else None,
            "nifty_last_timestamp": nifty["timestamp"].max().isoformat() if len(nifty) else None,
            "nifty_bar_count": int(len(nifty)),
            "expected_bar_count": int(len(expected)),
            "missing_timestamps": missing,
            "decision_cutoffs_available": cutoffs,
            "completed": bool(completed),
            "rejection_reason": rejection_reason,
        })
    session_grid = pd.DataFrame(grid_rows)
    counts = session_grid["session_classification"].value_counts().to_dict() if len(session_grid) else {}
    completed_count = int((session_grid["session_classification"] == "REGULAR_SESSION_COMPLETE").sum()) if len(session_grid) else 0
    report = {
        "session_policy_source": policy["source"],
        "session_policy_version": policy.get("version"),
        "nifty_sessions_present": len(sessions),
        "classification_counts": {str(k): int(v) for k, v in counts.items()},
        "completed_regular_sessions": completed_count,
        "special_sessions_excluded": session_grid.loc[session_grid["session_classification"].eq("SPECIAL_SESSION_OUT_OF_FROZEN_CONTRACT"), "session"].tolist() if len(session_grid) else [],
        "regular_partial_sessions": session_grid.loc[session_grid["session_classification"].eq("REGULAR_SESSION_PARTIAL"), "session"].tolist() if len(session_grid) else [],
        "missing_policy_sessions": session_grid.loc[session_grid["session_classification"].eq("MISSING_REQUIRED_INDEX_GRID"), "session"].tolist() if len(session_grid) else [],
        "decision_times": list(decision_times),
        "theoretical_max_state_rows": completed_count * len(decision_times),
        "session_contract": "explicit_regular_special_calendar_v1",
    }
    return session_grid, report


def audit(bars: Path, output_dir: Path, decision_times: list[str], session_policy: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(bars)
    policy = load_session_policy(session_policy)
    session_grid, report = audit_frame(df, policy, decision_times)
    report.update({"bars_path": str(bars), "bars_sha256": sha256(bars), "session_policy_path": str(session_policy), "session_policy_sha256": sha256(session_policy)})
    session_grid.to_parquet(output_dir / "session_grid.parquet", index=False)
    (output_dir / "bars_audit.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--session-policy", type=Path, required=True)
    parser.add_argument("--decision-times", nargs="+", default=["10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00", "14:15"])
    args = parser.parse_args()
    print(json.dumps(audit(args.bars, args.output_dir, args.decision_times, args.session_policy), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
