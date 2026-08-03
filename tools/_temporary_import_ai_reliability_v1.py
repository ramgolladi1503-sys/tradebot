from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "origin/feature/ai-pipeline-reliability-agent-v1"
SOURCE_BASE = "17262b4b6a42eb09d4d508bfdf6fe0d649ee32af"


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True)


def allowed(path: str) -> bool:
    return (
        path.startswith("core/ai_reliability_agent/")
        or path.startswith("scripts/run_ai_reliability")
        or path.startswith("tests/test_ai_reliability")
        or path.startswith("tests/fixtures/ai_reliability_real_artifact/")
        or path in {
            "docs/agent_reviews/ai_reliability_agent_v1.md",
            "docs/architecture/ai_reliability_agent_v1.md",
            "docs/test-reports/ai_reliability_agent_v1_certification.json",
            "docs/test-reports/ai_reliability_agent_v1_certification.md",
        }
    )


changed = [
    line.strip()
    for line in run("git", "diff", "--name-only", SOURCE_BASE, SOURCE).splitlines()
    if line.strip()
]
selected = [path for path in changed if allowed(path)]
rejected = [path for path in changed if not allowed(path)]
if not selected:
    raise SystemExit("NO_PR760_FILES_SELECTED")
subprocess.run(["git", "checkout", SOURCE, "--", *selected], cwd=ROOT, check=True)

init_path = ROOT / "core" / "ai_reliability_agent" / "__init__.py"
text = init_path.read_text(encoding="utf-8") if init_path.exists() else ""
export = '''\nfrom .pr763_session import (\n    FAILED_VERDICT as PR763_FAILED_VERDICT,\n    PASS_VERDICT as PR763_PASS_VERDICT,\n    PENDING_VERDICT as PR763_PENDING_VERDICT,\n    certify_pr763_session,\n)\n'''
if "certify_pr763_session" not in text:
    init_path.write_text(text.rstrip() + "\n" + export, encoding="utf-8")

print(f"selected={len(selected)}")
for path in selected:
    print(f"SELECTED {path}")
for path in rejected:
    print(f"REJECTED {path}")
