from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .real_manifest_audit_oracle import audit_real_manifest_with_oracle


MANIFEST_PATH = Path("runtime/market_data/upstox/20260714/manifest.json")
OUT_DIR = Path("research/option_e2e_recertification_v4/signal_ledgers_v4_4/evidence")


def build_audit(repo_root: Path) -> dict[str, Any]:
    path = repo_root / MANIFEST_PATH
    result: dict[str, Any] = {
        "manifest_path": str(MANIFEST_PATH),
        "manifest_sha256": _sha256_file(path) if path.exists() else "",
        "parse_status": "PARSE_FAILED",
        "provider": "",
        "capture_or_asof_ts": "",
        "referenced_source_files": [],
        "referenced_source_hashes": [],
        "observed_contract_identity_fields": [],
        "missing_contract_identity_fields": [],
        "current_master_used": False,
        "authority_tier": "CURRENT_MASTER_DIAGNOSTIC_ONLY",
        "blocker_code": "MANIFEST_CONTRACT_IDENTITY_INCOMPLETE",
        "research_only": True,
        "allowed_for_live_execution": False,
        "broker_api_called": False,
        "is_order_action": False,
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result["parse_status"] = "PARSE_OK"
        result["provider"] = str(payload.get("provider") or "")
        result["capture_or_asof_ts"] = str(payload.get("capture_or_asof_timestamp") or payload.get("finalized_at") or "")
        result["current_master_used"] = bool(payload.get("current_master_used"))
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
        observed = [field for field in required if field in payload]
        missing = sorted(required - set(observed))
        result["observed_contract_identity_fields"] = sorted(observed)
        result["missing_contract_identity_fields"] = missing
        if not missing:
            result["authority_tier"] = "DATED_HISTORICAL_SNAPSHOT"
            result["blocker_code"] = ""
        result["referenced_source_files"] = [str(payload.get("source_data_file") or "")]
        result["referenced_source_hashes"] = [str(payload.get("source_data_hash") or "")]
    except Exception:
        pass
    oracle = audit_real_manifest_with_oracle(result, path=path)
    result["oracle_verdict"] = oracle["verdict"]
    result["oracle_failures"] = oracle["failures"]
    return result


def write_audit(repo_root: Path, audit: dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = repo_root / OUT_DIR / "real_manifest_audit.json"
    path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = _sha256_file(path)
    (path.with_suffix(".json.sha256")).write_text(f"{digest}  real_manifest_audit.json\n", encoding="utf-8")
    summary = repo_root / OUT_DIR / "real_manifest_audit_summary.md"
    summary.write_text(
        "\n".join(
            [
                "# Real Manifest Audit Summary",
                "",
                f"- manifest_path: `{audit['manifest_path']}`",
                f"- parse_status: `{audit['parse_status']}`",
                f"- authority_tier: `{audit['authority_tier']}`",
                f"- blocker_code: `{audit['blocker_code']}`",
                f"- oracle_verdict: `{audit['oracle_verdict']}`",
                f"- missing_contract_identity_fields: `{', '.join(audit['missing_contract_identity_fields']) or 'none'}`",
                "",
                "This audit is research-only and does not prove corpus-wide historical authority.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    audit = build_audit(repo_root)
    write_audit(repo_root, audit)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
