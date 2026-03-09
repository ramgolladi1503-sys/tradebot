from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Violation:
    code: str
    file: str
    line: int
    message: str


REPO_ROOT = Path(__file__).resolve().parents[1]

SCAN_DIRS = ("core", "dashboard", "scripts", "strategies")

# Intentional exception: dashboard deadlock breaker checks DB progress to trigger rerun.
DB_FRESHNESS_QUERY_ALLOWLIST = {
    "core/tick_store.py",
    "dashboard/streamlit_app.py",
}

# Freshness DB helper usage is only allowed in the SLA engine, tick store internals, and
# snapshot builder (which reads latest tick rows for payload fields, not to recompute SLA).
FRESHNESS_DB_HELPER_ALLOWLIST = {
    "core/freshness_sla.py",
    "core/market_snapshot_builder.py",
    "core/tick_store.py",
}

FORBIDDEN_SNAPSHOT_MEMORY_TOKENS = (
    "depth_store",
    "_LAST_TICK_BY_TOKEN",
    "_LAST_WS_TICK_EPOCH",
    "get_last_tick(",
    "last_tick_epoch(",
)


def _iter_python_files(repo_root: Path, dirs: Iterable[str]) -> list[Path]:
    out: list[Path] = []
    for folder in dirs:
        base = repo_root / folder
        if not base.exists():
            continue
        out.extend(sorted(base.rglob("*.py")))
    return out


def _rel(path: Path, repo_root: Path) -> str:
    return str(path.resolve().relative_to(repo_root.resolve()))


def _line_for_offset(text: str, offset: int) -> int:
    if offset <= 0:
        return 1
    return text.count("\n", 0, offset) + 1


def _scan_freshness_drift(repo_root: Path, files: list[Path]) -> list[Violation]:
    violations: list[Violation] = []
    sql_pat = re.compile(r"SELECT\s+MAX\(timestamp_epoch\)\s+FROM\s+ticks", re.IGNORECASE)

    for path in files:
        rel = _rel(path, repo_root)
        text = path.read_text(encoding="utf-8")

        # Enforce single authoritative public freshness function.
        if rel != "core/freshness_sla.py" and re.search(r"^\s*def\s+get_freshness_status\s*\(", text, re.MULTILINE):
            line_no = _line_for_offset(text, text.find("def get_freshness_status"))
            violations.append(
                Violation(
                    code="FRESHNESS_DUPLICATE_PROVIDER",
                    file=rel,
                    line=line_no,
                    message="freshness provider must be defined only in core/freshness_sla.py",
                )
            )

        # Catch accidental raw SQL freshness computations.
        for match in sql_pat.finditer(text):
            if rel in DB_FRESHNESS_QUERY_ALLOWLIST:
                continue
            violations.append(
                Violation(
                    code="FRESHNESS_RAW_SQL_OUTSIDE_ALLOWLIST",
                    file=rel,
                    line=_line_for_offset(text, match.start()),
                    message="raw MAX(timestamp_epoch) ticks freshness query is not allowed here",
                )
            )

        # Catch direct imports of DB freshness helpers outside allowlist.
        if rel.endswith(".py"):
            try:
                tree = ast.parse(text, filename=rel)
            except Exception:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                if node.module != "core.tick_store":
                    continue
                imported = {alias.name for alias in node.names}
                if not imported.intersection({"get_max_tick_epoch_db", "get_latest_tick_rows_db"}):
                    continue
                if rel in FRESHNESS_DB_HELPER_ALLOWLIST:
                    continue
                violations.append(
                    Violation(
                        code="FRESHNESS_DB_HELPER_OUTSIDE_ALLOWLIST",
                        file=rel,
                        line=int(getattr(node, "lineno", 1)),
                        message="freshness DB helper imported outside approved modules",
                    )
                )

    return violations


def _iter_strategy_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    core_dir = repo_root / "core"
    for path in sorted(core_dir.glob("decision*.py")):
        files.append(path)
    for path in sorted(core_dir.glob("strategy*.py")):
        files.append(path)
    for path in sorted((repo_root / "strategies").glob("*.py")):
        files.append(path)
    extra = [core_dir / "trade_state_engine.py", core_dir / "decision_dag.py"]
    for path in extra:
        if path.exists() and path not in files:
            files.append(path)
    return files


def _scan_strategy_market_data_imports(repo_root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for path in _iter_strategy_files(repo_root):
        rel = _rel(path, repo_root)
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=rel)
        except Exception:
            violations.append(
                Violation(
                    code="STRATEGY_PARSE_ERROR",
                    file=rel,
                    line=1,
                    message="unable to parse strategy file for contract checks",
                )
            )
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "core.market_data":
                violations.append(
                    Violation(
                        code="STRATEGY_IMPORTS_MARKET_DATA",
                        file=rel,
                        line=int(getattr(node, "lineno", 1)),
                        message="strategy/decision module must not import core.market_data directly",
                    )
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "core.market_data":
                        violations.append(
                            Violation(
                                code="STRATEGY_IMPORTS_MARKET_DATA",
                                file=rel,
                                line=int(getattr(node, "lineno", 1)),
                                message="strategy/decision module must not import core.market_data directly",
                            )
                        )
    return violations


def _scan_snapshot_builder_memory_cache(repo_root: Path) -> list[Violation]:
    path = repo_root / "core" / "market_snapshot_builder.py"
    if not path.exists():
        return [
            Violation(
                code="SNAPSHOT_BUILDER_MISSING",
                file="core/market_snapshot_builder.py",
                line=1,
                message="snapshot builder missing; cannot enforce memory cache contract",
            )
        ]

    rel = _rel(path, repo_root)
    text = path.read_text(encoding="utf-8")
    violations: list[Violation] = []
    for token in FORBIDDEN_SNAPSHOT_MEMORY_TOKENS:
        for match in re.finditer(re.escape(token), text):
            violations.append(
                Violation(
                    code="SNAPSHOT_BUILDER_MEMORY_CACHE_REFERENCE",
                    file=rel,
                    line=_line_for_offset(text, match.start()),
                    message=f"snapshot builder must not reference memory cache token '{token}'",
                )
            )
    return violations


def run_checks(repo_root: Path | None = None) -> list[Violation]:
    root = Path(repo_root or REPO_ROOT)
    files = _iter_python_files(root, SCAN_DIRS)
    violations: list[Violation] = []
    violations.extend(_scan_freshness_drift(root, files))
    violations.extend(_scan_strategy_market_data_imports(root))
    violations.extend(_scan_snapshot_builder_memory_cache(root))
    return sorted(violations, key=lambda v: (v.code, v.file, v.line))


def _format_violations(violations: list[Violation]) -> str:
    lines = ["Contract check failed. Violations:"]
    for item in violations:
        lines.append(
            f"- [{item.code}] {item.file}:{item.line} {item.message}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Static contract checker for drift-prone boundaries.")
    parser.add_argument("--repo-root", type=str, default=str(REPO_ROOT), help="Repository root path")
    args = parser.parse_args(argv)

    violations = run_checks(Path(args.repo_root))
    if violations:
        print(_format_violations(violations))
        return 1
    print("Contract check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
