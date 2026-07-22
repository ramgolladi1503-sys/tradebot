from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import canonical_hash, write_json_with_sidecar

CLASSIFICATIONS = {
    "KNOWN_DEVELOPMENT",
    "PREVIOUSLY_VIEWED",
    "VALIDATION_CONSUMED",
    "HOLDOUT_CONSUMED",
    "POTENTIALLY_UNSEEN",
    "PROSPECTIVE_SEALED",
}


class ProspectiveAccessError(PermissionError):
    pass


class ProspectiveDataGovernance:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.quarantine = self.root / "quarantine"
        self.sealed = self.root / "accepted-but-sealed"
        self.released = self.root / "released-for-confirmation"
        self.consumed = self.root / "consumed"
        for path in (self.quarantine, self.sealed, self.released, self.consumed):
            path.mkdir(parents=True, exist_ok=True)

    def enumerate_development_dates(self) -> list[str]:
        return []

    def read_development_file(self, path: str | Path) -> bytes:
        resolved = Path(path).resolve()
        sealed = self.sealed.resolve()
        if resolved == sealed or sealed in resolved.parents:
            raise ProspectiveAccessError("development code cannot read sealed prospective data")
        return resolved.read_bytes()

    def aggregate_strategy_dependent_stats(self) -> dict[str, Any]:
        raise ProspectiveAccessError("sealed outcomes are unavailable to development code")

    def schema_health(self) -> dict[str, Any]:
        return {
            "sealed_file_count": sum(1 for path in self.sealed.rglob("*") if path.is_file()),
            "zones": ["quarantine", "accepted-but-sealed", "released-for-confirmation", "consumed"],
        }

    def create_release(
        self,
        *,
        release_id: str,
        candidate_bundle_hash: str,
        strategy_code_commit: str,
        configuration_hash: str,
        date_range: list[str],
        purpose: str,
        authority: str,
    ) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", release_id):
            raise ValueError("release_id must be filesystem safe")
        payload = {
            "schema_version": "1.0",
            "release_id": release_id,
            "candidate_bundle_hash": candidate_bundle_hash,
            "strategy_code_commit": strategy_code_commit,
            "configuration_hash": configuration_hash,
            "release_date_range": date_range,
            "release_purpose": purpose,
            "approving_authority": authority,
            "consumed": False,
        }
        path = self.released / f"{release_id}.json"
        write_json_with_sidecar(path, payload)
        return path

    def consume_release(self, release_path: str | Path, *, candidate_bundle_hash: str) -> dict[str, Any]:
        path = Path(release_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("consumed"):
            raise ProspectiveAccessError("consumed release cannot be reused as fresh confirmation")
        if payload.get("candidate_bundle_hash") != candidate_bundle_hash:
            raise ProspectiveAccessError("release is tied to a different frozen candidate")
        payload["consumed"] = True
        payload["consumed_at"] = datetime.now(timezone.utc).isoformat()
        write_json_with_sidecar(self.consumed / path.name, payload)
        write_json_with_sidecar(path, payload)
        return payload


def build_exposure_ledger(repo_root: str | Path, manifest: list[dict[str, Any]], output_dir: str | Path, *, commit: str) -> dict[str, Any]:
    repo_root = Path(repo_root)
    output_dir = Path(output_dir)
    now = datetime.now(timezone.utc).isoformat()
    entries = []
    searchable = [
        path
        for base in ("research", "docs", "runtime")
        for path in (repo_root / base).rglob("*")
        if path.is_file() and path.stat().st_size < 2_000_000
    ]
    text_cache: dict[Path, str] = {}
    for row in manifest:
        date = str(row["trading_date"])
        instrument = str(row["instrument"])
        compact = date.replace("-", "")
        evidence_path = None
        classification = "PREVIOUSLY_VIEWED"
        evidence = "conservative historical classification; absence of proof is not unseen"
        for path in searchable:
            try:
                text = text_cache.setdefault(path, path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            if date in text or compact in text or str(row["filename"]) in text:
                evidence_path = str(path.relative_to(repo_root))
                evidence = "date or source filename appears in repository artifact"
                if "holdout" in evidence_path.lower():
                    classification = "HOLDOUT_CONSUMED"
                elif "validation" in evidence_path.lower():
                    classification = "VALIDATION_CONSUMED"
                else:
                    classification = "KNOWN_DEVELOPMENT"
                break
        entries.append(
            {
                "date": date,
                "instrument": instrument,
                "source": "KITE",
                "classification": classification,
                "evidence": evidence,
                "artifact_or_path": evidence_path,
                "timestamp": now,
                "governing_commit": commit,
                "classification_authority": "kite_five_minute_governed_discovery_v1",
                "source_file_sha256": row["sha256"],
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger = output_dir / "exposure_ledger.jsonl"
    ledger.write_text(
        "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries),
        encoding="utf-8",
    )
    ledger.with_name(ledger.name + ".sha256").write_text(
        f"{canonical_hash(entries)}  {ledger.name}\n",
        encoding="utf-8",
    )
    counts = Counter(entry["classification"] for entry in entries)
    manifest_payload = {
        "schema_version": "1.0",
        "entry_count": len(entries),
        "classification_counts": dict(sorted(counts.items())),
        "append_only": True,
        "governing_commit": commit,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json_with_sidecar(output_dir / "exposure_ledger_manifest.json", manifest_payload)
    report = output_dir / "exposure_report.md"
    lines = ["# Kite Five-Minute Exposure Report", "", "Historical dates are not classified as fresh confirmation by default.", ""]
    lines.extend(f"- {key}: {value}" for key, value in sorted(counts.items()))
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report.with_name(report.name + ".sha256").write_text(
        f"{canonical_hash(lines)}  {report.name}\n",
        encoding="utf-8",
    )
    return manifest_payload
