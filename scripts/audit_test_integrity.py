from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


BLOCKING_KINDS = {
    "unconditional_assert_true",
    "skipped_test",
    "empty_test",
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    test_name: str
    kind: str
    severity: str
    message: str
    changed: bool


def _qualified_name(node: ast.AST) -> str:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = _qualified_name(target)
        if name:
            names.add(name)
    return names


def _is_docstring_statement(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _effective_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = list(node.body)
    if body and _is_docstring_statement(body[0]):
        body = body[1:]
    return body


def _has_oracle(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            return True
        if isinstance(child, ast.With):
            for item in child.items:
                context_name = _qualified_name(
                    item.context_expr.func
                    if isinstance(item.context_expr, ast.Call)
                    else item.context_expr
                )
                if context_name in {
                    "pytest.raises",
                    "pytest.warns",
                    "unittest.TestCase.assertRaises",
                }:
                    return True
        if isinstance(child, ast.Call):
            name = _qualified_name(child.func)
            if name in {"pytest.fail", "pytest.raises", "pytest.warns"}:
                return True
            if name.startswith("self.assert"):
                return True
            if name.endswith(
                (
                    ".assert_called",
                    ".assert_called_once",
                    ".assert_called_with",
                    ".assert_called_once_with",
                    ".assert_not_called",
                    ".assert_any_call",
                    ".assert_has_calls",
                )
            ):
                return True
    return False


def _function_findings(
    path: Path,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    changed: bool,
) -> list[Finding]:
    if not node.name.startswith("test"):
        return []

    findings: list[Finding] = []
    decorators = _decorator_names(node)
    if any(name in {"pytest.mark.skip", "pytest.mark.skipif"} for name in decorators):
        findings.append(
            Finding(
                path=str(path),
                line=node.lineno,
                test_name=node.name,
                kind="skipped_test",
                severity="error" if changed else "warning",
                message="Test is disabled by skip/skipif and cannot count as active evidence.",
                changed=changed,
            )
        )

    body = _effective_body(node)
    if not body or all(
        isinstance(statement, ast.Pass)
        or (
            isinstance(statement, ast.Return)
            and (
                statement.value is None
                or (
                    isinstance(statement.value, ast.Constant)
                    and statement.value.value is None
                )
            )
        )
        for statement in body
    ):
        findings.append(
            Finding(
                path=str(path),
                line=node.lineno,
                test_name=node.name,
                kind="empty_test",
                severity="error" if changed else "warning",
                message="Test has no executable verification body.",
                changed=changed,
            )
        )

    for child in ast.walk(node):
        if (
            isinstance(child, ast.Assert)
            and isinstance(child.test, ast.Constant)
            and child.test.value is True
        ):
            findings.append(
                Finding(
                    path=str(path),
                    line=child.lineno,
                    test_name=node.name,
                    kind="unconditional_assert_true",
                    severity="error" if changed else "warning",
                    message="Unconditional `assert True` is not test evidence.",
                    changed=changed,
                )
            )

    if not _has_oracle(node):
        findings.append(
            Finding(
                path=str(path),
                line=node.lineno,
                test_name=node.name,
                kind="no_local_oracle_detected",
                severity="review",
                message=(
                    "No local assertion/raises/warns/mock assertion was detected. "
                    "The test may rely on helper assertions or exception-free execution and needs review."
                ),
                changed=changed,
            )
        )

    return findings


def audit_file(path: Path, *, changed: bool = False) -> tuple[list[Finding], str | None]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        finding = Finding(
            path=str(path),
            line=getattr(exc, "lineno", 1) or 1,
            test_name="<module>",
            kind="unparseable_test_file",
            severity="error" if changed else "warning",
            message=f"Could not parse test file: {type(exc).__name__}: {exc}",
            changed=changed,
        )
        return [finding], str(exc)

    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            findings.extend(_function_findings(path, node, changed=changed))
    return findings, None


def _python_files(roots: Iterable[Path]) -> list[Path]:
    files: set[Path] = set()
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            files.add(root)
        elif root.exists():
            files.update(root.rglob("test_*.py"))
            files.update(root.rglob("*_test.py"))
    return sorted(files)


def changed_test_paths(base_ref: str | None) -> set[str]:
    if not base_ref:
        return set()
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git diff failed")
    return {
        line.strip()
        for line in proc.stdout.splitlines()
        if line.strip().endswith(".py")
        and (
            line.strip().startswith("tests/")
            or line.strip().startswith("testing/tests/")
        )
    }


def run_audit(
    roots: Iterable[Path],
    *,
    changed_paths: set[str] | None = None,
) -> dict[str, object]:
    changed_paths = changed_paths or set()
    files = _python_files(roots)
    findings: list[Finding] = []
    for path in files:
        normalized = path.as_posix()
        file_findings, _ = audit_file(path, changed=normalized in changed_paths)
        findings.extend(file_findings)

    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.kind] = counts.get(finding.kind, 0) + 1

    blocking = [
        finding
        for finding in findings
        if finding.changed
        and (
            finding.kind in BLOCKING_KINDS
            or finding.kind == "unparseable_test_file"
        )
    ]
    return {
        "schema_version": 1,
        "files_scanned": len(files),
        "changed_test_files": sorted(changed_paths),
        "finding_counts": dict(sorted(counts.items())),
        "blocking_count": len(blocking),
        "findings": [asdict(finding) for finding in findings],
    }


def _write_markdown(report: dict[str, object], path: Path) -> None:
    counts = report["finding_counts"]
    findings = report["findings"]
    lines = [
        "# Test Integrity Audit",
        "",
        f"- Files scanned: {report['files_scanned']}",
        f"- Changed test files: {len(report['changed_test_files'])}",
        f"- Blocking findings in changed tests: {report['blocking_count']}",
        "",
        "## Finding counts",
        "",
    ]
    if counts:
        for key, value in counts.items():
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- None")
    lines.extend(["", "## Changed-test findings", ""])
    changed_findings = [finding for finding in findings if finding["changed"]]
    if changed_findings:
        for finding in changed_findings:
            lines.append(
                f"- `{finding['path']}:{finding['line']}` "
                f"`{finding['test_name']}` — **{finding['kind']}**: {finding['message']}"
            )
    else:
        lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit pytest files for weak or disabled evidence.")
    parser.add_argument(
        "--roots",
        nargs="+",
        default=["tests", "testing/tests"],
        help="Test roots or files to scan.",
    )
    parser.add_argument(
        "--changed-base",
        default=None,
        help="Git base ref used to identify changed test files.",
    )
    parser.add_argument(
        "--report-dir",
        default=".runtime/qa",
        help="Directory for JSON and Markdown reports.",
    )
    args = parser.parse_args()

    try:
        changed_paths = changed_test_paths(args.changed_base)
    except RuntimeError as exc:
        print(f"TEST INTEGRITY AUDIT: ERROR: {exc}", file=sys.stderr)
        return 2

    report = run_audit(
        [Path(root) for root in args.roots],
        changed_paths=changed_paths,
    )
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "test_integrity_report.json"
    md_path = report_dir / "test_integrity_report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    _write_markdown(report, md_path)

    print(
        "TEST INTEGRITY AUDIT: "
        f"files={report['files_scanned']} "
        f"changed={len(report['changed_test_files'])} "
        f"blocking={report['blocking_count']}"
    )
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    return 1 if report["blocking_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
