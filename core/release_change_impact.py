"""Deterministic impact classification over an explicitly evidenced dependency graph.

Edges point from consumer to dependency. Graph completeness is a producer claim
that must be independently checked before certification; absence from an
incomplete graph never proves isolation. This module executes no project code.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Mapping


class Impact(str, Enum):
    NONE = "NO_LIVE_IMPACT"
    BOUNDED = "BOUNDED_LIVE_IMPACT"
    CRITICAL = "CRITICAL_LIVE_IMPACT"
    UNKNOWN = "UNKNOWN_IMPACT"


# These are semantic gate identifiers, not executable shell strings. The engine
# must bind each gate to a reviewed command and immutable evidence contract.
BASE_GATES = frozenset({"source_identity", "whole_tree_compile", "diff_check", "release_verifier"})
BOUNDED_GATES = frozenset({"decision_tests", "decision_isolation", "degraded_mode", "decision_mutations"})
CRITICAL_GATES = frozenset({"morning_readiness", "instrument_authority", "feed_subscription", "option_mirror", "persistence", "evidence_integrity", "cas_memory", "shutdown_seal", "security_authority", "critical_mutations"})


@dataclass(frozen=True)
class DependencyEvidence:
    edges: Mapping[str, frozenset[str]]
    critical_roots: frozenset[str]
    bounded_roots: frozenset[str]
    complete: bool
    unresolved: frozenset[str] = frozenset()


def _valid_path(value: str) -> bool:
    return bool(value) and not value.startswith("/") and "\\" not in value and ".." not in PurePosixPath(value).parts and str(PurePosixPath(value)) == value


def closure(roots: frozenset[str], edges: Mapping[str, frozenset[str]]) -> frozenset[str]:
    pending = list(roots)
    reached: set[str] = set()
    while pending:
        path = pending.pop()
        if path in reached:
            continue
        reached.add(path)
        pending.extend(edges.get(path, ()))
    return frozenset(reached)


def classify(changed_paths: list[str], graph: DependencyEvidence) -> dict:
    if any(not isinstance(path, str) or not _valid_path(path) for path in changed_paths):
        raise ValueError("invalid_changed_path")
    critical = closure(graph.critical_roots, graph.edges)
    bounded = closure(graph.bounded_roots, graph.edges)
    classified = {}
    for path in sorted(set(changed_paths)):
        # Reachability is evidence of impact even when other graph areas are unknown.
        if path in critical:
            impact, reason = Impact.CRITICAL, "reachable_from_critical_root"
        elif not graph.complete or graph.unresolved:
            impact, reason = Impact.UNKNOWN, "dependency_evidence_incomplete"
        elif path in bounded:
            impact, reason = Impact.BOUNDED, "bounded_reachability_only"
        elif path in graph.edges and path.endswith(".md"):
            impact, reason = Impact.NONE, "complete_graph_proves_document_unreachable"
        else:
            impact, reason = Impact.UNKNOWN, "unclassified_component"
        classified[path] = {"impact": impact.value, "reason": reason}
    impacts = {item["impact"] for item in classified.values()}
    overall = next((x for x in (Impact.UNKNOWN, Impact.CRITICAL, Impact.BOUNDED) if x.value in impacts), Impact.NONE)
    gates = set(BASE_GATES)
    if overall in {Impact.BOUNDED, Impact.CRITICAL, Impact.UNKNOWN}:
        gates.update(BOUNDED_GATES)
    if overall in {Impact.CRITICAL, Impact.UNKNOWN}:
        gates.update(CRITICAL_GATES)
    return {"impact": overall.value, "paths": classified, "required_gates": sorted(gates)}
