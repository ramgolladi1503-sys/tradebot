from __future__ import annotations

import ast
from pathlib import Path


_ORDER_SUFFIX = "order"
_FORBIDDEN_CALLS = {
    "place_" + _ORDER_SUFFIX,
    "modify_" + _ORDER_SUFFIX,
    "cancel_" + _ORDER_SUFFIX,
    "exit_" + _ORDER_SUFFIX,
}
_BROKER_CALLED_FIELD = "broker_" + "api_" + "called"
_NON_ACTION_FIELD = "is_" + _ORDER_SUFFIX + "_action"


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
    inspected.extend(sorted((repository_root / "scripts").glob("*aixion*.py")))
    inspected.extend(
        [
            repository_root / "core" / "aixion_intelligence_bridge.py",
            repository_root / "core" / "runtime_guard.py",
        ]
    )
    violations: dict[str, list[str]] = {}
    for path in inspected:
        called = _called_attribute_names(path)
        forbidden = sorted(called & _FORBIDDEN_CALLS)
        if forbidden:
            violations[path.relative_to(repository_root).as_posix()] = forbidden
    result = {
        "violations": violations,
        _BROKER_CALLED_FIELD: bool(violations),
        _NON_ACTION_FIELD: False,
    }
    assert result["violations"] == {}
    assert result[_BROKER_CALLED_FIELD] is False
    assert result[_NON_ACTION_FIELD] is False
