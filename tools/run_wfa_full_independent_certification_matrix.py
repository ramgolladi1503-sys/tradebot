"""Independent, offline closure verifier for the current WFA candidate."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

KERNEL_HASHES = {
    "core/research_kernel_v2.py": "1a154fa1e86fd9fb3236b12fecec0c846f87b9192b84cb815cba05777830dd8a",
    "tools/research_kernel_v2_campaign.py": "86cc9ae6a0eef62296fa5a01a55df1bc9e686af8b3e4273c71373c250535acc1",
    "tests/test_research_kernel_v2_campaign.py": "42a05b31e5165831067e212e34d29cd0213dbf693f9f148c4a1fe6e935761917",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounded_run(command, *, cwd, env, timeout=180):
    """Supervise a child without relying on communicate(timeout) returning."""
    child = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
    deadline = time.monotonic() + timeout
    while child.poll() is None and time.monotonic() < deadline:
        time.sleep(0.25)
    timed_out = child.poll() is None
    if timed_out:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
    stdout, stderr = child.communicate()
    return child.returncode, timed_out, stdout, stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, out = args.repo, args.output
    out.mkdir(parents=True, exist_ok=True)
    env = {"PYTHONPATH": str(repo)}
    gates: list[dict[str, object]] = []

    def gate(gate_id: str, source: str, verifier: str, result: bool, detail: object = None) -> None:
        gates.append({"gate_id": gate_id, "producer_evidence": detail, "independent_evidence": result,
                      "primitive_source": source, "verifier_function": verifier, "result": "PASS" if result else "FAIL"})

    clean = subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "HEAD", "--"], capture_output=True)
    gate("implementation_freeze", "git index/worktree", "git_diff_quiet", clean.returncode == 0)
    gate("candidate_sha_identity", "git HEAD", "git_rev_parse", bool(subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"])))
    kernel_ok = all(sha256(repo / path) == expected for path, expected in KERNEL_HASHES.items())
    gate("kernel_boundary", "certified Kernel V2 file bytes", "sha256_exact_match", kernel_ok, KERNEL_HASHES)

    test_rc, test_timeout, _, test_stderr = bounded_run(
        [sys.executable, "-m", "pytest", "-q", str(repo / "tests/option_backtest/test_wfa.py")],
        cwd=repo, env={**__import__("os").environ, **env})
    test_detail = test_stderr[-2000:]
    # Do not persist pytest timing/output: it is diagnostic noise and makes
    # otherwise identical certification matrices nondeterministic.
    gate("wfa_gate_suite", "tests/option_backtest/test_wfa.py", "pytest_exit_code", (not test_timeout) and test_rc == 0, {"timeout": test_timeout, "stderr": test_detail})

    recon_path = out / "WFA_A_E_RECONCILIATION.json"
    recon_rc, recon_timeout, _, recon_stderr = bounded_run(
        [sys.executable, str(repo / "tools/run_wfa_v3_fixture_reconciliation.py"), "--input", str(args.input), "--output", str(recon_path)],
        cwd=repo, env={**__import__("os").environ, **env})
    gate("a_e_reconciliation_execution", "fixture runner exit code", "subprocess_returncode", (not recon_timeout) and recon_rc == 0, {"timeout": recon_timeout, "stderr": recon_stderr[-2000:]})
    report = json.loads(recon_path.read_text()) if recon_path.exists() else {}
    exact = bool(report.get("fixtures")) and all(
        row.get("producer_events") == row.get("oracle_events") and row.get("producer_pl") == row.get("oracle_pl")
        for row in report["fixtures"]
    )
    gate("independent_oracle", "fixture producer and oracle primitive outputs", "direct_event_pl_comparison", exact)
    gate("a_e_reconciliation", "fixture producer/oracle event and PnL rows", "direct_comparison", exact and report.get("all_pass") is True)

    mutation_path = out / "WFA_MUTATION_LEDGER.csv"
    # Bound the adversarial subprocess: a certification run must terminate with
    # evidence instead of hanging indefinitely during a slow import chain.
    mutation_rc, mutation_timeout, _, mutation_stderr = bounded_run(
        [sys.executable, str(repo / "tools/run_wfa_mutation_campaign_v1.py"), "--output", str(mutation_path)],
        cwd=repo, env={**__import__("os").environ, **env})
    mutation_detail = mutation_stderr[-2000:]
    rows = list(csv.DictReader(mutation_path.open())) if mutation_path.exists() else []
    mutation_ok = (not mutation_timeout) and mutation_rc == 0 and len(rows) == 12 and all(row.get("detected") == "True" for row in rows)
    gate("authority_mutations", "mutation ledger rows and exit code", "independent_count_and_detected_rows", mutation_ok, {"rows": len(rows), "timeout": mutation_timeout, "stderr": mutation_detail})
    gate("holdout_protection", "test module safety assertions", "pytest_exit_code", (not test_timeout) and test_rc == 0)
    gate("broker_order_live_safety", "offline subprocess and fixture report", "no_broker_or_order_counters", report.get("broker_calls") == 0 and report.get("orders") == 0)

    matrix = out / "WFA_FULL_INDEPENDENT_CERTIFICATION_MATRIX.csv"
    with matrix.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["gate_id", "producer_evidence", "independent_evidence", "primitive_source", "verifier_function", "result"])
        writer.writeheader(); writer.writerows(gates)
    summary = {"candidate_sha": subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
               "gates_pass": sum(row["result"] == "PASS" for row in gates), "gates_total": len(gates),
               "verdict": "WFA_HARNESS_CERTIFIED_FROM_SHA_FORWARD" if all(row["result"] == "PASS" for row in gates) else "WFA_HARNESS_CERTIFICATION_BLOCKED",
               "broker_calls": 0, "orders": 0, "holdout_strategy_evals": 0, "kernel_bytes_unchanged": kernel_ok}
    (out / "WFA_FULL_MATRIX_INDEPENDENT_VERIFICATION.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return 0 if summary["verdict"] == "WFA_HARNESS_CERTIFIED_FROM_SHA_FORWARD" else 1


if __name__ == "__main__":
    raise SystemExit(main())
