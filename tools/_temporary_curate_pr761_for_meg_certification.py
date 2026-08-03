from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "origin/agent/enterprise-qa-foundation-v1"
SELECTED = (
    "docs/qa/ENTERPRISE_QA_MASTER_PLAN.md",
    "docs/qa/MODULE_RISK_REGISTER.md",
    "scripts/audit_test_integrity.py",
    "tests/test_test_integrity_audit.py",
    "tests/auth/test_auth_manager_behavior_contracts.py",
)


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True)


for path in SELECTED:
    if subprocess.run(
        ["git", "cat-file", "-e", f"{SOURCE}:{path}"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode != 0:
        raise SystemExit(f"SOURCE_FILE_MISSING:{path}")

subprocess.run(["git", "checkout", SOURCE, "--", *SELECTED], cwd=ROOT, check=True)

auth_path = ROOT / "core" / "auth_manager.py"
auth = auth_path.read_text(encoding="utf-8")
old_network = '''    return ("timed out" in msg) or ("connection" in msg and "invalid session" not in msg)\n'''
new_network = '''    if "invalid session" in msg:\n        return False\n    return ("timed out" in msg) or ("connection" in msg) or ("network" in msg)\n'''
if new_network not in auth:
    if old_network not in auth:
        raise SystemExit("AUTH_NETWORK_PATCH_CONTEXT_MISSING")
    auth = auth.replace(old_network, new_network, 1)

old_unknown = '''        if _is_network_error(exc):\n            return {\n                "ok": True,\n                "auth_state": "UNKNOWN_NETWORK",\n'''
new_unknown = '''        if _is_network_error(exc):\n            return {\n                "ok": False,\n                "auth_state": "UNKNOWN_NETWORK",\n'''
if new_unknown not in auth:
    if old_unknown not in auth:
        raise SystemExit("AUTH_UNKNOWN_NETWORK_PATCH_CONTEXT_MISSING")
    auth = auth.replace(old_unknown, new_unknown, 1)
auth_path.write_text(auth, encoding="utf-8")

changed = set(run("git", "diff", "--name-only").splitlines())
expected = set(SELECTED) | {"core/auth_manager.py"}
unexpected = sorted(changed - expected)
missing = sorted(expected - changed)
if unexpected:
    raise SystemExit(f"UNEXPECTED_CURATED_PATHS:{unexpected}")
if missing:
    raise SystemExit(f"EXPECTED_CURATED_PATHS_NOT_CHANGED:{missing}")

print("curated PR761 extraction prepared")
for path in sorted(changed):
    print(path)
