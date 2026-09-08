from __future__ import annotations

import hashlib
import json
from pathlib import Path

from research.macd_futures_participation_regime_v1.canonical_authority import (
    resolve_canonical_authority,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _authority_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    evidence = tmp_path / "evidence"
    repo = tmp_path / "repo"
    evidence.mkdir()
    (repo / "research").mkdir(parents=True)
    implementation = repo / "research" / "canonical_macd.py"
    implementation.write_text("VALUE = 1\n")
    expected = _sha(implementation)
    (evidence / "MACD_CANONICAL_REIMPLEMENTATION_FREEZE.json").write_text(
        json.dumps(
            {
                "canonical_implementation_path": "research/canonical_macd.py",
                "canonical_implementation_sha256": expected,
            }
        )
    )
    (evidence / "MACD_CANONICAL_IMPLEMENTATION_SPEC.json").write_text(
        json.dumps({"strategy_id": "REDDIT_MACD_1H_LONG_ONLY"})
    )
    (evidence / "MACD_CANONICAL_LATENCY_STRESS.json").write_text("{}\n")
    return evidence, repo, implementation


def test_matching_implementation_authority_passes(tmp_path: Path) -> None:
    evidence, repo, _ = _authority_fixture(tmp_path)
    result = resolve_canonical_authority(evidence, repo)
    assert result.status == "PASS"
    assert result.blocker is None
    assert len(result.verified_implementation_candidates) == 1
    assert len(result.latency_artifacts) == 1


def test_mutated_implementation_sha_fails_closed(tmp_path: Path) -> None:
    evidence, repo, implementation = _authority_fixture(tmp_path)
    implementation.write_text("VALUE = 2\n")
    result = resolve_canonical_authority(evidence, repo)
    assert result.status == "BLOCKED"
    assert result.blocker == "DECLARED_IMPLEMENTATION_NOT_PRESENT_OR_SHA_MISMATCH"
    assert result.verified_implementation_candidates == []
