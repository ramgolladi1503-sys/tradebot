from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _iter_strategy_decision_files() -> list[Path]:
    files: list[Path] = []
    core_dir = REPO_ROOT / "core"
    for path in sorted(core_dir.glob("decision*.py")):
        files.append(path)
    for path in sorted(core_dir.glob("strategy*.py")):
        files.append(path)
    trade_state_engine = core_dir / "trade_state_engine.py"
    if trade_state_engine.exists():
        files.append(trade_state_engine)
    for path in sorted((REPO_ROOT / "strategies").glob("*.py")):
        files.append(path)
    # Guard explicitly covers decision DAG entrypoint.
    dag = core_dir / "decision_dag.py"
    if dag.exists() and dag not in files:
        files.append(dag)
    return files


def test_no_strategy_bypasses_snapshot() -> None:
    violations: list[str] = []
    for path in _iter_strategy_decision_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "core.market_data":
                    imported = {alias.name for alias in node.names}
                    if "fetch_live_market_data" in imported:
                        violations.append(
                            f"{path}:L{node.lineno} forbidden import from core.market_data: fetch_live_market_data"
                        )

            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "core.market_data":
                        violations.append(
                            f"{path}:L{node.lineno} forbidden module import: core.market_data"
                        )

            if isinstance(node, ast.Call):
                # core.market_data.fetch_live_market_data(...)
                if isinstance(node.func, ast.Attribute):
                    owner = node.func.value
                    if (
                        isinstance(owner, ast.Attribute)
                        and isinstance(owner.value, ast.Name)
                        and owner.value.id == "core"
                        and owner.attr == "market_data"
                        and node.func.attr == "fetch_live_market_data"
                    ):
                        violations.append(
                            f"{path}:L{node.lineno} forbidden call: core.market_data.fetch_live_market_data"
                        )
                # fetch_live_market_data(...)
                if isinstance(node.func, ast.Name) and node.func.id == "fetch_live_market_data":
                    violations.append(f"{path}:L{node.lineno} forbidden call: fetch_live_market_data")

            # depth_store in strategy/decision functions indicates bypass of snapshot payload
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if isinstance(child, ast.Name) and child.id == "depth_store":
                        violations.append(
                            f"{path}:L{child.lineno} forbidden depth_store usage in function {node.name}"
                        )

    assert not violations, "Snapshot bypass violations found:\n" + "\n".join(sorted(violations))
