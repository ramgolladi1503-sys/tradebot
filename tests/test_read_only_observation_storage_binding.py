import ast
from pathlib import Path


SOURCE = Path(__file__).parents[1] / "core" / "kite_read_only_observation_runtime.py"


def _statement_index(body, predicate):
    for index, statement in enumerate(body):
        if predicate(statement):
            return index
    raise AssertionError("expected statement was not found")


def test_storage_environment_is_bound_before_depth_store_import():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_observation"
    )

    env_update_index = _statement_index(
        function.body,
        lambda node: (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Attribute)
            and isinstance(node.value.func.value.value, ast.Name)
            and node.value.func.value.value.id == "os"
            and node.value.func.value.attr == "environ"
            and node.value.func.attr == "update"
        ),
    )
    depth_import_index = _statement_index(
        function.body,
        lambda node: (
            isinstance(node, ast.Import)
            and any(alias.name == "core.depth_store" for alias in node.names)
        ),
    )

    assert env_update_index < depth_import_index
