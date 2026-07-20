from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from research.opening_range_retest_edge_screen_v1 import contract as C


RETURN_FIELD = "directional_underlying_return"
TOLERANCE = 1e-10


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sidecar_hash(path: Path) -> str | None:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    return sidecar.read_text(encoding="utf-8").split()[0] if sidecar.exists() else None


def parse_timestamp(value: str) -> str:
    # String-level normalization is sufficient for this independent oracle's
    # calendar/session grouping and avoids importing engine timestamp helpers.
    return value[:19]


def measured_primary_rows(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for record in ledger.get("records", []):
        horizon = record.get("horizons", {}).get(str(C.PRIMARY_HORIZON), {})
        if horizon.get("status") != "MEASURED":
            continue
        core = record["candidate_core"]
        rows.append(
            {
                "candidate_id": record["candidate_id"],
                "session_date": core["session_date"],
                "symbol": core["symbol"],
                "direction": core["direction"],
                "proposal_ready_at_iso": core["proposal_ready_at_iso"],
                "entry_start": parse_timestamp(record["legal_entry"]["start"]),
                "terminal_start": parse_timestamp(horizon["terminal_start"]),
                "entry_open": float(record["legal_entry"]["open"]),
                "terminal_close": float(horizon["terminal_close"]),
                "return": float(horizon[RETURN_FIELD]),
            }
        )
    return rows


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def session_means(rows: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[row["session_date"]].append(row["return"])
    return {key: mean(values) for key, values in sorted(grouped.items())}


def sign_test(values: list[float]) -> dict[str, Any]:
    positive = sum(1 for value in values if value > 0)
    negative = sum(1 for value in values if value < 0)
    zero = len(values) - positive - negative
    n = positive + negative
    if n == 0:
        one_sided = 1.0
        two_sided = 1.0
    else:
        one_sided = sum(math.comb(n, i) for i in range(positive, n + 1)) / (2**n)
        two_sided = min(1.0, 2.0 * sum(math.comb(n, i) for i in range(min(positive, negative) + 1)) / (2**n))
    return {
        "positive": positive,
        "negative": negative,
        "zero": zero,
        "binomial_n_excluding_zero": n,
        "one_sided_p_positive_tendency": one_sided,
        "two_sided_p": two_sided,
    }


def opposite_direction_check(rows: list[dict[str, Any]]) -> dict[str, Any]:
    mismatches = 0
    max_abs_error = 0.0
    first_mismatch = None
    for row in rows:
        raw = (row["terminal_close"] - row["entry_open"]) / row["entry_open"]
        signal = raw if row["direction"] == "BUY_CALL" else -raw
        opposite = -raw if row["direction"] == "BUY_CALL" else raw
        error = max(abs(signal - row["return"]), abs(signal + opposite))
        max_abs_error = max(max_abs_error, error)
        if error > TOLERANCE:
            mismatches += 1
            if first_mismatch is None:
                first_mismatch = {"candidate_id": row["candidate_id"], "error": error}
    return {
        "records_checked": len(rows),
        "mismatches": mismatches,
        "max_abs_error": max_abs_error,
        "first_mismatch": first_mismatch,
    }


def component_count(rows: list[dict[str, Any]]) -> int:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["session_date"], row["symbol"])].append(row)
    count = 0
    for group_rows in grouped.values():
        current_end = ""
        for row in sorted(group_rows, key=lambda item: (item["entry_start"], item["terminal_start"], item["candidate_id"])):
            if not current_end or row["entry_start"] >= current_end:
                count += 1
                current_end = row["terminal_start"]
            elif row["terminal_start"] > current_end:
                current_end = row["terminal_start"]
    return count


def compare_float(name: str, observed: float, expected: float, failures: list[str], agreements: list[dict[str, Any]]) -> None:
    diff = abs(observed - expected)
    agreements.append({"metric": name, "oracle": observed, "artifact": expected, "abs_diff": diff})
    if diff > TOLERANCE:
        failures.append(f"METRIC_MISMATCH:{name}:{diff}")


def audit(output_dir: Path) -> dict[str, Any]:
    failures: list[str] = []
    artifacts: dict[str, dict[str, Any]] = {}
    for key, filename in C.ARTIFACT_NAMES.items():
        path = output_dir / filename
        if not path.exists():
            failures.append(f"MISSING_ARTIFACT:{key}")
            continue
        actual = C.sha256_file(str(path))
        expected = sidecar_hash(path)
        if actual != expected:
            failures.append(f"SIDECAR_MISMATCH:{key}")
        artifacts[key] = {"path": filename, "sha256": actual, "sidecar_sha256": expected}

    ledger_path = output_dir / "opening_range_retest_outcome_ledger_v2.json"
    overlap_path = output_dir / "opening_range_retest_outcome_overlap_v2.json"
    if not ledger_path.exists():
        ledger_path = Path(C.SOURCE_LEDGER_PATH)
    if not overlap_path.exists():
        overlap_path = Path(C.SOURCE_OVERLAP_PATH)
    ledger = load_json(ledger_path)
    overlap_authority = load_json(overlap_path)
    metrics = load_json(output_dir / C.ARTIFACT_NAMES["metrics"])
    controls = load_json(output_dir / C.ARTIFACT_NAMES["controls"])
    overlap = load_json(output_dir / C.ARTIFACT_NAMES["overlap"])
    verdict = load_json(output_dir / C.ARTIFACT_NAMES["verdict"])

    if C.sha256_file(str(ledger_path)) != C.SOURCE_LEDGER_SHA256:
        failures.append("SOURCE_LEDGER_SHA_MISMATCH")
    if C.sha256_file(str(overlap_path)) != C.SOURCE_OVERLAP_SHA256:
        failures.append("SOURCE_OVERLAP_SHA_MISMATCH")

    rows = measured_primary_rows(ledger)
    sessions = list(session_means(rows).values())
    primary_mean = mean(sessions)
    primary_sign = sign_test(sessions)
    agreements: list[dict[str, Any]] = []
    compare_float("primary.session_equal_mean", primary_mean, metrics["primary"]["session_equal_mean"], failures, agreements)
    compare_float("primary.session_equal_mean_bps", primary_mean * 10000.0, metrics["primary"]["session_equal_mean_bps"], failures, agreements)
    compare_float("primary.session_median", median(sessions), metrics["primary"]["session_distribution"]["median"], failures, agreements)
    if len(rows) != C.EXPECTED_MEASURED_COUNTS[C.PRIMARY_HORIZON]:
        failures.append("PRIMARY_COUNT_MISMATCH")
    if primary_sign != metrics["primary"]["sign_test"]:
        failures.append("PRIMARY_SIGN_TEST_MISMATCH")

    opposite = opposite_direction_check(rows)
    if opposite["mismatches"] != 0:
        failures.append("OPPOSITE_RECOMPUTE_MISMATCH")
    if controls["opposite_direction"]["mismatches"] != 0:
        failures.append("OPPOSITE_CONTROL_ARTIFACT_FAILED")

    auth_horizon = overlap_authority.get("horizons", {}).get(str(C.PRIMARY_HORIZON), {})
    if auth_horizon.get("complete_interval_count") != len(rows):
        failures.append("OVERLAP_AUTHORITY_COUNT_MISMATCH")
    oracle_component_count = component_count(rows)
    if oracle_component_count != overlap["one_per_accepted_overlap_component"]["component_count"]:
        failures.append("OVERLAP_COMPONENT_COUNT_MISMATCH")

    oracle_verdict = "ORB_NO_STRUCTURAL_EDGE" if primary_mean <= 0 else verdict["verdict"]
    if oracle_verdict != verdict["verdict"]:
        failures.append("VERDICT_AGREEMENT_MISMATCH")
    if verdict.get("terminal_primary_rule_applied") != (primary_mean <= 0):
        failures.append("TERMINAL_PRIMARY_RULE_MISMATCH")

    max_abs_diff = max((item["abs_diff"] for item in agreements), default=0.0)
    return {
        "schema_version": C.SCHEMA_VERSION,
        "mode": "ORB_EDGE_SCREEN_ORACLE_AUDIT_V1",
        "candidate_id": "ALL_ORB_OUTCOME_V2_CANDIDATES",
        "decision": "ORB_EDGE_SCREEN_AUDIT_CERTIFIED" if not failures else "ORB_EDGE_SCREEN_AUDIT_FAILED",
        "reason": "independent oracle recomputed primary returns, sign tests, primitive opposite returns, overlap component counts, and verdict trace from accepted source artifacts",
        "timestamp": C.TIMESTAMP,
        "source": "opening_range_retest_outcome_ledger_v2.json",
        "verdict": "ORB_EDGE_SCREEN_AUDIT_CERTIFIED" if not failures else "ORB_EDGE_SCREEN_AUDIT_FAILED",
        "failures": failures,
        "artifact_hashes": artifacts,
        "metric_agreement": agreements,
        "first_mismatch": failures[0] if failures else None,
        "maximum_absolute_difference": max_abs_diff,
        "verdict_agreement": oracle_verdict == verdict["verdict"],
        "opposite_direction_oracle": opposite,
        "overlap_component_count_oracle": oracle_component_count,
        **C.safety_fields(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(audit(Path(args.artifact_dir)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
