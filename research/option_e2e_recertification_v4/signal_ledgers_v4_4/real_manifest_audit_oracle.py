from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def audit_real_manifest_with_oracle(audit: dict[str, Any], *, path: Path) -> dict[str, Any]:
    failures: list[str] = []
    if audit.get("manifest_sha256") != _sha256_file(path):
        failures.append("MANIFEST_HASH_MISMATCH")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        parsed = None
        failures.append("MANIFEST_PARSE_FAILED")
    if isinstance(parsed, dict):
        required = {
            "provider",
            "capture_or_asof_timestamp",
            "source_data_file",
            "source_data_hash",
            "instrument_token",
            "trading_symbol",
            "underlying",
            "option_right",
            "strike",
            "expiry",
            "contract_source_relationship",
            "immutable_content_hash",
            "asof_not_after_event",
        }
        missing = sorted(required - set(parsed))
        if audit.get("missing_contract_identity_fields") != missing:
            failures.append("CONTRACT_FIELD_DERIVATION_MISMATCH")
        if missing:
            if audit.get("authority_tier") != "CURRENT_MASTER_DIAGNOSTIC_ONLY":
                failures.append("AUTHORITY_TIER_MISMATCH")
            if audit.get("blocker_code") != "MANIFEST_CONTRACT_IDENTITY_INCOMPLETE":
                failures.append("BLOCKER_MISMATCH")
        else:
            if audit.get("authority_tier") != "DATED_HISTORICAL_SNAPSHOT":
                failures.append("AUTHORITY_TIER_MISMATCH")
    else:
        if audit.get("parse_status") != "PARSE_FAILED":
            failures.append("PARSE_STATUS_MISMATCH")
    return {
        "verdict": "REAL_MANIFEST_AUDIT_ORACLE_PASSED" if not failures else "REAL_MANIFEST_AUDIT_ORACLE_FAILED",
        "failures": sorted(set(failures)),
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    audit_path = repo_root / "research/option_e2e_recertification_v4/signal_ledgers_v4_4/evidence/real_manifest_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    oracle = audit_real_manifest_with_oracle(audit, path=repo_root / "runtime/market_data/upstox/20260714/manifest.json")
    oracle_path = audit_path.with_name("real_manifest_audit_oracle.json")
    oracle_path.write_text(json.dumps(oracle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = _sha256_file(oracle_path)
    oracle_path.with_suffix(".json.sha256").write_text(f"{digest}  real_manifest_audit_oracle.json\n", encoding="utf-8")
    print(json.dumps(oracle, indent=2, sort_keys=True))
    return 0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
