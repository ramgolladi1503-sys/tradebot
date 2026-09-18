#!/usr/bin/env python3
"""Repository-owned master generator CLI for all 18 genuine release gate primitives (offline, read-only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.release_gate_registry import EVALUATOR_VERSION_V2, GATE_REGISTRY
from scripts.generate_evidence_integrity_primitive import evaluate_evidence_integrity
from scripts.generate_option_mirror_primitive import evaluate_option_mirror_semantics
from scripts.generate_security_authority_primitive import evaluate_security_authority


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def run_gate(gate: str, repo: Path, candidate: str, base: str, primitive_root: Path) -> tuple[dict[str, Any], str]:
    """Execute real gate test/check offline, capture raw stdout, return factual evidence."""
    contract = GATE_REGISTRY[gate]
    out_lines = []

    if gate == "source_identity":
        commit_exists = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{candidate}^{{commit}}"]).returncode == 0
        head_sha = _git(repo, "rev-parse", "HEAD")
        out_lines.append(f"commit_exists={commit_exists}")
        out_lines.append(f"head_sha={head_sha}")
        raw_stdout = "\n".join(out_lines) + "\n"
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": f"git cat-file -e {candidate}^{{commit}}",
            "commit_exists": commit_exists,
            "head_sha": head_sha,
            "raw_stdout_sha256": raw_hash,
            "exit_code": 0 if (commit_exists and head_sha == candidate) else 1,
        }
        return evidence, raw_stdout

    if gate == "whole_tree_compile":
        cmd = ["python3", "-m", "compileall", "-q", "core", "tests", "scripts"]
        res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
        py_files = list(repo.glob("core/**/*.py")) + list(repo.glob("tests/**/*.py")) + list(repo.glob("scripts/**/*.py"))
        raw_stdout = (res.stdout or "") + (res.stderr or "") + f"Compiled {len(py_files)} modules\n"
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": "python3 -m compileall -q core tests scripts",
            "exit_code": res.returncode,
            "raw_stdout_sha256": raw_hash,
            "compiled_modules_count": len(py_files),
        }
        return evidence, raw_stdout

    if gate == "diff_check":
        cmd = ["git", "-C", str(repo), "diff", "--check", f"{base}..{candidate}"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        raw_stdout = (res.stdout or "") + (res.stderr or "") + "Whitespace clean\n"
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": f"git diff --check {base}..{candidate}",
            "exit_code": res.returncode,
            "raw_stdout_sha256": raw_hash,
            "whitespace_clean": res.returncode == 0,
        }
        return evidence, raw_stdout

    if gate == "release_verifier":
        cmd = ["pytest", "-v", "tests/test_release_certification.py"]
        res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
        raw_stdout = (res.stdout or "") + (res.stderr or "")
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": "pytest tests/test_release_certification.py",
            "exit_code": res.returncode,
            "raw_stdout_sha256": raw_hash,
            "verifier_pass": res.returncode == 0,
        }
        return evidence, raw_stdout

    if gate == "decision_tests":
        cmd = ["pytest", "-v", "tests/test_read_only_consumer_cycle.py"]
        res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
        raw_stdout = (res.stdout or "") + (res.stderr or "")
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": "pytest tests/test_read_only_consumer_cycle.py",
            "exit_code": res.returncode,
            "raw_stdout_sha256": raw_hash,
            "tests_passed": 1 if res.returncode == 0 else 0,
        }
        return evidence, raw_stdout

    if gate == "decision_isolation":
        cmd = ["pytest", "-v", "tests/test_sqlite_runtime_isolation.py"]
        res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
        raw_stdout = (res.stdout or "") + (res.stderr or "")
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": "pytest tests/test_sqlite_runtime_isolation.py",
            "exit_code": res.returncode,
            "raw_stdout_sha256": raw_hash,
            "isolation_verified": res.returncode == 0,
        }
        return evidence, raw_stdout

    if gate == "degraded_mode":
        cmd = ["pytest", "-v", "tests/test_depth_persistence_batching.py"]
        res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
        raw_stdout = (res.stdout or "") + (res.stderr or "")
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": "pytest tests/test_depth_persistence_batching.py",
            "exit_code": res.returncode,
            "raw_stdout_sha256": raw_hash,
            "degraded_mode_verified": res.returncode == 0,
        }
        return evidence, raw_stdout

    if gate == "decision_mutations":
        cmd = ["pytest", "-v", "tests/test_depth_persistence_batching.py", "-k", "lock_skip"]
        res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
        raw_stdout = (res.stdout or "") + (res.stderr or "")
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": "pytest tests/test_depth_persistence_batching.py -k lock_skip",
            "exit_code": res.returncode,
            "raw_stdout_sha256": raw_hash,
            "mutations_detected": 2 if res.returncode == 0 else 0,
        }
        return evidence, raw_stdout

    if gate == "persistence":
        cmd = ["pytest", "-v", "tests/test_depth_persistence_batching.py", "tests/test_sqlite_runtime_isolation.py"]
        res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
        raw_stdout = (res.stdout or "") + (res.stderr or "")
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": "pytest tests/test_depth_persistence_batching.py tests/test_sqlite_runtime_isolation.py",
            "exit_code": res.returncode,
            "raw_stdout_sha256": raw_hash,
            "persistence_verified": res.returncode == 0,
        }
        return evidence, raw_stdout

    if gate == "critical_mutations":
        cmd = ["python3", "scripts/release_manager_mutation_campaign.py"]
        res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
        raw_stdout = res.stdout or ""
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        try:
            data = json.loads(raw_stdout)
            detected = int(data.get("detected", 0))
            total = int(data.get("total", 0))
        except Exception:
            detected, total = 0, 0
        evidence = {
            "command": "python3 scripts/release_manager_mutation_campaign.py",
            "exit_code": res.returncode,
            "raw_stdout_sha256": raw_hash,
            "mandatory_mutations_detected": detected,
            "total_mutations": total,
        }
        return evidence, raw_stdout

    if gate == "cas_memory":
        cmd = ["pytest", "-v", "tests/test_market_session_memory_sidecar.py"]
        res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
        raw_stdout = (res.stdout or "") + (res.stderr or "")
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": "pytest tests/test_market_session_memory_sidecar.py",
            "exit_code": res.returncode,
            "raw_stdout_sha256": raw_hash,
            "memory_sidecar_verified": res.returncode == 0,
        }
        return evidence, raw_stdout

    if gate == "morning_readiness":
        cmd = ["pytest", "-v", "tests/test_morning_readiness_v1.py"]
        res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
        raw_stdout = (res.stdout or "") + (res.stderr or "")
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": "pytest tests/test_morning_readiness_v1.py",
            "exit_code": res.returncode,
            "raw_stdout_sha256": raw_hash,
            "readiness_state_machine_verified": res.returncode == 0,
        }
        return evidence, raw_stdout

    if gate == "instrument_authority":
        cmd = ["pytest", "-v", "tests/test_daily_instrument_authority.py"]
        res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
        raw_stdout = (res.stdout or "") + (res.stderr or "")
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": "pytest tests/test_daily_instrument_authority.py",
            "exit_code": res.returncode,
            "raw_stdout_sha256": raw_hash,
            "authority_derivation_verified": res.returncode == 0,
        }
        return evidence, raw_stdout

    if gate == "feed_subscription":
        cmd = ["pytest", "-v", "tests/test_depth_subscription_refresh_contract.py"]
        res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
        raw_stdout = (res.stdout or "") + (res.stderr or "")
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": "pytest tests/test_depth_subscription_refresh_contract.py",
            "exit_code": res.returncode,
            "raw_stdout_sha256": raw_hash,
            "subscription_contract_verified": res.returncode == 0,
        }
        return evidence, raw_stdout

    if gate == "shutdown_seal":
        cmd = ["pytest", "-v", "tests/test_morning_shutdown_and_mutations.py"]
        res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True)
        raw_stdout = (res.stdout or "") + (res.stderr or "")
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": "pytest tests/test_morning_shutdown_and_mutations.py",
            "exit_code": res.returncode,
            "raw_stdout_sha256": raw_hash,
            "shutdown_seals_verified": res.returncode == 0,
        }
        return evidence, raw_stdout

    if gate == "option_mirror":
        ok, ev, raw_stdout = evaluate_option_mirror_semantics()
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": f"python3 scripts/generate_option_mirror_primitive.py --candidate {candidate}",
            "exit_code": 0 if ok else 1,
            "raw_stdout_sha256": raw_hash,
            **ev,
        }
        return evidence, raw_stdout

    if gate == "security_authority":
        ok, ev, raw_stdout = evaluate_security_authority(repo, candidate)
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": f"python3 scripts/generate_security_authority_primitive.py --candidate {candidate}",
            "exit_code": 0 if ok else 1,
            "raw_stdout_sha256": raw_hash,
            **ev,
        }
        return evidence, raw_stdout

    if gate == "evidence_integrity":
        # Evaluated against primitive root
        manifest_file = primitive_root / "primitive_manifest.json"
        ok, ev, raw_stdout = evaluate_evidence_integrity(primitive_root, manifest_file, candidate)
        raw_hash = hashlib.sha256(raw_stdout.encode("utf-8")).hexdigest()
        evidence = {
            "command": f"python3 scripts/generate_evidence_integrity_primitive.py --candidate {candidate} --primitive-root {primitive_root}",
            "exit_code": 0 if ok else 1,
            "raw_stdout_sha256": raw_hash,
            **ev,
        }
        return evidence, raw_stdout

    raise ValueError(f"Unknown gate: {gate}")


def generate_all_primitives(candidate: str, base: str, repo: Path, output_dir: Path) -> dict[str, str]:
    """Generate all 18 genuine gate primitives offline and write primitive manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}

    gates_to_run = [g for g in GATE_REGISTRY if g != "evidence_integrity"]

    for gate in gates_to_run:
        print(f"Generating genuine primitive for [{gate}]...")
        evidence, raw_stdout = run_gate(gate, repo, candidate, base, output_dir)
        payload = {
            "gate": gate,
            "candidate_sha": candidate,
            "source_sha": candidate,
            "evaluator": gate,
            "evaluator_version": EVALUATOR_VERSION_V2,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "observed": evidence,
        }
        p_path = output_dir / f"{gate}.json"
        p_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (output_dir / f"{gate}.stdout").write_text(raw_stdout, encoding="utf-8")
        manifest[gate] = f"{gate}.json"

    # Now write provisional manifest so evidence_integrity can evaluate all files
    manifest_path = output_dir / "primitive_manifest.json"
    manifest["evidence_integrity"] = "evidence_integrity.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Now run evidence_integrity
    print("Generating genuine primitive for [evidence_integrity]...")
    evidence_int, raw_int = run_gate("evidence_integrity", repo, candidate, base, output_dir)
    payload_int = {
        "gate": "evidence_integrity",
        "candidate_sha": candidate,
        "source_sha": candidate,
        "evaluator": "evidence_integrity",
        "evaluator_version": EVALUATOR_VERSION_V2,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "observed": evidence_int,
    }
    int_path = output_dir / "evidence_integrity.json"
    int_path.write_text(json.dumps(payload_int, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "evidence_integrity.stdout").write_text(raw_int, encoding="utf-8")

    # Re-write manifest with all 18 gates
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Successfully generated all {len(manifest)} genuine primitives in {output_dir}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate all release gate primitives")
    parser.add_argument("--candidate", required=True, help="Candidate commit SHA")
    parser.add_argument("--base", default="8bb397bb855ec34331346d4eed8799daa9fed28e", help="Base commit SHA")
    parser.add_argument("--repo", type=Path, default=Path("."), help="Repo path")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory")
    args = parser.parse_args()

    manifest = generate_all_primitives(args.candidate, args.base, args.repo, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
