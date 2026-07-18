import ast
from pathlib import Path


RESOURCE_TEST_FILE = Path(__file__).with_name("test_feed_reconnect_resource_soak.py")
CONFTEST_FILE = Path(__file__).with_name("conftest.py")


def _literal_run_profile_cycles(function_node: ast.FunctionDef) -> list[int]:
    cycles: list[int] = []
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "run_profile":
            continue
        if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant):
            continue
        value = node.args[1].value
        if isinstance(value, int):
            cycles.append(value)
    return cycles


def _tier_sets() -> tuple[set[str], set[str]]:
    tree = ast.parse(CONFTEST_FILE.read_text(encoding="utf-8"))
    assignments: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id not in {
            "_FEED_RESOURCE_SOAK_TESTS",
            "_FEED_RESOURCE_CERTIFICATION_TESTS",
        }:
            continue
        value = ast.literal_eval(node.value)
        assignments[target.id] = set(value)

    return (
        assignments["_FEED_RESOURCE_SOAK_TESTS"],
        assignments["_FEED_RESOURCE_CERTIFICATION_TESTS"],
    )


def test_expensive_feed_profiles_have_non_default_tiers():
    resource_tree = ast.parse(RESOURCE_TEST_FILE.read_text(encoding="utf-8"))
    soak_tests, certification_tests = _tier_sets()

    discovered_soak: set[str] = set()
    discovered_certification: set[str] = set()
    for node in resource_tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        cycles = _literal_run_profile_cycles(node)
        if not cycles:
            continue
        maximum_cycles = max(cycles)
        if maximum_cycles >= 1000:
            discovered_certification.add(node.name)
        elif maximum_cycles >= 50:
            discovered_soak.add(node.name)

    assert certification_tests == discovered_certification
    assert soak_tests == discovered_soak
    assert soak_tests.isdisjoint(certification_tests)
