from __future__ import annotations

from pathlib import Path


SCAN_DIRS = ("core", "dashboard", "scripts", "runtime", "tools", "strategies")
FORBIDDEN_PATTERNS = (
    'Path("logs"',
    "Path('logs'",
    'Path("data"',
    "Path('data'",
    '"logs/',
    "'logs/",
    '".runtime/logs',
    "'.runtime/logs",
    '"runtime/logs',
    "'runtime/logs",
    '"data/',
    "'data/",
)

# Keep this list short and explicit. Only use when a literal is required for
# path-hardening scanners (for example, health gate policy checks).
ALLOWLIST_EXACT: dict[str, set[int]] = {
    "scripts/check_today_candidates.py": {5, 6},
    "scripts/get_candidate_details.py": {5, 6},
    "scripts/monitor_live.py": {11, 12, 13, 14, 15},
    "scripts/build_eod_no_trade_evidence.py": {18, 20, 27, 34},
    "scripts/analyze_today.py": {5, 6},
    "scripts/check_morning.py": {5, 6},
    "scripts/analyze_past.py": {5, 6},
    "scripts/analyze_blocked_candidates.py": {6, 7},
    "scripts/show_candidates.py": {12, 14},
    "scripts/run_trend_exhaustion_research.py": {29},
    "scripts/run_mean_reversion_spec_truth_audit.py": {51},
    "scripts/run_trend_exhaustion_reversion_v2_research.py": {34},
    "scripts/verify_hits.py": {7},
    "scripts/mean_reversion_passive_live_observer.py": {10},
    "scripts/run_concentration_audit.py": {16},
    "scripts/run_exhaustion_audit.py": {17},
    "scripts/run_bugfix_evaluator.py": {15},
    "scripts/run_mean_reversion_parity_audit.py": {15},
    "scripts/run_ohlcv_strategy_evidence.py": {164},
    "scripts/run_mean_reversion_deepdive.py": {163},
    "core/eod_no_trade_evidence.py": {69},
    "scripts/check_today_candidates.py": {5},
    "scripts/get_candidate_details.py": {5},
    "scripts/monitor_live.py": {11, 12, 13},
    "scripts/build_eod_no_trade_evidence.py": {18, 20},
    "scripts/analyze_today.py": {5},
    "scripts/check_morning.py": {5},
    "scripts/analyze_past.py": {5},
    "scripts/analyze_blocked_candidates.py": {6},
    "scripts/show_candidates.py": {12},
}


def _iter_python_files(repo_root: Path):
    for folder in SCAN_DIRS:
        base = repo_root / folder
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if any(part in {"tests", "docs"} for part in path.parts):
                continue
            yield path


def _next_doc_state(line: str, in_doc: bool, delim: str | None) -> tuple[bool, str | None]:
    quote_patterns = ("'''", '"""')
    if in_doc and delim is not None:
        if delim in line and line.count(delim) % 2 == 1:
            return False, None
        return True, delim
    for candidate in quote_patterns:
        if candidate not in line:
            continue
        if line.count(candidate) % 2 == 1:
            return True, candidate
    return False, None


def test_no_hardcoded_paths_repo_wide():
    repo_root = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    for path in _iter_python_files(repo_root):
        rel = str(path.relative_to(repo_root))
        allowed_lines = ALLOWLIST_EXACT.get(rel, set())
        in_doc = False
        delim: str | None = None
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            next_in_doc, next_delim = _next_doc_state(line, in_doc, delim)
            if not in_doc and stripped.startswith("#"):
                in_doc, delim = next_in_doc, next_delim
                continue
            if in_doc:
                in_doc, delim = next_in_doc, next_delim
                continue
            if line_no in allowed_lines:
                in_doc, delim = next_in_doc, next_delim
                continue
            if any(pattern in line for pattern in FORBIDDEN_PATTERNS):
                violations.append(f"{rel}:{line_no}: {stripped[:220]}")
            in_doc, delim = next_in_doc, next_delim

    assert not violations, "Hardcoded logs/data paths detected:\n" + "\n".join(violations)

