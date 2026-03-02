from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PATTERNS = (
    'Path("logs/',
    "Path('logs/",
    'pathlib.Path("logs/',
    "pathlib.Path('logs/",
    'Path("data/',
    "Path('data/",
    'pathlib.Path("data/',
    "pathlib.Path('data/",
    '"/logs/"',
    "'/logs/'",
    '"/data/"',
    "'/data/'",
)

ALLOWED_HINTS = (
    "logs_dir(",
    "cfg.TRADE_DB_PATH",
    "resolve_trade_log_path(",
    "ensure_trade_log_file(",
    "core.paths.",
    "# ALLOW_HARDCODE_PATH",
)


def _iter_python_files(base_dir: Path) -> list[Path]:
    return sorted(p for p in base_dir.rglob("*.py") if p.is_file())


def _is_comment_only(line: str) -> bool:
    return line.strip().startswith("#")


def _next_docstring_state(line: str, in_doc: bool, delim: str | None) -> tuple[bool, str | None]:
    quote_patterns = ("'''", '"""')

    if in_doc and delim is not None:
        if delim in line and line.count(delim) % 2 == 1:
            return False, None
        return True, delim

    for candidate in quote_patterns:
        if candidate not in line:
            continue
        count = line.count(candidate)
        if count % 2 == 1:
            return True, candidate
    return False, None


def _scan_for_hardcoded_paths(py_files: list[Path]) -> list[tuple[str, int, str]]:
    violations: list[tuple[str, int, str]] = []
    for file_path in py_files:
        in_doc = False
        delim: str | None = None
        for line_no, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            next_in_doc, next_delim = _next_docstring_state(line, in_doc, delim)

            # Ignore comment-only lines and docstring bodies.
            if not in_doc and _is_comment_only(line):
                in_doc, delim = next_in_doc, next_delim
                continue
            if in_doc:
                in_doc, delim = next_in_doc, next_delim
                continue

            if any(hint in line for hint in ALLOWED_HINTS):
                in_doc, delim = next_in_doc, next_delim
                continue

            if any(pattern in line for pattern in FORBIDDEN_PATTERNS):
                rel = str(file_path.relative_to(REPO_ROOT))
                violations.append((rel, line_no, stripped[:200]))

            in_doc, delim = next_in_doc, next_delim
    return violations


def _format_violations(violations: list[tuple[str, int, str]]) -> str:
    rows = [
        "Hardcoded repo-relative logs/data paths detected. Use canonical helpers (logs_dir(), cfg.TRADE_DB_PATH, resolve_trade_log_path(), etc.):"
    ]
    rows.extend(f"- {path}:{line_no}: {line}" for path, line_no, line in violations)
    return "\n".join(rows)


def test_dashboard_no_hardcoded_logs_or_data_paths() -> None:
    dashboard_dir = REPO_ROOT / "dashboard"
    violations = _scan_for_hardcoded_paths(_iter_python_files(dashboard_dir))
    assert not violations, _format_violations(violations)


def test_scripts_no_hardcoded_logs_or_data_paths() -> None:
    # Scope to high-impact operational scripts; broader migration can extend this list.
    target_scripts = [
        REPO_ROOT / "scripts" / "reconcile_fills.py",
        REPO_ROOT / "scripts" / "reconcile_outcomes_truth.py",
        REPO_ROOT / "scripts" / "execution_diagnostics.py",
    ]
    violations = _scan_for_hardcoded_paths([p for p in target_scripts if p.exists()])
    assert not violations, _format_violations(violations)
