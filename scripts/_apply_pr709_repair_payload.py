#!/usr/bin/env python3
"""Apply the allow-listed PR #709 repair payload staged as text chunks."""

from __future__ import annotations

import base64
import hashlib
import io
import tarfile
from pathlib import Path, PurePosixPath

EXPECTED_SHA256 = "4b5434c00dd50f324252206c9923a26aaca43f48327d5b44e1083a67c6aaef0c"
ALLOWED_PATHS = {
    "research/constituent_lead_lag/bar_grid.py",
    "research/constituent_lead_lag/model.py",
    "research/constituent_lead_lag/unweighted.py",
    "research/constituent_lead_lag/evidence_controls.py",
    "research/constituent_lead_lag/proxy_weights.py",
    "research/constituent_lead_lag/__init__.py",
    "scripts/calculate_proxy_membership_coverage.py",
    "scripts/audit_proxy_campaign_bars.py",
    "scripts/run_reconstructed_weight_proxy_research.py",
    "scripts/audit_reconstructed_proxy_evidence.py",
    "tests/research/test_certification_repair.py",
    "tests/research/test_reconstructed_proxy_oracle.py",
}


def _patch_oracle_legacy_signature(root: Path) -> None:
    """Keep old callers fail-closed without weakening the v3 oracle."""
    path = root / "scripts" / "audit_reconstructed_proxy_evidence.py"
    text = path.read_text(encoding="utf-8")
    old = "def audit(campaign_root: Path, output_dir: Path) -> dict[str, object]:"
    if old not in text:
        raise SystemExit("cannot locate v3 oracle audit definition")
    text = text.replace(
        old,
        "def _audit_v3(campaign_root: Path, output_dir: Path) -> dict[str, object]:",
        1,
    )
    compatibility = r'''


def _audit_legacy(
    evaluation_dir: Path,
    bars: Path,
    output_dir: Path,
    coverage_dir: Path | None = None,
) -> dict[str, object]:
    """Diagnose old bundles, which are never sufficient for v3 certification."""
    output_dir.mkdir(parents=True, exist_ok=True)
    checks: dict[str, bool] = {}
    errors: list[str] = []
    try:
        bars_df = read_table(bars)
        state_path = evaluation_dir / "signal_states_weighted.parquet"
        if not state_path.exists():
            state_path = evaluation_dir / "signal_states_weighted.csv"
        states = read_table(state_path)
        sessions = int(bars_df["session"].astype(str).nunique()) if "session" in bars_df else 0
        state_rows = int(len(states))
        reason_counts = (
            {str(k): int(v) for k, v in states["reason"].astype(str).value_counts().to_dict().items()}
            if "reason" in states
            else {}
        )
        _check(checks, "state_count_bound", state_rows <= sessions * 10)
        _check(checks, "reason_count_sum", sum(reason_counts.values()) == state_rows)
        _check(checks, "pre_outcome_freeze_present", (evaluation_dir / "pre_outcome_freeze.json").is_file())
        _check(checks, "artifact_manifest_present", (evaluation_dir / "artifact_manifest.json").is_file())
        _check(checks, "summary_present", (evaluation_dir / "summary.json").is_file())
        _check(
            checks,
            "coverage_present",
            coverage_dir is not None
            and (coverage_dir / "membership_coverage_summary.json").is_file(),
        )
        report = {
            "verdict": "FAIL",
            "certification_status": "LEGACY_BUNDLE_NOT_CERTIFIABLE",
            "checks": checks,
            "errors": errors,
            "bars_sha256": sha256(bars),
            "sessions": sessions,
            "state_rows": state_rows,
            "reason_counts": reason_counts,
            "oracle_imports_strategy": False,
            "research_only": True,
            "allowed_for_live_execution": False,
        }
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        report = {
            "verdict": "FAIL",
            "certification_status": "LEGACY_BUNDLE_NOT_CERTIFIABLE",
            "checks": checks,
            "errors": errors,
            "oracle_imports_strategy": False,
            "research_only": True,
            "allowed_for_live_execution": False,
        }
    (output_dir / "oracle_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    return report


def audit(*args: object, **kwargs: object) -> dict[str, object]:
    """Audit v3 campaigns, with fail-closed support for the old call shape."""
    if len(args) == 2 and not kwargs:
        return _audit_v3(Path(args[0]), Path(args[1]))
    if len(args) in {3, 4} and not kwargs:
        coverage_dir = Path(args[3]) if len(args) == 4 and args[3] is not None else None
        return _audit_legacy(Path(args[0]), Path(args[1]), Path(args[2]), coverage_dir)
    if {"campaign_root", "output_dir"}.issubset(kwargs):
        return _audit_v3(Path(kwargs["campaign_root"]), Path(kwargs["output_dir"]))
    raise TypeError(
        "audit expects (campaign_root, output_dir) or legacy "
        "(evaluation_dir, bars, output_dir[, coverage_dir])"
    )
'''
    marker = "\n\ndef main() -> int:\n"
    if marker not in text:
        raise SystemExit("cannot locate oracle main definition")
    path.write_text(text.replace(marker, compatibility + marker, 1), encoding="utf-8")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    chunk_dir = root / "scripts" / ".pr709_payload"
    chunks = sorted(chunk_dir.glob("chunk_*.txt"))
    if len(chunks) != 8:
        raise SystemExit(f"expected 8 payload chunks, found {len(chunks)}")

    encoded = "".join(path.read_text(encoding="utf-8").strip() for path in chunks)
    archive = base64.b64decode(encoded, validate=True)
    actual_hash = hashlib.sha256(archive).hexdigest()
    if actual_hash != EXPECTED_SHA256:
        raise SystemExit(f"payload hash mismatch: {actual_hash}")

    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        members = bundle.getmembers()
        member_paths = {member.name for member in members}
        if member_paths != ALLOWED_PATHS:
            raise SystemExit(
                f"payload path mismatch: missing={sorted(ALLOWED_PATHS - member_paths)}, "
                f"unexpected={sorted(member_paths - ALLOWED_PATHS)}"
            )
        for member in members:
            pure = PurePosixPath(member.name)
            if pure.is_absolute() or ".." in pure.parts:
                raise SystemExit(f"unsafe payload path: {member.name}")
            if not member.isfile() or member.issym() or member.islnk():
                raise SystemExit(f"unsupported payload member: {member.name}")
            source = bundle.extractfile(member)
            if source is None:
                raise SystemExit(f"cannot read payload member: {member.name}")
            target = root / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read())

    _patch_oracle_legacy_signature(root)
    print(f"applied {len(ALLOWED_PATHS)} PR #709 repair files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
