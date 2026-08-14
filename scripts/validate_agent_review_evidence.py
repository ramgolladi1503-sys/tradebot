from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REQUIRED_SECTIONS = (
    "Agent Work Contract",
    "Scope Guard",
    "Grill Me Review",
    "Hermes Review",
    "GSD Review",
    "QA / Safety Review",
    "Acceptance Proof",
    "Runtime Proof Required After Merge",
    "What This PR Does Not Prove",
    "Human Approval",
)

HIGH_RISK_PATHS = (
    "config/",
    "core/auth.py",
    "core/kite_depth_ws.py",
    "core/orchestrator.py",
    "core/execution_engine.py",
    "core/execution/",
    "core/risk",
    "strategies/",
)

AGENT_REVIEW_DIR = Path("docs/agent_reviews")
EXTERNAL_REVIEW_DIR = AGENT_REVIEW_DIR / "external_exact_sha_reviews"


def _run_git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            proc.stderr.strip() or proc.stdout.strip() or f"git {' '.join(args)} failed"
        )
    return proc.stdout.strip()


def changed_files(base_ref: str, candidate_ref: str = "HEAD") -> list[str]:
    merge_base = _run_git(["merge-base", candidate_ref, base_ref])
    output = _run_git(["diff", "--name-only", f"{merge_base}..{candidate_ref}"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def agent_review_files(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.parts[:2] == ("docs", "agent_reviews") and path.suffix.lower() == ".md":
            out.append(path)
    return out


def _missing_sections(text: str) -> list[str]:
    lower = text.lower()
    return [section for section in REQUIRED_SECTIONS if section.lower() not in lower]


def _has_unresolved_blocking_issue(text: str) -> bool:
    lower = text.lower()
    blocked_markers = (
        "verdict: fail",
        "blocking issues: yes",
        "blocking issue: yes",
        "unresolved blocking issue",
        "unresolved blocker",
    )
    return any(marker in lower for marker in blocked_markers)


def _high_risk_changed(paths: list[str]) -> bool:
    for path in paths:
        for prefix in HIGH_RISK_PATHS:
            if path == prefix.rstrip("/") or path.startswith(prefix):
                return True
    return False


def _base_external_review(base_ref: str, candidate_sha: str) -> str | None:
    """Read only an exact-SHA manifest from the trusted base tree."""
    manifest = EXTERNAL_REVIEW_DIR / f"{candidate_sha}.md"
    proc = subprocess.run(
        ["git", "show", f"{base_ref}:{manifest.as_posix()}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout


def validate(base_ref: str, candidate_ref: str = "HEAD") -> int:
    paths = changed_files(base_ref, candidate_ref)
    review_paths = agent_review_files(paths)
    errors: list[str] = []
    candidate_sha = _run_git(["rev-parse", candidate_ref])
    external_review = _base_external_review(base_ref, candidate_sha)

    if not review_paths and external_review is None:
        errors.append(
            "Missing mandatory agent review evidence file under docs/agent_reviews/*.md. "
            "Every PR must include Agent Work Contract, Scope Guard, Grill Me, Hermes, GSD, QA/Safety, "
            "Acceptance Proof, Runtime Proof Required After Merge, What This PR Does Not Prove, and Human Approval."
        )

    for review_path in review_paths:
        if not review_path.exists():
            errors.append(
                f"Agent review file is listed as changed but does not exist: {review_path}"
            )
            continue
        text = review_path.read_text(encoding="utf-8")
        missing = _missing_sections(text)
        if missing:
            errors.append(
                f"{review_path}: missing required sections: {', '.join(missing)}"
            )
        if _has_unresolved_blocking_issue(text):
            errors.append(
                f"{review_path}: unresolved blocking issue or FAIL verdict found"
            )

    high_risk = _high_risk_changed(paths)
    if high_risk:
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in review_paths if path.exists()
        )
        if external_review:
            combined += "\n" + external_review
        combined = combined.lower()
        if "high-risk path review" not in combined:
            errors.append(
                "High-risk files changed, but no agent review doc contains 'High-Risk Path Review'. "
                "Required for config, auth, feed/WebSocket, orchestrator, execution, risk, or strategies changes."
            )

    if errors:
        print("AGENT REVIEW EVIDENCE GATE: FAILED", file=sys.stderr)
        print("Changed files:", file=sys.stderr)
        for path in paths:
            print(f"  - {path}", file=sys.stderr)
        print("Errors:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("AGENT REVIEW EVIDENCE GATE: PASSED")
    print("Agent review files:")
    for path in review_paths:
        print(f"  - {path}")
    if external_review:
        print(f"  - {EXTERNAL_REVIEW_DIR / (candidate_sha + '.md')} (trusted base manifest)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate mandatory agent review evidence for PRs."
    )
    parser.add_argument(
        "--base-ref",
        default=os.environ.get("AGENT_REVIEW_BASE_REF", "origin/main"),
        help="Base ref to diff against. Defaults to AGENT_REVIEW_BASE_REF or origin/main.",
    )
    parser.add_argument(
        "--candidate-ref",
        default="HEAD",
        help="Exact candidate ref to inspect; defaults to HEAD.",
    )
    args = parser.parse_args()
    return validate(args.base_ref, args.candidate_ref)


if __name__ == "__main__":
    raise SystemExit(main())
