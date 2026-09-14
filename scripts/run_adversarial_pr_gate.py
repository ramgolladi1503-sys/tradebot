from __future__ import annotations

import argparse
import ast
import math
import os
import re
import subprocess
import sys
from pathlib import Path

HIGH_RISK_PREFIXES = (
    "main.py", "config/", "core/auth.py", "core/broker", "core/order",
    "core/execution", "core/risk", "core/feed", "core/kite", "core/runtime",
    "strategies/", ".github/workflows/", "scripts/run_adversarial_pr_gate.py",
)
ATTACK_REQUIRED_PREFIXES = ("config/", ".github/workflows/", ".github/actions/")
ATTACK_REQUIRED_EXACT = (
    "requirements.txt", "pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini", "Dockerfile",
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
RECERTIFICATION_BRANCH_PREFIX = "governance/adversarial-gate-recertification-"
RECERTIFICATION_DIR = "docs/adversarial_gate_recertifications"

SKIP_PATTERNS = (
    r"pytest\.skip\(", r"pytest\.xfail\(", r"pytest\.mark\.skip",
    r"pytest\.mark\.xfail", r"unittest\.skip", r"@skip\b",
)
TRIVIAL_ASSERT_PATTERNS = (
    r"^\s*assert\s+(True|1|1\.0)\s*(#.*)?$",
    r"^\s*assert\s+(['\"]).*\2\s*(#.*)?$",
)
BROAD_RAISES_PATTERN = re.compile(r"pytest\.raises\(\s*(Exception|BaseException)\b")
PYTEST_SUPPRESSION_PATTERNS = (
    r"--ignore(?:=|\s)", r"--ignore-glob(?:=|\s)", r"--deselect(?:=|\s)",
    r"--continue-on-collection-errors\b", r"\btestpaths\s*=", r"\bpython_files\s*=",
    r"\bpython_functions\s*=", r"\bpython_classes\s*=",
)
ADVERSARIAL_TEST_TOKENS = ("attack", "adversarial", "mutation", "safety", "negative")
NEGATIVE_SEMANTIC_TOKENS = (
    "fail", "reject", "block", "invalid", "missing", "tamper", "unsafe", "forbid",
    "deny", "error", "boundary", "negative", "attack", "mutation",
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
    return _is_code(path) or path in ATTACK_REQUIRED_EXACT or any(path.startswith(p) for p in ATTACK_REQUIRED_PREFIXES)


def _is_adversarial_test(path: str) -> bool:
    return _is_test(path) and any(token in Path(path).name.lower() for token in ADVERSARIAL_TEST_TOKENS)


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
    indirect_lookup = re.compile(r"\b(getattr|__getattribute__)\s*\([^\n]*?[\"'](eval|exec|compile|__import__)[\"']")
    for path in paths:
        if not _is_code(path):
            continue
        for line in _added_lines(changed_diff(base_ref, candidate_ref, path)):
            direct, indirect = direct_call.search(line), indirect_lookup.search(line)
            if direct and direct.group(1) in DANGEROUS_CALLS:
                errors.append(f"DANGEROUS_API_ADDED:{path}:{direct.group(1)}:{line.strip()}")
            if indirect and indirect.group(2) in DANGEROUS_CALLS:
                errors.append(f"DANGEROUS_API_INDIRECT_LOOKUP_ADDED:{path}:{indirect.group(2)}:{line.strip()}")


def _test_weakening_attack(base_ref: str, candidate_ref: str, paths: list[str], errors: list[str]) -> None:
    for path in paths:
        if not _is_test(path):
            continue
        diff = changed_diff(base_ref, candidate_ref, path)
        added, removed = _added_lines(diff), _removed_lines(diff)
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
            errors.append(f"TEST_WEAKENING_ASSERTION_LOSS:{path}:removed={removed_asserts}:added={added_asserts}")


def _pytest_config_suppression_attack(base_ref: str, candidate_ref: str, paths: list[str], errors: list[str]) -> None:
    config_paths = {"pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini"}
    for path in paths:
        if path in config_paths:
            for line in _added_lines(changed_diff(base_ref, candidate_ref, path)):
                if any(re.search(pattern, line) for pattern in PYTEST_SUPPRESSION_PATTERNS):
                    errors.append(f"PYTEST_COLLECTION_OR_SUPPRESSION_CHANGE_REQUIRES_EXPLICIT_RECERTIFICATION:{path}:{line.strip()}")


def _coverage_shape_attack(paths: list[str], errors: list[str]) -> None:
    attacked = [p for p in paths if _requires_attack(p)]
    tests = [p for p in paths if _is_test(p)]
    adversarial = [p for p in tests if _is_adversarial_test(p)]
    if attacked and not tests:
        errors.append("ATTACK_REQUIRED_CHANGE_WITHOUT_TEST_CHANGE")
    if attacked and not adversarial:
        errors.append("ATTACK_REQUIRED_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE")
    if any(_high_risk(p) for p in attacked) and not adversarial:
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


def _module_name_for_path(path: str) -> str:
    return path[:-3].replace("/", ".") if path.endswith(".py") else ""


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names if alias.name != "*")
    return modules


def _required_attack_case_count(attacked_surface: list[str], high_risk: bool) -> int:
    scaled = max(1, math.ceil(len(attacked_surface) / 4))
    return min(10, max(2 if high_risk else 1, scaled))


def _adversarial_test_quality_attack(candidate_ref: str, paths: list[str], errors: list[str]) -> None:
    attacked = [p for p in paths if _requires_attack(p)]
    if not attacked:
        return
    high_risk = any(_high_risk(p) for p in attacked)
    adv_paths = [p for p in paths if _is_adversarial_test(p)]
    total_tests = substantive_tests = total_assertions = negative_named_tests = 0
    imported_modules: set[str] = set()
    for path in adv_paths:
        text = _read_candidate(candidate_ref, path)
        if text is None:
            errors.append(f"ADVERSARIAL_TEST_UNREADABLE:{path}")
            continue
        try:
            tree = ast.parse(text, filename=path)
        except SyntaxError:
            continue
        imported_modules.update(_imported_modules(tree))
        functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]
        total_tests += len(functions)
        negative_named_tests += sum(1 for n in functions if any(t in n.name.lower() for t in NEGATIVE_SEMANTIC_TOKENS))
        for node in functions:
            assertions = _substantive_assertion_count(node)
            total_assertions += assertions
            substantive_tests += int(assertions > 0)
    required = _required_attack_case_count(attacked, high_risk)
    if total_tests < required:
        errors.append(f"ADVERSARIAL_TEST_TOO_SHALLOW:test_functions={total_tests}:required={required}")
    if substantive_tests < required:
        errors.append(f"ADVERSARIAL_TEST_SUBSTANTIVE_CASE_FLOOR_FAIL:substantive_tests={substantive_tests}:required={required}")
    if total_assertions < required:
        errors.append(f"ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL:assertions={total_assertions}:required={required}")
    if negative_named_tests < required:
        errors.append(f"ADVERSARIAL_NEGATIVE_CASE_FLOOR_FAIL:negative_named_tests={negative_named_tests}:required={required}")
    for surface in attacked:
        if not (_high_risk(surface) and _is_code(surface)):
            continue
        module = _module_name_for_path(surface)
        if module not in imported_modules and not any(name.startswith(module + ".") for name in imported_modules):
            errors.append(f"HIGH_RISK_SURFACE_UNIMPORTED_BY_ADVERSARIAL_TEST:{surface}")


def _base_contains_gate(base_ref: str) -> bool:
    return _run(["git", "cat-file", "-e", f"{base_ref}:scripts/run_adversarial_pr_gate.py"], check=False).returncode == 0


def _trusted_recertification_authorized(base_ref: str, candidate_ref: str) -> bool:
    candidate_sha = _git("rev-parse", candidate_ref).lower()
    manifest = f"{RECERTIFICATION_DIR}/{candidate_sha}.md"
    proc = _run(["git", "show", f"{base_ref}:{manifest}"], check=False)
    if proc.returncode != 0:
        return False
    lines = {line.strip().lower() for line in proc.stdout.splitlines() if line.strip()}
    required = {
        f"candidate_sha: {candidate_sha}",
        "authorized: true",
        "scope: adversarial-gate-recertification",
    }
    return required.issubset(lines)


def _governance_self_protection(
    base_ref: str,
    paths: list[str],
    branch: str,
    errors: list[str],
    candidate_ref: str = "HEAD",
) -> None:
    touched = [p for p in paths if p in GATE_PROTECTED_PATHS]
    if not touched:
        return
    if branch == BOOTSTRAP_BRANCH and not _base_contains_gate(base_ref):
        forbidden = [p for p in touched if p not in BOOTSTRAP_ALLOWED_PATHS]
        if not forbidden:
            return
        errors.append("BOOTSTRAP_SCOPE_VIOLATION:" + ",".join(forbidden))
        return
    if branch.startswith(RECERTIFICATION_BRANCH_PREFIX) and _trusted_recertification_authorized(base_ref, candidate_ref):
        return
    errors.append("ADVERSARIAL_GATE_SELF_MODIFICATION_BLOCKED_REQUIRES_TRUSTED_RECERTIFICATION:" + ",".join(touched))


def _run_changed_tests(paths: list[str], errors: list[str]) -> None:
    tests = [p for p in paths if _is_test(p) and Path(p).exists()]
    if tests and subprocess.run([sys.executable, "-m", "pytest", "-q", *tests], check=False).returncode != 0:
        errors.append("CHANGED_TESTS_FAILED")


def execute(base_ref: str, candidate_ref: str, branch: str, run_tests: bool) -> int:
    paths = changed_files(base_ref, candidate_ref)
    errors: list[str] = []
    _syntax_attack(candidate_ref, paths, errors)
    _dangerous_api_attack(base_ref, candidate_ref, paths, errors)
    _test_weakening_attack(base_ref, candidate_ref, paths, errors)
    _pytest_config_suppression_attack(base_ref, candidate_ref, paths, errors)
    _coverage_shape_attack(paths, errors)
    _adversarial_test_quality_attack(candidate_ref, paths, errors)
    _governance_self_protection(base_ref, paths, branch, errors, candidate_ref)
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
