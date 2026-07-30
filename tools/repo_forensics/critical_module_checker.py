from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tools.repo_forensics.config_loader import ForensicsConfig
from tools.repo_forensics.import_graph import FileReferenceGraph, build_reference_graph


@dataclass(frozen=True)
class CriticalModuleStatus:
    group: str
    path: str
    status: str
    production_callers: list[str] = field(default_factory=list)
    test_callers: list[str] = field(default_factory=list)
    evidence: str = ""


@dataclass(frozen=True)
class CriticalModuleReport:
    statuses: dict[str, list[CriticalModuleStatus]] = field(default_factory=dict)

    @property
    def missing(self) -> list[CriticalModuleStatus]:
        return [
            item
            for items in self.statuses.values()
            for item in items
            if item.status == "MISSING"
        ]

    @property
    def test_only(self) -> list[CriticalModuleStatus]:
        return [
            item
            for items in self.statuses.values()
            for item in items
            if item.status == "TEST_ONLY"
        ]

    @property
    def unreferenced(self) -> list[CriticalModuleStatus]:
        return [
            item
            for items in self.statuses.values()
            for item in items
            if item.status == "UNREFERENCED"
        ]

    @property
    def entrypoints(self) -> list[CriticalModuleStatus]:
        return [
            item
            for items in self.statuses.values()
            for item in items
            if item.status == "ENTRYPOINT"
        ]


def check_critical_modules(
    repo_root: str | Path,
    config: ForensicsConfig,
    graph: FileReferenceGraph | None = None,
) -> CriticalModuleReport:
    root = Path(repo_root).resolve()
    reference_graph = graph or build_reference_graph(root, config)
    configured_entrypoints = {
        path.strip().lstrip("./")
        for path in (*config.required_entrypoints, *config.optional_entrypoints)
    }
    grouped: dict[str, list[CriticalModuleStatus]] = {}

    for group, paths in config.critical_modules.items():
        grouped[group] = []
        for module_path in paths:
            normalized = module_path.strip().lstrip("./")
            grouped[group].append(
                _status_for_module(
                    root,
                    group,
                    normalized,
                    reference_graph,
                    is_entrypoint=normalized in configured_entrypoints,
                )
            )
    return CriticalModuleReport(statuses=grouped)


def _status_for_module(
    repo_root: Path,
    group: str,
    module_path: str,
    graph: FileReferenceGraph,
    *,
    is_entrypoint: bool = False,
) -> CriticalModuleStatus:
    if not (repo_root / module_path).exists():
        return CriticalModuleStatus(
            group=group,
            path=module_path,
            status="MISSING",
            evidence="configured_critical_module_missing",
        )

    production_callers = sorted(graph.production_callers(module_path))
    test_callers = sorted(graph.test_callers(module_path))

    if is_entrypoint:
        return CriticalModuleStatus(
            group=group,
            path=module_path,
            status="ENTRYPOINT",
            production_callers=production_callers,
            test_callers=test_callers,
            evidence="configured_entrypoint_is_runtime_root",
        )
    if production_callers:
        return CriticalModuleStatus(
            group=group,
            path=module_path,
            status="PRODUCTION_REFERENCED",
            production_callers=production_callers,
            test_callers=test_callers,
            evidence="production_reference_found",
        )
    if test_callers:
        return CriticalModuleStatus(
            group=group,
            path=module_path,
            status="TEST_ONLY",
            production_callers=production_callers,
            test_callers=test_callers,
            evidence="test_references_only",
        )
    return CriticalModuleStatus(
        group=group,
        path=module_path,
        status="UNREFERENCED",
        production_callers=production_callers,
        test_callers=test_callers,
        evidence="no_static_references_found",
    )
