from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

HIGH_RISK_PREFIXES = (
    "main.py",
    "config/",
    "core/auth.py",
    "core/broker",
    "core/order",
    "core/execution",
    "core/risk",
    "core/feed",
    "core/kite",
    "core/runtime",
    "strategies/",
)

PRODUCTION_PREFIXES = ("core/", "strategies/", "scripts/", "tools/")
TEST_PREFIXES = ("tests/",)
GATE_PROTECTED_PATHS = (
    ".github/workflows/adversarial-pr-gate.yml",
    "scripts/run_adversarial_pr_gate.py",
    "tests/governance/test_adversarial_pr_gate.py",
)
BOOTSTRAP_BRANCH = "governance/adversarial-pr-gate-v1"

SKIP_PATTERNS = (
    r"pytest\.skip\(",
    r"pytest\.mark\.skip",
    r"pytest\.mark\.xfail",
    r"unittest\.skip",
    r"@skip\b",
)
ADVERSARIAL_TEST_TOKENS = ("attack", "adversarial", "mutation", "safety", "negative")
NEGATIVE_SEMANTIC_TOKENS = (
    "fail",
    "reject",
    "block",
    "invalid",
    "missing",
    "tamper",
    "unsafe",
    "forbid",
    "deny",
    "error",
    "boundary",
    "negative",
    "attack",
    "mutation",
)
DANGEROUS_CALLS = {"eval", "exec", "compile", "__import__"}


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if check and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "command failed")
    return proc


def _git(*args: str) -> str:
    return _run(["git", *args]).stdout.strip()


def changed_files(base_ref: str, candidate_ref: str) -> list[str]:
    merge_base = _git("merge-base", base_ref, candidate_ref)
    out = _git("diff", "--name-only", f"{merge_base}..{candidate_ref}")
    return [line.strip() for line in out.splitlines() if line.strip()]


def changed_diff(base_ref: str, candidate_ref: str, path: str) -> str:
    merge_base = _git("merge-base", base_ref, candidate_ref)
    return _git("diff", "--unified=0", f"{merge_base}..{candidate_ref}", "--", path)


def _added_lines(diff: str) -> list[str]:
    return [line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]


def _removed_lines(diff: str) -> list[str]:
    return [line[1:] for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")]


def _is_code(path: str) -> bool:
    return path.endswith(".py") and path.startswith(PRODUCTION_PREFIXES)


def _is_test(path: str) -> bool:
    return path.endswith(".py") and path.startswith(TEST_PREFIXES)


def _is_adversarial_test(path: str) -> bool:
    name = Path(path).name.lower()
    return _is_test(path) and any(token in name for token in ADVERSARIAL_TEST_TOKENS)


def _high_risk(path: str) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in HIGH_RISK_PREFIXES)


def _read_candidate(candidate_ref: str, path: str) -> str | None:
    proc = _run(["git", "show", f"{candidate_ref}:{path}"], check=False)
    return proc.stdout if proc.returncode == 0 else None


def _syntax_attack(candidate_ref: str, paths: list[str], errors: list[str]) -> None:
    for path in paths:
        if not path.endswith(".py"):
            continue
        text = _read_candidate(candidate_ref, path)
        if text is None:
            continue
        try:
            ast.parse(text, filename=path)
        except SyntaxError as exc:
            errors.append(f"SYNTAX_ATTACK_FAIL:{path}:{exc.msg}")


def _dangerous_api_attack(base_ref: str, candidate_ref: str, paths: list[str], errors: list[str]) -> None:
    call_pattern = re.compile(r"\b(eval|exec|compile|__import__)\s*\(")
    for path in paths:
        if not _is_code(path):
            continue
        for line in _added_lines(changed_diff(base_ref, candidate_ref, path)):
            match = call_pattern.search(line)
            if match and match.group(1) in DANGEROUS_CALLS:
                errors.append(f"DANGEROUS_API_ADDED:{path}:{match.group(1)}:{line.strip()}")


def _test_weakening_attack(base_ref: str, candidate_ref: str, paths: list[str], errors: list[str]) -> None:
    for path in paths:
        if not _is_test(path):
            continue
        diff = changed_diff(base_ref, candidate_ref, path)
        added = _added_lines(diff)
        removed = _removed_lines(diff)
        for line in added:
            if any(re.search(pattern, line) for pattern in SKIP_PATTERNS):
                errors.append(f"TEST_WEAKENING_SKIP_ADDED:{path}:{line.strip()}")
        removed_asserts = sum(1 for line in removed if re.search(r"\bassert\b|pytest\.raises|assert_", line))
        added_asserts = sum(1 for line in added if re.search(r"\bassert\b|pytest\.raises|assert_", line))
        if removed_asserts > added_asserts:
            errors.append(
                f"TEST_WEAKENING_ASSERTION_LOSS:{path}:removed={removed_asserts}:added={added_asserts}"
            )


def _coverage_shape_attack(paths: list[str], errors: list[str]) -> None:
    production = [p for p in paths if _is_code(p)]
    tests = [p for p in paths if _is_test(p)]
    adversarial = [p for p in tests if _is_adversarial_test(p)]
    if production and not tests:
        errors.append("PRODUCTION_CHANGE_WITHOUT_TEST_CHANGE")
    if production and not adversarial:
        errors.append("PRODUCTION_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE")
    if any(_high_risk(p) for p in production) and not adversarial:
        errors.append("HIGH_RISK_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE")


def _adversarial_test_quality_attack(candidate_ref: str, paths: list[str], errors: list[str]) -> None:
    production = [p for p in paths if _is_code(p)]
    if not production:
        return
    high_risk = any(_high_risk(p) for p in production)
    adv_paths = [p for p in paths if _is_adversarial_test(p)]
    total_tests = 0
    total_assertions = 0
    negative_named_tests = 0

    for path in adv_paths:
        text = _read_candidate(candidate_ref, path)
        if text is None:
            errors.append(f"ADVERSARIAL_TEST_UNREADABLE:{path}")
            continue
        try:
            tree = ast.parse(text, filename=path)
        except SyntaxError:
            continue
        test_functions = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        ]
        total_tests += len(test_functions)
        negative_named_tests += sum(
            1 for node in test_functions if any(token in node.name.lower() for token in NEGATIVE_SEMANTIC_TOKENS)
        )
        total_assertions += sum(1 for node in ast.walk(tree) if isinstance(node, ast.Assert))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "pytest" and node.func.attr == "raises":
                    total_assertions += 1

    min_tests = 2 if high_risk else 1
    min_assertions = 2 if high_risk else 1
    if total_tests < min_tests:
        errors.append(f"ADVERSARIAL_TEST_TOO_SHALLOW:test_functions={total_tests}:required={min_tests}")
    if total_assertions < min_assertions:
        errors.append(f"ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL:assertions={total_assertions}:required={min_assertions}")
    if negative_named_tests < 1:
        errors.append("ADVERSARIAL_TEST_HAS_NO_NEGATIVE_SEMANTIC_CASE")


def _governance_self_protection(paths: list[str], branch: str, errors: list[str]) -> None:
    touched = [p for p in paths if p in GATE_PROTECTED_PATHS]
    if touched and branch != BOOTSTRAP_BRANCH:
        errors.append("ADVERSARIAL_GATE_SELF_MODIFICATION_REQUIRES_DEDICATED_RECERTIFICATION:" + ",".join(touched))


def _run_changed_tests(paths: list[str], errors: list[str]) -> None:
    tests = [p for p in paths if _is_test(p) and Path(p).exists()]
    if not tests:
        return
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", *tests], check=False)
    if proc.returncode != 0:
        errors.append(f"CHANGED_TESTS_FAILED:exit={proc.returncode}")


def execute(base_ref: str, candidate_ref: str, branch: str, run_tests: bool) -> int:
    paths = changed_files(base_ref, candidate_ref)
    errors: list[str] = []

    _syntax_attack(candidate_ref, paths, errors)
    _dangerous_api_attack(base_ref, candidate_ref, paths, errors)
    _test_weakening_attack(base_ref, candidate_ref, paths, errors)
    _coverage_shape_attack(paths, errors)
    _adversarial_test_quality_attack(candidate_ref, paths, errors)
    _governance_self_protection(paths, branch, errors)

    if run_tests:
        _run_changed_tests(paths, errors)

    print("ADVERSARIAL_PR_GATE")
    print(f"base_ref={base_ref}")
    print(f"candidate_ref={candidate_ref}")
    print(f"branch={branch}")
    print(f"changed_files={len(paths)}")
    print(f"high_risk_changed={any(_high_risk(p) for p in paths)}")
    print(f"adversarial_tests={sum(1 for p in paths if _is_adversarial_test(p))}")
    for path in paths:
        print(f"changed:{path}")

    if errors:
        print("VERDICT=FAIL", file=sys.stderr)
        for error in errors:
            print(f"ATTACK_FAILURE:{error}", file=sys.stderr)
        return 1

    print("VERDICT=PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed adversarial PR gate")
    parser.add_argument("--base-ref", default=os.environ.get("ADVERSARIAL_BASE_REF", "origin/main"))
    parser.add_argument("--candidate-ref", default=os.environ.get("ADVERSARIAL_CANDIDATE_REF", "HEAD"))
    parser.add_argument("--branch", default=os.environ.get("ADVERSARIAL_BRANCH", ""))
    parser.add_argument("--run-tests", action="store_true")
    args = parser.parse_args()
    try:
        return execute(args.base_ref, args.candidate_ref, args.branch, args.run_tests)
    except Exception as exc:
        print(f"VERDICT=BLOCKED\nGATE_EXCEPTION:{type(exc).__name__}:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
