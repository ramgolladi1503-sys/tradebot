from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from tools.repo_forensics.config_loader import ForensicsConfig


PROVEN = "PROVEN"
PARTIALLY_PROVEN = "PARTIALLY_PROVEN"
THEORETICAL = "THEORETICAL"
MOCKED = "MOCKED"
UNPROVEN = "UNPROVEN"


@dataclass(frozen=True)
class ProductCapabilityStatus:
    capability: str
    status: str
    proof_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    evidence_files: list[str] = field(default_factory=list)
    risk: str = ""


@dataclass(frozen=True)
class ProductRealityReport:
    capabilities: list[ProductCapabilityStatus] = field(default_factory=list)

    @property
    def proven(self) -> list[ProductCapabilityStatus]:
        return [item for item in self.capabilities if item.status == PROVEN]

    @property
    def partially_proven(self) -> list[ProductCapabilityStatus]:
        return [item for item in self.capabilities if item.status == PARTIALLY_PROVEN]

    @property
    def theoretical(self) -> list[ProductCapabilityStatus]:
        return [item for item in self.capabilities if item.status == THEORETICAL]

    @property
    def mocked(self) -> list[ProductCapabilityStatus]:
        return [item for item in self.capabilities if item.status == MOCKED]

    @property
    def unproven(self) -> list[ProductCapabilityStatus]:
        return [item for item in self.capabilities if item.status == UNPROVEN]


def audit_product_reality(repo_root: str | Path, config: ForensicsConfig) -> ProductRealityReport:
    root = Path(repo_root).resolve()
    capabilities = _configured_capabilities(config)
    if not capabilities:
        capabilities = _default_tradebot_capabilities()
    files = list(_iter_relevant_files(root, config))
    statuses = [_classify_capability(root, files, capability) for capability in capabilities]
    return ProductRealityReport(capabilities=statuses)


def _classify_capability(repo_root: Path, files: list[Path], capability: str) -> ProductCapabilityStatus:
    tokens = _tokens(capability)
    proof_files: list[str] = []
    test_files: list[str] = []
    evidence_files: list[str] = []
    mock_hits = 0
    theory_hits = 0

    for path in files:
        rel = path.relative_to(repo_root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lowered = text.lower()
        rel_lower = rel.lower()
        if not _matches(tokens, lowered, rel_lower):
            continue
        if _is_test_path(rel):
            test_files.append(rel)
        elif _is_evidence_path(rel):
            evidence_files.append(rel)
        else:
            proof_files.append(rel)
        if any(marker in lowered or marker in rel_lower for marker in ["mock", "fake", "stub", "dummy"]):
            mock_hits += 1
        if any(marker in lowered for marker in ["todo", "not implemented", "placeholder", "future", "theoretical"]):
            theory_hits += 1

    proof_files = sorted(set(proof_files))[:8]
    test_files = sorted(set(test_files))[:8]
    evidence_files = sorted(set(evidence_files))[:8]

    if proof_files and test_files and evidence_files and mock_hits == 0 and theory_hits == 0:
        status = PROVEN
        risk = "source, tests, and evidence exist without obvious mock/theory markers"
    elif proof_files and (test_files or evidence_files):
        status = PARTIALLY_PROVEN
        risk = "source exists but proof is incomplete or contains weak/mock/theory markers"
    elif test_files and not proof_files:
        status = MOCKED if mock_hits else THEORETICAL
        risk = "tests mention capability but production source proof is missing"
    elif evidence_files and not proof_files:
        status = THEORETICAL
        risk = "evidence mentions capability but production source proof is missing"
    else:
        status = UNPROVEN
        risk = "no strong static source/test/evidence signal found"

    if mock_hits and status in {PROVEN, PARTIALLY_PROVEN, THEORETICAL}:
        status = MOCKED if not proof_files else PARTIALLY_PROVEN
        risk = f"mock/fake/stub markers found count={mock_hits}"
    if theory_hits and status == PROVEN:
        status = PARTIALLY_PROVEN
        risk = f"placeholder/future/theoretical markers found count={theory_hits}"

    return ProductCapabilityStatus(
        capability=capability,
        status=status,
        proof_files=proof_files,
        test_files=test_files,
        evidence_files=evidence_files,
        risk=risk,
    )


def _configured_capabilities(config: ForensicsConfig) -> list[str]:
    params = config.data.get("agent_parameters", {})
    if not isinstance(params, dict):
        return []
    reality = params.get("product_reality", {})
    if not isinstance(reality, dict):
        return []
    capabilities = reality.get("capabilities", [])
    if not isinstance(capabilities, list):
        return []
    return [str(item).strip() for item in capabilities if str(item).strip()]


def _default_tradebot_capabilities() -> list[str]:
    return [
        "market data feed freshness",
        "option chain token resolution",
        "candidate generation",
        "candidate scoring ranking",
        "no trade safety suppression",
        "risk management rejection",
        "paper trading evidence",
        "live broker execution boundary",
        "replay backtest validation",
        "dashboard control tower visibility",
    ]


def _iter_relevant_files(repo_root: Path, config: ForensicsConfig) -> Iterable[Path]:
    suffixes = {".py", ".md", ".txt", ".json", ".jsonl", ".yaml", ".yml"}
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        if _should_skip(path, repo_root, config):
            continue
        yield path


def _matches(tokens: set[str], text: str, path: str) -> bool:
    if not tokens:
        return False
    combined = f"{path}\n{text}"
    hits = sum(1 for token in tokens if token in combined)
    return hits >= min(2, len(tokens))


def _tokens(value: str) -> set[str]:
    stop = {"the", "and", "or", "for", "with", "to", "of", "a", "an"}
    return {part for part in value.lower().replace("/", " ").replace("-", " ").replace("_", " ").split() if len(part) > 2 and part not in stop}


def _is_test_path(path: str) -> bool:
    parts = path.split("/")
    return bool(parts and parts[0] in {"tests", "testing"}) or Path(path).name.startswith("test_")


def _is_evidence_path(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in ["docs/", "report", "evidence", "runtime/", "logs/"])


def _should_skip(path: Path, repo_root: Path, config: ForensicsConfig) -> bool:
    rel = path.relative_to(repo_root)
    if any(part in config.excluded_directories for part in rel.parts):
        return True
    if any(part in {".git", ".venv", "venv", "__pycache__"} for part in rel.parts):
        return True
    return False
