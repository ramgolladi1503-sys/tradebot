"""
TradeBot Heritage Manifest Resolver (Stage 2 GSD Implementation under ARCH-01)

Formal Invariant Contracts:
- Invariant I-1: Calendar-aware predecessor discovery (up to 10 days scan using NSE calendar).
- Invariant I-2: Cryptographic manifest sealing & independent verification via verify_market_heritage_manifest.
- Invariant I-5: Strictly read-only, is_order_action=false, broker_api_called=false, allowed_for_live_execution=false.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.market_calendar import IN_HOLIDAYS


def verify_market_heritage_manifest(
    manifest_path: Path | str,
    decision_epoch: float | None = None,
) -> dict[str, Any]:
    """Verify cryptographic integrity, schema structure, and sealing of a market heritage manifest."""
    p = Path(manifest_path)
    if not p.is_file():
        return {
            "verdict": "FAIL",
            "errors": [f"File does not exist: {p}"],
            "manifest_sha256": None,
        }

    try:
        content_bytes = p.read_bytes()
        digest = hashlib.sha256(content_bytes).hexdigest()
        data = json.loads(content_bytes.decode("utf-8"))
    except Exception as exc:
        return {
            "verdict": "FAIL",
            "errors": [f"Unparseable manifest JSON: {exc}"],
            "manifest_sha256": None,
        }

    errors: list[str] = []
    if not isinstance(data, dict):
        errors.append("Manifest root must be a JSON object")
        return {"verdict": "FAIL", "errors": errors, "manifest_sha256": digest}

    # Verify required keys
    for req_key in ("session_date", "exchange"):
        if req_key not in data:
            errors.append(f"Missing required key: {req_key}")

    # Check embedded hash if present
    embedded_hash = data.get("manifest_sha256") or data.get("canonical_sha256")
    if embedded_hash and str(embedded_hash) != digest:
        errors.append(f"Embedded hash mismatch: {embedded_hash} != {digest}")

    verdict = "PASS" if not errors else "FAIL"
    return {
        "verdict": verdict,
        "errors": errors,
        "manifest_sha256": digest,
        "session_date": data.get("session_date"),
    }


class ResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    NO_PREDECESSOR_FOUND = "NO_PREDECESSOR_FOUND"
    MANIFEST_NOT_FOUND = "MANIFEST_NOT_FOUND"
    MANIFEST_VERIFICATION_FAILED = "MANIFEST_VERIFICATION_FAILED"
    CORRUPT_MANIFEST = "CORRUPT_MANIFEST"
    AMBIGUOUS_MANIFEST = "AMBIGUOUS_MANIFEST"


@dataclass(frozen=True)
class HeritageManifestResolution:
    status: ResolutionStatus
    manifest_path: Path | None
    manifest_sha256: str | None
    target_date: str
    predecessor_date: str | None
    verification_report: dict[str, Any] | None
    error_message: str | None = None
    read_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    allowed_for_live_execution: bool = False


class HeritageManifestResolver:
    """Discovers and independently verifies predecessor T-1 market heritage manifests."""

    @staticmethod
    def find_predecessor_date(
        target_date: str | dt.date,
        max_lookback_days: int = 10,
    ) -> dt.date | None:
        """Scan backward day-by-day from target_date - 1 up to max_lookback_days,

        skipping weekends and official NSE F&O holidays (Invariant I-1).
        """
        if isinstance(target_date, str):
            curr = dt.date.fromisoformat(target_date)
        else:
            curr = target_date

        for step in range(1, max_lookback_days + 1):
            candidate = curr - dt.timedelta(days=step)
            # Monday is 0, Sunday is 6. Weekends are 5 and 6.
            if candidate.weekday() >= 5:
                continue
            if candidate in IN_HOLIDAYS:
                continue
            return candidate

        return None

    @classmethod
    def resolve(
        cls,
        target_date: str,
        search_roots: Sequence[Path | str],
        run_id: str | None = None,
        decision_epoch: float | None = None,
        max_lookback_days: int = 10,
    ) -> HeritageManifestResolution:
        """Resolve and verify the predecessor session's heritage manifest."""
        predecessor_date_obj = cls.find_predecessor_date(
            target_date, max_lookback_days=max_lookback_days
        )
        if predecessor_date_obj is None:
            return HeritageManifestResolution(
                status=ResolutionStatus.NO_PREDECESSOR_FOUND,
                manifest_path=None,
                manifest_sha256=None,
                target_date=target_date,
                predecessor_date=None,
                verification_report=None,
                error_message=f"No valid trading predecessor found within {max_lookback_days} days.",
            )

        predecessor_date_str = predecessor_date_obj.isoformat()
        candidate_paths: list[Path] = []

        # Candidate discovery patterns across search roots
        for raw_root in search_roots:
            root = Path(raw_root)
            if not root.exists():
                continue

            # 1. Direct session folders: session_{predecessor_date_str} or sessions/session_{predecessor_date_str}
            possible_session_dirs = [
                root / f"session_{predecessor_date_str}",
                root / "sessions" / f"session_{predecessor_date_str}",
            ]
            for session_dir in possible_session_dirs:
                if session_dir.is_dir():
                    # Direct manifests inside session folder
                    for name in (
                        "heritage_manifest.json",
                        "manifest.json",
                        f"heritage_manifest_{predecessor_date_str}.json",
                    ):
                        p = session_dir / name
                        if p.is_file() and p not in candidate_paths:
                            candidate_paths.append(p)

                    # Nested run subfolders
                    for child in session_dir.iterdir():
                        if child.is_dir():
                            for name in ("heritage_manifest.json", "manifest.json"):
                                p = child / name
                                if p.is_file() and p not in candidate_paths:
                                    candidate_paths.append(p)

            # 2. Dedicated heritage archive root
            heritage_dir = root / "heritage"
            if heritage_dir.is_dir():
                for p in heritage_dir.glob(f"*{predecessor_date_str}*.json"):
                    if p.is_file() and p not in candidate_paths:
                        candidate_paths.append(p)

            # 3. Direct files in root
            for name in (
                f"heritage_manifest_{predecessor_date_str}.json",
                f"manifest_{predecessor_date_str}.json",
            ):
                p = root / name
                if p.is_file() and p not in candidate_paths:
                    candidate_paths.append(p)

        if not candidate_paths:
            return HeritageManifestResolution(
                status=ResolutionStatus.MANIFEST_NOT_FOUND,
                manifest_path=None,
                manifest_sha256=None,
                target_date=target_date,
                predecessor_date=predecessor_date_str,
                verification_report=None,
                error_message=f"No manifest file found for predecessor session {predecessor_date_str}.",
            )

        # Ambiguity resolution if run_id provided
        selected_path: Path | None = None
        if len(candidate_paths) == 1:
            selected_path = candidate_paths[0]
        elif run_id:
            for p in candidate_paths:
                if run_id in str(p):
                    selected_path = p
                    break

        if selected_path is None:
            # Check if all candidate paths are byte-identical
            hashes = set()
            for p in candidate_paths:
                try:
                    hashes.add(hashlib.sha256(p.read_bytes()).hexdigest())
                except Exception:
                    pass
            if len(hashes) == 1:
                selected_path = candidate_paths[0]
            else:
                return HeritageManifestResolution(
                    status=ResolutionStatus.AMBIGUOUS_MANIFEST,
                    manifest_path=None,
                    manifest_sha256=None,
                    target_date=target_date,
                    predecessor_date=predecessor_date_str,
                    verification_report=None,
                    error_message=f"Multiple ambiguous manifests found for predecessor session {predecessor_date_str}: {[str(p) for p in candidate_paths]}",
                )

        # Invariant I-2: Cryptographic validation & verify_market_heritage_manifest
        try:
            content_bytes = selected_path.read_bytes()
            computed_sha256 = hashlib.sha256(content_bytes).hexdigest()
            manifest_data = json.loads(content_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return HeritageManifestResolution(
                status=ResolutionStatus.CORRUPT_MANIFEST,
                manifest_path=selected_path,
                manifest_sha256=None,
                target_date=target_date,
                predecessor_date=predecessor_date_str,
                verification_report=None,
                error_message=f"Manifest at {selected_path} is corrupt or not valid JSON.",
            )
        except Exception as exc:
            return HeritageManifestResolution(
                status=ResolutionStatus.CORRUPT_MANIFEST,
                manifest_path=selected_path,
                manifest_sha256=None,
                target_date=target_date,
                predecessor_date=predecessor_date_str,
                verification_report=None,
                error_message=f"Failed to read manifest at {selected_path}: {exc}",
            )

        # Run independent verifier
        try:
            report = verify_market_heritage_manifest(
                selected_path, decision_epoch=decision_epoch
            )
        except Exception as exc:
            return HeritageManifestResolution(
                status=ResolutionStatus.MANIFEST_VERIFICATION_FAILED,
                manifest_path=selected_path,
                manifest_sha256=computed_sha256,
                target_date=target_date,
                predecessor_date=predecessor_date_str,
                verification_report=None,
                error_message=f"Verifier raised exception: {exc}",
            )

        if report.get("verdict") != "PASS":
            return HeritageManifestResolution(
                status=ResolutionStatus.MANIFEST_VERIFICATION_FAILED,
                manifest_path=selected_path,
                manifest_sha256=computed_sha256,
                target_date=target_date,
                predecessor_date=predecessor_date_str,
                verification_report=report,
                error_message=f"Verifier returned non-PASS verdict ({report.get('verdict')}): {report.get('errors')}",
            )

        # Ensure sha256 in report matches computed_sha256
        report_sha = report.get("manifest_sha256")
        if report_sha and report_sha != computed_sha256:
            return HeritageManifestResolution(
                status=ResolutionStatus.MANIFEST_VERIFICATION_FAILED,
                manifest_path=selected_path,
                manifest_sha256=computed_sha256,
                target_date=target_date,
                predecessor_date=predecessor_date_str,
                verification_report=report,
                error_message=f"SHA-256 digest mismatch between verifier ({report_sha}) and computed ({computed_sha256}).",
            )

        return HeritageManifestResolution(
            status=ResolutionStatus.RESOLVED,
            manifest_path=selected_path.resolve(),
            manifest_sha256=computed_sha256,
            target_date=target_date,
            predecessor_date=predecessor_date_str,
            verification_report=report,
            error_message=None,
        )
