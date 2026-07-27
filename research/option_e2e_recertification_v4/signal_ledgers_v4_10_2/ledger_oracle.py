from __future__ import annotations


def certify_ledger(
    records: list[dict[str, object]],
    *,
    source_manifest: dict[str, object] | None = None,
    oracle_evidence: dict[str, object] | None = None,
) -> dict[str, object]:
    """Fail closed unless an independent oracle explicitly passes the same rows."""

    source_status = str((source_manifest or {}).get("conclusion", "SIGNAL_SOURCE_SEARCH_INCOMPLETE"))
    if not records:
        return {
            "verdict": "SIGNAL_LEDGER_CERTIFICATION_DISABLED",
            "records": [],
            "failures": [source_status, "NO_SIGNAL_ROWS"],
        }

    if not oracle_evidence:
        return {
            "verdict": "SIGNAL_LEDGER_CERTIFICATION_DISABLED",
            "records": records,
            "failures": ["INDEPENDENT_ORACLE_EVIDENCE_REQUIRED"],
        }

    if oracle_evidence.get("verdict") != "SIGNAL_LEDGER_ORACLE_PASS":
        return {
            "verdict": "SIGNAL_LEDGER_ORACLE_FAIL",
            "records": records,
            "failures": list(oracle_evidence.get("failures", ["ORACLE_DID_NOT_PASS"])),
        }

    expected_count = oracle_evidence.get("signal_count")
    if expected_count != len(records):
        return {
            "verdict": "SIGNAL_LEDGER_ORACLE_FAIL",
            "records": records,
            "failures": ["ORACLE_SIGNAL_COUNT_MISMATCH"],
        }

    return {
        "verdict": "SIGNAL_LEDGER_CERTIFIED",
        "records": records,
        "failures": [],
    }
