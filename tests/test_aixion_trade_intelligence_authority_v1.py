from __future__ import annotations

import ast
from pathlib import Path


FORBIDDEN_CALLS = {
    "place_order",
    "modify_order",
    "cancel_order",
    "exit_order",
}


def _called_attribute_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Attribute):
            names.add(function.attr)
        elif isinstance(function, ast.Name):
            names.add(function.id)
    return names


def test_sidecar_has_no_broker_order_authority():
    repository_root = Path(__file__).resolve().parents[1]
    inspected = sorted((repository_root / "aixion_trade_intelligence").glob("*.py"))
    inspected.extend(
        [
            repository_root / "scripts" / "run_aixion_trade_intelligence_offline.py",
            repository_root / "scripts" / "generate_aixion_trade_intelligence_fixture.py",
            repository_root / "scripts" / "check_aixion_trade_intelligence_canary.py",
        ]
    )
    violations: dict[str, list[str]] = {}
    for path in inspected:
        called = _called_attribute_names(path)
        forbidden = sorted(called & FORBIDDEN_CALLS)
        if forbidden:
            violations[path.relative_to(repository_root).as_posix()] = forbidden
    broker_api_called = bool(violations)
    is_order_action = False
    assert broker_api_called is False
    assert is_order_action is False
    assert violations == {}
