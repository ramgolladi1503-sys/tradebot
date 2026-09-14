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
    ".github/workflows/",
)

ATTACK_REQUIRED_PREFIXES = (
    "config/",
    ".github/workflows/",
    ".github/actions/",
)
ATTACK_REQUIRED_EXACT = (
    "requirements.txt",
    "pyproject.toml",
    "pytest.ini",
    "setup.cfg",
    "tox.ini",
    "Dockerfile",
)
TEST_PREFIXES = ("tests/",)
GATE_PROTECTED_PATHS = (
    ".github/workflows/adversarial-pr-gate.yml",
    ".github/workflows/ci.yml",
    ".github/workflows/agent-review-gate.yml",
    ".github/workflows/repo-forensics-pr-gate.yml",
    ".github/workflows/frozen-head-candidate-safety-tests.yml",
    ".github/workflows/codeql.yml",
    "scripts/run_adversarial_pr_gate.py",
    "scripts/validate_agent_review_evidence.py",
    "tests/governance/test_adversarial_pr_gate.py",
    "tests/governance/test_adversarial_pr_gate_workflow_safety.py",
)
BOOTSTRAP_ALLOWED_PATHS = {
    ".github/workflows/adversarial-pr-gate.yml",
    "scripts/run_adversarial_pr_gate.py",
    "tests/governance/test_adversarial_pr_gate.py",
    "tests/governance/test_adversarial_pr_gate_workflow_safety.py",
}
BOOTSTRAP_BRANCH = "governance/adversarial-pr-gate-v1"

SKIP_PATTERNS = (
    r"pytest\.skip\(",
    r"pytest\.xfail\(",
    r"pytest\.mark\.skip",
    r"pytest\.mark\.xfail",
    r"unittest\.skip",
    r"@skip\b",
)
TRIVIAL_ASSERT_PATTERNS = (
    r"^\s*assert\s+(True|1|1\.0)\s*(#.*)?$",
    r"^\s*assert\s+(['\"]).*\2\s*(#.*)?$",
)
BROAD_RAISES_PATTERN = re.compile(r"pytest\.raises\(\s*(Exception|BaseException)\b")
PYTEST_SUPPRESSION_PATTERNS = (
    r"--ignore(?:=|\s)",
    r"--ignore-glob(?:=|\s)",
    r"--deselect(?:=|\s)",
    r"--continue-on-collection-errors\b",
    r"\btestpaths\s*=",
    r"\bpython_files\s*=",
    r"\bpython_functions\s*=",
    r"\bpython_classes\s*=",
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


def _is_test(path: str) -> bool:
    return path.endswith(".py") and path.startswith(TEST_PREFIXES)


def _is_code(path: str) -> bool:
    return path.endswith(".py") and not _is_test(path) and not path.startswith("docs/")


def _requires_attack(path: str) -> bool:
    if _is_test(path) or path.startswith("docs/"):
        return False
    if _is_code(path):
        return True
    return path in ATTACK_REQUIRED_EXACT or any(path.startswith(prefix) for prefix in ATTACK_REQUIRED_PREFIXES)


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
    direct_call = re.compile(r"\b(eval|exec|compile|__import__)\s*\(")
    indirect_lookup = re.compile(
        r"\b(getattr|__getattribute__)\s*\([^\n]*?[\"'](eval|exec|compile|__import__)[\"']"
    )
    for path in paths:
        if not _is_code(path):
            continue
        for line in _added_lines(changed_diff(base_ref, candidate_ref, path)):
            direct = direct_call.search(line)
            indirect = indirect_lookup.search(line)
            if direct and direct.group(1) in DANGEROUS_CALLS:
                errors.append(f"DANGEROUS_API_ADDED:{path}:{direct.group(1)}:{line.strip()}")
            if indirect and indirect.group(2) in DANGEROUS_CALLS:
                errors.append(f"DANGEROUS_API_INDIRECT_LOOKUP_ADDED:{path}:{indirect.group(2)}:{line.strip()}")


def _test_weakening_attack(base_ref: str, candidate_ref: str, paths: list[str], errors: list[str]) -> None:
    for path in paths:
        if not _is_test(path):
            continue
        diff = changed_diff(base_ref, candidate_ref, path)
        added = _added_lines(diff)
        removed = _removed_lines(diff)
        for line in added:
            if any(re.search(pattern, line) for pattern in SKIP_PATTERNS):
                errors.append(f"TEST_WEAKENING_SKIP_OR_XFAIL_ADDED:{path}:{line.strip()}")
            if any(re.search(pattern, line) for pattern in TRIVIAL_ASSERT_PATTERNS):
                errors.append(f"TEST_WEAKENING_TRIVIAL_ASSERT_ADDED:{path}:{line.strip()}")
            if BROAD_RAISES_PATTERN.search(line):
                errors.append(f"TEST_WEAKENING_BROAD_EXCEPTION_ASSERTION:{path}:{line.strip()}")
        removed_asserts = sum(1 for line in removed if re.search(r"\bassert\b|pytest\.raises|assert_", line))
        added_asserts = sum(1 for line in added if re.search(r"\bassert\b|pytest\.raises|assert_", line))
        if removed_asserts > added_asserts:
            errors.append(
                f"TEST_WEAKENING_ASSERTION_LOSS:{path}:removed={removed_asserts}:added={added_asserts}"
            )


def _pytest_config_suppression_attack(base_ref: str, candidate_ref: str, paths: list[str], errors: list[str]) -> None:
    config_paths = {"pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini"}
    for path in paths:
        if path not in config_paths:
            continue
        for line in _added_lines(changed_diff(base_ref, candidate_ref, path)):
            if any(re.search(pattern, line) for pattern in PYTEST_SUPPRESSION_PATTERNS):
                errors.append(f"PYTEST_COLLECTION_OR_SUPPRESSION_CHANGE_REQUIRES_EXPLICIT_RECERTIFICATION:{path}:{line.strip()}")


def _coverage_shape_attack(paths: list[str], errors: list[str]) -> None:
    attacked_surface = [p for p in paths if _requires_attack(p)]
    tests = [p for p in paths if _is_test(p)]
    adversarial = [p for p in tests if _is_adversarial_test(p)]
    if attacked_surface and not tests:
        errors.append("ATTACK_REQUIRED_CHANGE_WITHOUT_TEST_CHANGE")
    if attacked_surface and not adversarial:
        errors.append("ATTACK_REQUIRED_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE")
    if any(_high_risk(p) for p in attacked_surface) and not adversarial:
        errors.append("HIGH_RISK_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE")


def _substantive_assertion_count(function: ast.AST) -> int:
    count = 0
    for node in ast.walk(function):
        if isinstance(node, ast.Assert):
            test = node.test
            if isinstance(test, ast.Constant):
                continue
            if isinstance(test, ast.Compare) and len(test.ops) == 1 and len(test.comparators) == 1:
                if ast.dump(test.left, include_attributes=False) == ast.dump(test.comparators[0], include_attributes=False):
                    continue
            count += 1
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "pytest" and node.func.attr == "raises":
                if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in {"Exception", "BaseException"}:
                    continue
                count += 1
    return count


def _adversarial_test_quality_attack(candidate_ref: str, paths: list[str], errors: list[str]) -> None:
    attacked_surface = [p for p in paths if _requires_attack(p)]
    if not attacked_surface:
        return
    high_risk = any(_high_risk(p) for p in attacked_surface)
    adv_paths = [p for p in paths if _is_adversarial_test(p)]
    total_tests = 0
    substantive_tests = 0
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
        for node in test_functions:
            assertions = _substantive_assertion_count(node)
            total_assertions += assertions
            if assertions > 0:
                substantive_tests += 1

    min_tests = 2 if high_risk else 1
    min_assertions = 2 if high_risk else 1
    min_substantive_tests = 2 if high_risk else 1
    if total_tests < min_tests:
        errors.append(f"ADVERSARIAL_TEST_TOO_SHALLOW:test_functions={total_tests}:required={min_tests}")
    if substantive_tests < min_substantive_tests:
        errors.append(
            f"ADVERSARIAL_TEST_SUBSTANTIVE_CASE_FLOOR_FAIL:substantive_tests={substantive_tests}:required={min_substantive_tests}"
        )
    if total_assertions < min_assertions:
        errors.append(f"ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL:assertions={total_assertions}:required={min_assertions}")
    if negative_named_tests < 1:
        errors.append("ADVERSARIAL_TEST_HAS_NO_NEGATIVE_SEMANTIC_CASE")


def _base_contains_gate(base_ref: str) -> bool:
    proc = _run(["git", "cat-file", "-e", f"{base_ref}:scripts/run_adversarial_pr_gate.py"], check=False)
    return proc.returncode == 0


def _governance_self_protection(base_ref: str, paths: list[str], branch: str, errors: list[str]) -> None:
    touched = [p for p in paths if p in GATE_PROTECTED_PATHS]
    if not touched:
        return
    if branch == BOOTSTRAP_BRANCH and not _base_contains_gate(base_ref):
        forbidden_bootstrap = [p for p in touched if p not in BOOTSTRAP_ALLOWED_PATHS]
        if not forbidden_bootstrap:
            return
        errors.append("BOOTSTRAP_SCOPE_VIOLATION:" + ",".join(forbidden_bootstrap))
        return
    errors.append(
        "ADVERSARIAL_GATE_SELF_MODIFICATION_BLOCKED_REQUIRES_TRUSTED_RECERTIFICATION:" + ",".join(touched)
    )


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
    _pytest_config_suppression_attack(base_ref, candidate_ref, paths, errors)
    _coverage_shape_attack(paths, errors)
    _adversarial_test_quality_attack(candidate_ref, paths, errors)
    _governance_self_protection(base_ref, paths, branch, errors)

    if run_tests:
        _run_changed_tests(paths, errors)

    print("ADVERSARIAL_PR_GATE")
    print(f"base_ref={base_ref}")
    print(f"candidate_ref={candidate_ref}")
    print(f"branch={branch}")
    print(f"changed_files={len(paths)}")
    print(f"high_risk_changed={any(_high_risk(p) for p in paths)}")
    print(f"attack_required_changed={sum(1 for p in paths if _requires_attack(p))}")
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
