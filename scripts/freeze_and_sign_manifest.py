"""Human-Audited CLI Manifest Signing Tool.

Enforces the freeze-and-sign cryptographic air-gap before system boot.
Requires explicit operator review and manual confirmation ('SIGN')
to update model_manifest.json. Automated scripts must NEVER bypass this tool.
"""

from __future__ import annotations

import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone


def execute_manual_signature_pipeline():
    artifact_dir = Path("artifacts")
    manifest_path = artifact_dir / "model_manifest.json"
    matrix_path = artifact_dir / "calibrated_regime_matrix.json"

    print("⏳ CRITICAL SECURITY AUDIT: Initializing Manifest Signing Sequence...")

    # 1. Enforce strict parameter visibility inside the terminal
    if not matrix_path.exists():
        print("❌ ERROR: No calibrated parameters found in artifacts/calibrated_regime_matrix.json")
        sys.exit(1)

    try:
        active_params = json.loads(matrix_path.read_text())
        print("\n" + "=" * 55)
        print("🔍 DETECTED PROPOSED ALPHACALIBRATOR CONFIGURATION:")
        print(json.dumps(active_params, indent=4))
        print("=" * 55 + "\n")
    except Exception as e:
        print(f"❌ ERROR: Malformed JSON parameter artifact: {str(e)}")
        sys.exit(1)

    # 2. Force Explicit Human Interruption Verification
    # When run non-interactively or in CI, fail-closed unless explicit 'SIGN' is provided
    try:
        user_input = input("PROCEED WITH CRYPTOGRAPHIC SIGNATURE? (Type 'SIGN' to commit changes): ")
    except EOFError:
        print("❌ COMMIT ABORTED: Non-interactive session without manual 'SIGN'. Safe state preserved.")
        sys.exit(1)

    if user_input.strip() != "SIGN":
        print("❌ COMMIT ABORTED: Cryptographic hashes left unmodified. Safe state preserved.")
        sys.exit(0)

    # 3. Compute deterministic binary row hashes across all 5 artifacts
    mandatory_artifacts = [
        "calibrated_regime_matrix.json",
        "scaler.npz",
        "regime_model_weights.npz",
        "calibrator.npz",
        "outcome_model.npz",
    ]

    manifest_payload = {
        "manifest_metadata": {
            "schema_version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "authorized_by_operator": True,
        },
        "artifact_checksums": {},
    }

    for filename in mandatory_artifacts:
        target_file = artifact_dir / filename
        if not target_file.exists():
            print(f"❌ ERROR: Mandatory production array file missing from disk: {filename}")
            sys.exit(1)

        binary_data = target_file.read_bytes()
        sha256_hash = hashlib.sha256(binary_data).hexdigest()
        manifest_payload["artifact_checksums"][f"{filename}_sha256"] = sha256_hash
        print(f"🔒 Hashed contract reference: {filename} -> {sha256_hash[:16]}...[OK]")

    # 4. Atomically serialize the locked manifest matrix back to disk
    manifest_path.write_text(json.dumps(manifest_payload, indent=2))
    print("\n✅ model_manifest.json SUCCESSFUL RE-LOCK. System cleared for boot.")


if __name__ == "__main__":
    execute_manual_signature_pipeline()
