from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


CONFIRMED = "CONFIRMED"
LIKELY = "LIKELY"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FailureSignal:
    nodeid: str
    file: str | None = None
    module: str | None = None
    error_text: str | None = None
    fixture: str | None = None
    missing_field: str | None = None
    runtime_flow_step: str | None = None
    safety_boundary: str | None = None
    candidate_concept: str | None = None
    proof: str | None = None


@dataclass(frozen=True)
class FailureCluster:
    cluster_id: str
    reason: str
    confidence: str
    failures: tuple[FailureSignal, ...]
    proof: tuple[str, ...] = field(default_factory=tuple)

    @property
    def failure_count(self) -> int:
        return len(self.failures)

    @property
    def has_proof(self) -> bool:
        return bool(self.proof)


@dataclass(frozen=True)
class FailureClusterReport:
    clusters: tuple[FailureCluster, ...]

    @property
    def cluster_count(self) -> int:
        return len(self.clusters)

    @property
    def unknown(self) -> tuple[FailureCluster, ...]:
        return tuple(cluster for cluster in self.clusters if cluster.confidence == UNKNOWN)


@dataclass(frozen=True)
class FixContract:
    cluster_id: str
    allowed: bool
    reason: str
    proof: tuple[str, ...] = field(default_factory=tuple)


def cluster_failure_text(text: str) -> FailureClusterReport:
    """Cluster pytest/CI failure text by likely shared root-cause signals.

    This module is local and static. It does not call external agents, create PRs,
    mutate code, or suggest patches without proof.
    """

    signals = tuple(_parse_signals(text))
    buckets: dict[tuple[str, str], list[FailureSignal]] = defaultdict(list)
    for signal in signals:
        buckets[_cluster_key(signal)].append(signal)

    clusters = tuple(
        _build_cluster(index, reason, tuple(items))
        for index, ((reason, _value), items) in enumerate(sorted(buckets.items()), start=1)
    )
    return FailureClusterReport(clusters=clusters)


def build_fix_contract(cluster: FailureCluster) -> FixContract:
    if not cluster.has_proof or cluster.confidence == UNKNOWN:
        return FixContract(
            cluster_id=cluster.cluster_id,
            allowed=False,
            reason="proof_required_before_fix_contract",
            proof=cluster.proof,
        )
    return FixContract(
        cluster_id=cluster.cluster_id,
        allowed=True,
        reason="cluster_has_root_cause_proof",
        proof=cluster.proof,
    )


def _parse_signals(text: str) -> list[FailureSignal]:
    blocks = _split_failure_blocks(text)
    return [_parse_block(block) for block in blocks if block.strip()]


def _split_failure_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if _is_failure_header(line) and current:
            blocks.append(current)
            current = [line]
            continue
        current.append(line)
    if current:
        blocks.append(current)
    return ["\n".join(block) for block in blocks if any(_is_failure_header(line) for line in block)]


def _is_failure_header(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("FAILED ") or stripped.startswith("ERROR ")


def _parse_block(block: str) -> FailureSignal:
    nodeid = _extract_nodeid(block)
    file = _extract_file(nodeid, block)
    return FailureSignal(
        nodeid=nodeid,
        file=file,
        module=_module_from_file(file),
        error_text=_extract_error_text(block),
        fixture=_extract_fixture(block),
        missing_field=_extract_missing_field(block),
        runtime_flow_step=_extract_runtime_flow_step(block),
        safety_boundary=_extract_safety_boundary(block),
        candidate_concept=_extract_candidate_concept(block),
        proof=_extract_proof(block),
    )


def _extract_nodeid(block: str) -> str:
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith(("FAILED ", "ERROR ")):
            return stripped.split(maxsplit=1)[1].split()[0]
    return "unknown"


def _extract_file(nodeid: str, block: str) -> str | None:
    if "::" in nodeid:
        return nodeid.split("::", 1)[0]
    match = re.search(r"([A-Za-z0-9_./-]+\.py)", block)
    return match.group(1) if match else None


def _module_from_file(file: str | None) -> str | None:
    if not file:
        return None
    return Path(file).stem


def _extract_error_text(block: str) -> str | None:
    patterns = (
        r"(AssertionError:.*)",
        r"(TypeError:.*)",
        r"(ValueError:.*)",
        r"(KeyError:.*)",
        r"(ImportError:.*)",
        r"(ModuleNotFoundError:.*)",
        r"(E\s+.*)",
    )
    for pattern in patterns:
        match = re.search(pattern, block)
        if match:
            return _normalize_error(match.group(1))
    return None


def _normalize_error(error: str) -> str:
    text = error.strip()
    text = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", text)
    text = re.sub(r"\d+", "N", text)
    return text[:160]


def _extract_fixture(block: str) -> str | None:
    patterns = (
        r"fixture '([^']+)' not found",
        r"fixture \"([^\"]+)\" not found",
        r"FixtureLookupError:.*?([A-Za-z_][A-Za-z0-9_]*)",
        r"fixture(?:=|:|\s)([A-Za-z_][A-Za-z0-9_]*)",
    )
    for pattern in patterns:
        match = re.search(pattern, block, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1)
    return None


def _extract_missing_field(block: str) -> str | None:
    patterns = (
        r"missing[_ ]field(?:=|:|\s)([A-Za-z_][A-Za-z0-9_]*)",
        r"required[_ ]field(?:=|:|\s)([A-Za-z_][A-Za-z0-9_]*)",
        r"KeyError: ['\"]([^'\"]+)['\"]",
    )
    for pattern in patterns:
        match = re.search(pattern, block, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_runtime_flow_step(block: str) -> str | None:
    match = re.search(r"flow[_ ]step(?:=|:|\s)([A-Za-z_][A-Za-z0-9_]*)", block, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _extract_safety_boundary(block: str) -> str | None:
    lowered = block.lower()
    for marker in ("broker", "live_order", "paper_live", "execution_boundary", "dashboard_order"):
        if marker in lowered:
            return marker
    return None


def _extract_candidate_concept(block: str) -> str | None:
    lowered = block.lower()
    for marker in ("candidate", "ranking", "score", "confidence"):
        if marker in lowered:
            return marker
    return None


def _extract_proof(block: str) -> str | None:
    match = re.search(r"proof(?:=|:)([^\n]+)", block, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    if _extract_fixture(block):
        return "shared_fixture_signal"
    if _extract_missing_field(block):
        return "shared_missing_field_signal"
    return None


def _cluster_key(signal: FailureSignal) -> tuple[str, str]:
    for reason, value in (
        ("fixture", signal.fixture),
        ("missing_field", signal.missing_field),
        ("safety_boundary", signal.safety_boundary),
        ("runtime_flow_step", signal.runtime_flow_step),
        ("candidate_concept", signal.candidate_concept),
        ("error_text", signal.error_text),
        ("module", signal.module),
    ):
        if value:
            return reason, value
    return "unknown", signal.nodeid


def _build_cluster(index: int, reason: str, failures: tuple[FailureSignal, ...]) -> FailureCluster:
    proofs = tuple(sorted({failure.proof for failure in failures if failure.proof}))
    confidence = _confidence(reason, failures, proofs)
    return FailureCluster(
        cluster_id=f"ARIADNE-{index:03d}",
        reason=reason,
        confidence=confidence,
        failures=failures,
        proof=proofs,
    )


def _confidence(reason: str, failures: tuple[FailureSignal, ...], proofs: tuple[str, ...]) -> str:
    if reason == "unknown" or not proofs:
        return UNKNOWN
    if len(failures) >= 2 and reason in {"fixture", "missing_field", "safety_boundary", "runtime_flow_step", "candidate_concept", "error_text"}:
        return CONFIRMED
    return LIKELY
