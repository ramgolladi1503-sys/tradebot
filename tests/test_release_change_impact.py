import pytest
from core.release_change_impact import DependencyEvidence, Impact, classify, CRITICAL_GATES


def graph(complete=True, unresolved=frozenset()):
    return DependencyEvidence(
        edges={"main.py": frozenset({"core/feed.py"}), "core/feed.py": frozenset({"shared.py"}),
               "shared.py": frozenset(), "rank.py": frozenset({"scores.py"}), "scores.py": frozenset(),
               "docs/report.md": frozenset()},
        critical_roots=frozenset({"main.py"}), bounded_roots=frozenset({"rank.py"}),
        complete=complete, unresolved=unresolved)


def test_transitive_critical_dependency():
    result = classify(["shared.py"], graph())
    assert result["impact"] == Impact.CRITICAL.value
    assert CRITICAL_GATES.issubset(result["required_gates"])


def test_bounded_reachability():
    result = classify(["scores.py"], graph())
    assert result["impact"] == Impact.BOUNDED.value
    assert "decision_isolation" in result["required_gates"]
    assert not CRITICAL_GATES.intersection(result["required_gates"])


@pytest.mark.parametrize("g", [graph(False), graph(unresolved=frozenset({"dynamic_import"}))])
def test_incomplete_graph_cannot_prove_no_impact(g):
    result = classify(["docs/report.md"], g)
    assert result["impact"] == Impact.UNKNOWN.value
    assert CRITICAL_GATES.issubset(result["required_gates"])


def test_docs_path_does_not_override_runtime_reachability():
    g = graph()
    g.edges["core/feed.py"] = frozenset({"docs/report.md"})
    assert classify(["docs/report.md"], g)["impact"] == Impact.CRITICAL.value


def test_complete_unreachable_document_is_no_impact():
    assert classify(["docs/report.md"], graph())["impact"] == Impact.NONE.value


def test_unrecognized_new_file_is_unknown():
    assert classify(["new_module.py"], graph())["impact"] == Impact.UNKNOWN.value


def test_order_duplicates_and_cycles_deterministic():
    g = graph()
    g.edges["shared.py"] = frozenset({"core/feed.py"})
    assert classify(["shared.py", "scores.py", "shared.py"], g) == classify(["scores.py", "shared.py"], g)


@pytest.mark.parametrize("path", ["../main.py", "/main.py", "a/../b", "./main.py", "a\\b", ""])
def test_invalid_paths_rejected(path):
    with pytest.raises(ValueError):
        classify([path], graph())
