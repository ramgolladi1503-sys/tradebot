from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from tools.repo_forensics.config_loader import ForensicsConfig


TEST_CLASSES = {
    "SHAPE_ONLY",
    "UNIT_BEHAVIOR",
    "INTEGRATION_WIRING",
    "SAFETY_REGRESSION",
    "RUNTIME_COMMAND",
    "EVIDENCE_CONTRACT",
    "FAKE_CONFIDENCE",
    "UNKNOWN",
}


@dataclass(frozen=True)
class TestRealityStatus:
    path: str
    test_class: str
    strength: str
    evidence: str
    risks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TestRealityReport:
    tests: list[TestRealityStatus] = field(default_factory=list)

    @property
    def class_counts(self) -> Counter[str]:
        return Counter(item.test_class for item in self.tests)

    @property
    def fake_confidence_tests(self) -> list[TestRealityStatus]:
        return [item for item in self.tests if item.test_class == "FAKE_CONFIDENCE"]

    @property
    def shape_only_tests(self) -> list[TestRealityStatus]:
        return [item for item in self.tests if item.test_class == "SHAPE_ONLY"]

    @property
    def unknown_tests(self) -> list[TestRealityStatus]:
        return [item for item in self.tests if item.test_class == "UNKNOWN"]


def classify_tests(repo_root: str | Path, config: ForensicsConfig) -> TestRealityReport:
    root = Path(repo_root).resolve()
    tests: list[TestRealityStatus] = []
    for path in sorted(root.rglob("test_*.py")):
        if _should_skip(path, root, config):
            continue
        tests.append(_classify_test_file(root, path))
    for path in sorted((root / "tests").rglob("*.py")) if (root / "tests").exists() else []:
        if path.name.startswith("test_") or _should_skip(path, root, config):
            continue
        tests.append(_classify_test_file(root, path))
    return TestRealityReport(tests=tests)


def _classify_test_file(repo_root: Path, path: Path) -> TestRealityStatus:
    rel = path.relative_to(repo_root).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return TestRealityStatus(rel, "UNKNOWN", "weak", "unreadable_test_file")

    lowered = source.lower()
    risks = _risk_markers(lowered)
    assertion_count = _assertion_count(source)
    evidence = []

    if _has_fake_confidence_markers(lowered, source):
        evidence.append("fake_confidence_marker")
        return TestRealityStatus(rel, "FAKE_CONFIDENCE", "weak", ",".join(evidence), risks)

    if _has_safety_markers(lowered):
        evidence.append("safety_regression_marker")
        return TestRealityStatus(rel, "SAFETY_REGRESSION", "strong" if assertion_count else "medium", ",".join(evidence), risks)

    if _has_evidence_contract_markers(lowered):
        evidence.append("evidence_contract_marker")
        return TestRealityStatus(rel, "EVIDENCE_CONTRACT", "strong" if assertion_count else "medium", ",".join(evidence), risks)

    if _has_runtime_command_markers(lowered):
        evidence.append("runtime_command_marker")
        return TestRealityStatus(rel, "RUNTIME_COMMAND", "medium", ",".join(evidence), risks)

    if _has_integration_markers(lowered):
        evidence.append("integration_wiring_marker")
        return TestRealityStatus(rel, "INTEGRATION_WIRING", "medium", ",".join(evidence), risks)

    if _looks_shape_only(source, lowered, assertion_count):
        evidence.append("shape_only_assertions")
        return TestRealityStatus(rel, "SHAPE_ONLY", "weak", ",".join(evidence), risks)

    if assertion_count:
        evidence.append("behavior_assertions_present")
        return TestRealityStatus(rel, "UNIT_BEHAVIOR", "medium", ",".join(evidence), risks)

    return TestRealityStatus(rel, "UNKNOWN", "weak", "no_assertion_signal", risks)


def _assertion_count(source: str) -> int:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source.count("assert ")
    return sum(1 for node in ast.walk(tree) if isinstance(node, ast.Assert))


def _has_fake_confidence_markers(lowered: str, source: str) -> bool:
    weak_assertions = [
        "assert true",
        "assert len(",
        "assert result is not none",
        "assert response is not none",
        "assert data is not none",
    ]
    if any(marker in lowered for marker in weak_assertions):
        return True
    if "except exception" in lowered and "pass" in lowered:
        return True
    if "mock" in lowered and "place_order" in lowered and "broker_api_called" not in lowered:
        return True
    if source.count("assert ") == 1 and any(marker in lowered for marker in [" in result", " in data", " in report"]):
        return True
    return False


def _has_safety_markers(lowered: str) -> bool:
    markers = [
        "broker_api_called",
        "is_order_action",
        "live_order_action",
        "paper_path",
        "sim_path",
        "fallback_data_not_executable",
        "stale_feed",
        "risk_rejected",
        "kill_switch",
        "place_order",
    ]
    return any(marker in lowered for marker in markers)


def _has_evidence_contract_markers(lowered: str) -> bool:
    markers = [
        "candidate_id",
        "decision",
        "reason",
        "evidence",
        "audit_log",
        "report",
        "jsonl",
        "runtime_health",
    ]
    return any(marker in lowered for marker in markers) and "assert" in lowered


def _has_runtime_command_markers(lowered: str) -> bool:
    markers = ["subprocess", "run_repo_forensics", "run_live.sh", "main.py", "command", "cli"]
    return any(marker in lowered for marker in markers)


def _has_integration_markers(lowered: str) -> bool:
    markers = ["orchestrator", "pipeline", "wiring", "import_graph", "runtime_wiring", "critical_module"]
    return any(marker in lowered for marker in markers)


def _looks_shape_only(source: str, lowered: str, assertion_count: int) -> bool:
    if assertion_count == 0:
        return False
    shape_markers = [
        " in result",
        " in data",
        " in report",
        "hasattr(",
        "isinstance(",
        ".keys()",
        "len(",
    ]
    behavior_markers = ["== false", " is false", "raises(", "not in", "!=", "blocked", "rejected"]
    return any(marker in lowered for marker in shape_markers) and not any(marker in lowered for marker in behavior_markers)


def _risk_markers(lowered: str) -> list[str]:
    risks: list[str] = []
    if "mock" in lowered:
        risks.append("mock_heavy")
    if "place_order" in lowered:
        risks.append("broker_adjacent")
    if "live" in lowered:
        risks.append("live_adjacent")
    if "fallback" in lowered:
        risks.append("fallback_adjacent")
    return risks


def _should_skip(path: Path, repo_root: Path, config: ForensicsConfig) -> bool:
    rel = path.relative_to(repo_root)
    if any(part in config.excluded_directories for part in rel.parts):
        return True
    if any(part in {".git", ".venv", "venv", "__pycache__"} for part in rel.parts):
        return True
    return False
