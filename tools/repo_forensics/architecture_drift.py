from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from tools.repo_forensics.config_loader import ForensicsConfig


@dataclass(frozen=True)
class ArchitectureDriftFinding:
    path: str
    severity: str
    drift_type: str
    evidence: str


@dataclass(frozen=True)
class ArchitectureDriftReport:
    findings: list[ArchitectureDriftFinding] = field(default_factory=list)

    @property
    def high(self) -> list[ArchitectureDriftFinding]:
        return [item for item in self.findings if item.severity == "HIGH"]

    @property
    def medium(self) -> list[ArchitectureDriftFinding]:
        return [item for item in self.findings if item.severity == "MEDIUM"]

    @property
    def unknown(self) -> list[ArchitectureDriftFinding]:
        return [item for item in self.findings if item.severity == "UNKNOWN"]


def detect_architecture_drift(repo_root: str | Path, config: ForensicsConfig) -> ArchitectureDriftReport:
    root = Path(repo_root).resolve()
    files = list(_iter_python_files(root, config))
    findings: list[ArchitectureDriftFinding] = []
    findings.extend(_duplicate_module_stems(root, files, config))
    findings.extend(_legacy_current_split(root, files, config))
    findings.extend(_missing_critical_module_doc_refs(root, config))
    findings.extend(_dashboard_evidence_reader_drift(root, config))
    return ArchitectureDriftReport(findings=findings)


def _duplicate_module_stems(
    repo_root: Path,
    files: list[Path],
    config: ForensicsConfig,
) -> list[ArchitectureDriftFinding]:
    watch_terms = _watch_terms(config)
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        stem = path.stem.lower()
        if stem in {"__init__", "conftest"}:
            continue
        rel = path.relative_to(repo_root).as_posix()
        if _is_test_or_tooling(rel):
            continue
        if watch_terms and not any(term in stem or term in rel.lower() for term in watch_terms):
            continue
        grouped[stem].append(path)

    findings: list[ArchitectureDriftFinding] = []
    for stem, paths in sorted(grouped.items()):
        if len(paths) < 2:
            continue
        rel_paths = [path.relative_to(repo_root).as_posix() for path in paths]
        findings.append(
            ArchitectureDriftFinding(
                path=", ".join(rel_paths[:5]),
                severity="MEDIUM",
                drift_type="duplicate_module_stem",
                evidence=f"stem={stem} count={len(rel_paths)}",
            )
        )
    return findings


def _legacy_current_split(
    repo_root: Path,
    files: list[Path],
    config: ForensicsConfig,
) -> list[ArchitectureDriftFinding]:
    watch_terms = _watch_terms(config)
    legacy_markers = {"legacy", "old", "deprecated", "stale"}
    current_markers = {"v2", "new", "pro", "runtime", "current"}
    by_term: dict[str, dict[str, list[str]]] = defaultdict(lambda: {"legacy": [], "current": []})

    for path in files:
        rel = path.relative_to(repo_root).as_posix()
        lowered = rel.lower()
        if _is_test_or_tooling(rel):
            continue
        for term in watch_terms:
            if term not in lowered:
                continue
            if any(marker in lowered for marker in legacy_markers):
                by_term[term]["legacy"].append(rel)
            if any(marker in lowered for marker in current_markers):
                by_term[term]["current"].append(rel)

    findings: list[ArchitectureDriftFinding] = []
    for term, groups in sorted(by_term.items()):
        if groups["legacy"] and groups["current"]:
            sample = (groups["legacy"] + groups["current"])[:6]
            findings.append(
                ArchitectureDriftFinding(
                    path=", ".join(sample),
                    severity="MEDIUM",
                    drift_type="old_new_pipeline_split",
                    evidence=f"watch_area={term} legacy={len(groups['legacy'])} current={len(groups['current'])}",
                )
            )
    return findings


def _missing_critical_module_doc_refs(repo_root: Path, config: ForensicsConfig) -> list[ArchitectureDriftFinding]:
    configured_paths = {path for paths in config.critical_modules.values() for path in paths}
    missing_paths = {path for path in configured_paths if not (repo_root / path).exists()}
    if not missing_paths:
        return []

    findings: list[ArchitectureDriftFinding] = []
    for doc in _iter_doc_files(repo_root, config):
        rel = doc.relative_to(repo_root).as_posix()
        try:
            text = doc.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        referenced = sorted(path for path in missing_paths if path in text)
        if referenced:
            findings.append(
                ArchitectureDriftFinding(
                    path=rel,
                    severity="UNKNOWN",
                    drift_type="doc_references_missing_critical_module",
                    evidence=",".join(referenced[:5]),
                )
            )
    return findings


def _dashboard_evidence_reader_drift(repo_root: Path, config: ForensicsConfig) -> list[ArchitectureDriftFinding]:
    dashboard_files = [path for path in _iter_python_files(repo_root, config) if path.relative_to(repo_root).as_posix().startswith("dashboard/")]
    if not dashboard_files:
        return []

    configured_evidence_terms = {Path(path).name for path in config.runtime_evidence_paths if Path(path).name}
    configured_evidence_terms.update(Path(path).as_posix() for path in config.runtime_evidence_paths)

    findings: list[ArchitectureDriftFinding] = []
    evidence_reader_files: list[str] = []
    for path in dashboard_files:
        rel = path.relative_to(repo_root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lowered = text.lower()
        if any(marker in lowered for marker in ["json", "report", "log", "snapshot", "evidence"]):
            evidence_reader_files.append(rel)
            if not configured_evidence_terms:
                findings.append(
                    ArchitectureDriftFinding(
                        path=rel,
                        severity="UNKNOWN",
                        drift_type="dashboard_evidence_reader_unproven",
                        evidence="dashboard_reads_evidence_like_data_but_no_evidence_paths_configured",
                    )
                )
                continue
            if not any(term.lower() in lowered for term in configured_evidence_terms):
                findings.append(
                    ArchitectureDriftFinding(
                        path=rel,
                        severity="UNKNOWN",
                        drift_type="dashboard_evidence_reader_unproven",
                        evidence="dashboard_reads_evidence_like_data_without_configured_path_reference",
                    )
                )
    if not evidence_reader_files:
        findings.append(
            ArchitectureDriftFinding(
                path="dashboard",
                severity="UNKNOWN",
                drift_type="dashboard_evidence_reader_missing",
                evidence="dashboard_files_exist_but_no_evidence_reader_signal_found",
            )
        )
    return findings


def _watch_terms(config: ForensicsConfig) -> set[str]:
    params = config.data.get("agent_parameters", {})
    terms: set[str] = set()
    if isinstance(params, dict):
        drift = params.get("architecture_drift", {})
        if isinstance(drift, dict):
            watch = drift.get("watch_areas", [])
            if isinstance(watch, list):
                terms.update(_normalize_term(str(item)) for item in watch)
    if not terms:
        for group in config.critical_modules:
            terms.add(_normalize_term(group))
    return {term for term in terms if term}


def _normalize_term(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _iter_python_files(repo_root: Path, config: ForensicsConfig) -> Iterable[Path]:
    for path in repo_root.rglob("*.py"):
        if _should_skip(path, repo_root, config):
            continue
        yield path


def _iter_doc_files(repo_root: Path, config: ForensicsConfig) -> Iterable[Path]:
    for suffix in ("*.md", "*.txt", "*.rst"):
        for path in repo_root.rglob(suffix):
            if _should_skip(path, repo_root, config):
                continue
            yield path


def _should_skip(path: Path, repo_root: Path, config: ForensicsConfig) -> bool:
    rel = path.relative_to(repo_root)
    if any(part in config.excluded_directories for part in rel.parts):
        return True
    if any(part in {".git", ".venv", "venv", "__pycache__"} for part in rel.parts):
        return True
    return False


def _is_test_or_tooling(path: str) -> bool:
    parts = path.split("/")
    return bool(parts and parts[0] in {"tests", "testing", "tools"}) or Path(path).name.startswith("test_")
