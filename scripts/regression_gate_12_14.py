import subprocess
import sys


STEPS = [
    ["python", "scripts/dr_backup.py"],
    ["python", "scripts/dr_verify.py", "--state", "/tmp/restore_test"],
    ["python", "scripts/verify_audit_chain.py"],
    ["python", "scripts/canary_status.py"],
    ["python", "scripts/desk_status.py"],
    ["python", "scripts/capital_committee_report.py", "--days", "60"],
    ["python", "scripts/paper_tournament.py", "--days", "30"],
    ["python", "scripts/generate_hypotheses.py"],
    ["python", "scripts/adaptive_risk_status.py"],
]


def main():
    for cmd in STEPS:
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"FAIL: {' '.join(cmd)}")
            raise SystemExit(result.returncode)
    print("PASS: regression_gate_12_14")


if __name__ == "__main__":
    main()
