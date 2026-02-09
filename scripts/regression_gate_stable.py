import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(cmd, next_action=None):
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode == 0:
        print(f"PASS: {' '.join(cmd)}")
        return True
    print(f"FAIL: {' '.join(cmd)}")
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    lines = [l for l in out.splitlines() if l.strip()]
    tail = lines[-50:] if lines else []
    print("---- last 50 lines ----")
    for l in tail:
        print(l)
    print("NEXT ACTION:", next_action or "inspect command output")
    return False


def main():
    steps = [
        (["python", "-m", "compileall", "."], "fix syntax/import errors"),
        (["python", "-m", "pytest", "-q"], "review failing tests"),
        (["python", "scripts/regression_gate_12_14.py"], "inspect phase 12-14 gates"),
        (["python", "scripts/run_pilot_checklist.py", "--dry-run"], "review pilot checklist reasons"),
        (["python", "scripts/sla_check.py"], "verify epoch fields in DB"),
        (["python", "scripts/verify_audit_chain.py"], "verify audit chain integrity"),
        (["python", "scripts/verify_risk_units.py"], "risk unit mismatch"),
        (["python", "scripts/verify_desk_paths.py"], "desk config paths"),
        (["python", "scripts/verify_feed_sla.py"], "feed SLA status"),
        (["python", "scripts/run_stress_tests.py"], "run stress tests or generate data"),
        (["python", "scripts/import_sanity.py"], "import failures in core modules"),
    ]
    for cmd, action in steps:
        ok = _run(cmd, next_action=action)
        if not ok:
            return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
