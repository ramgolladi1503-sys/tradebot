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

    print(f"applied {len(ALLOWED_PATHS)} PR #709 repair files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
