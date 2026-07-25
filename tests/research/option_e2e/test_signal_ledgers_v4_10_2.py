from __future__ import annotations

import hashlib
import json
from pathlib import Path

from research.option_e2e_recertification_v4.signal_ledgers_v4_10_2 import (
    generate_source_evidence as generator_module,
)
from research.option_e2e_recertification_v4.signal_ledgers_v4_10_2.determinism import (
    compare_deterministic_outputs,
)
from research.option_e2e_recertification_v4.signal_ledgers_v4_10_2.ledger_builder import (
    build_signal_ledgers,
)
from research.option_e2e_recertification_v4.signal_ledgers_v4_10_2.ledger_oracle import (
    certify_ledger,
)
from research.option_e2e_recertification_v4.signal_ledgers_v4_10_2.source_search_manifest import (
    SOURCE_INCOMPLETE,
    SOURCE_RESOLVED,
    build_source_search_manifest,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v4_10_2_is_read_only_and_reports_search_incomplete() -> None:
    repo = Path(".")
    tracked_evidence = [
        repo / "research" / "option_e2e_recertification_v4" / "v4_10_2_source_search_manifest.json",
        repo / "research" / "option_e2e_recertification_v4" / "v4_10_2_development_boundary.json",
        repo / "research" / "option_e2e_recertification_v4" / "v4_10_2_holdout_boundary.json",
    ]
    before = {str(path): _sha256(path) for path in tracked_evidence if path.exists()}

    records, summary, detail = build_signal_ledgers(repo)

    after = {str(path): _sha256(path) for path in tracked_evidence if path.exists()}
    assert before == after
    assert records == []
    assert summary["source_status"] == SOURCE_INCOMPLETE
    assert summary["execution_status"] == "VWAP_EXECUTION_NOT_RUN_NO_ACCEPTED_SOURCE"
    assert summary["oracle_verdict"] == "SIGNAL_LEDGER_CERTIFICATION_DISABLED"
    assert detail["contract"]["status"] == "NOT_CREATED_NO_ACCEPTED_SOURCE"
    assert detail["split"]["status"] == "NOT_CREATED_NO_ACCEPTED_DATASET"
    assert detail["execution"]["execution_allowed"] is False
    assert detail["execution"]["broker_api_called"] is False
    assert detail["execution"]["is_order_action"] is False
    assert detail["reconciliation"]["status"] == "SOURCE_RECONCILIATION_INCOMPLETE"


def test_v4_10_2_default_manifest_requires_explicit_local_evidence_generation() -> None:
    manifest = build_source_search_manifest(Path("."))

    assert manifest["conclusion"] == SOURCE_INCOMPLETE
    assert manifest["reason_codes"] == ["SOURCE_EVIDENCE_NOT_GENERATED"]
    assert manifest["candidate_count"] == 0
    assert manifest["accepted_candidate_count"] == 0
    assert manifest["unresolved_candidate_count"] == 0
    assert manifest["semantic_sha256"]
    assert any(root["root_id"] == "CURRENT_WORKTREE" for root in manifest["root_inventory"])


def test_v4_10_2_oracle_rejects_arbitrary_nonempty_records() -> None:
    records = [{"strategy_or_hypothesis_id": "VWAP_RECLAIM", "signal_id": "fake"}]

    result = certify_ledger(records, source_manifest={"conclusion": "SIGNAL_SOURCE_RESOLVED"})

    assert result["verdict"] == "SIGNAL_LEDGER_CERTIFICATION_DISABLED"
    assert result["failures"] == ["INDEPENDENT_ORACLE_EVIDENCE_REQUIRED"]


def test_v4_10_2_semantic_determinism_ignores_diagnostic_paths() -> None:
    first = {
        "conclusion": SOURCE_INCOMPLETE,
        "candidate_count": 0,
        "diagnostics": {"root_paths": {"CURRENT_WORKTREE": "/tmp/one"}},
    }
    second = {
        "conclusion": SOURCE_INCOMPLETE,
        "candidate_count": 0,
        "diagnostics": {"root_paths": {"CURRENT_WORKTREE": "/tmp/two"}},
    }

    comparison = compare_deterministic_outputs(first, second)

    assert comparison["match"] is True
    assert comparison["first_semantic_sha256"] == comparison["second_semantic_sha256"]


def test_v4_10_2_generator_materializes_streaming_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    data_root = tmp_path / "data"
    data_root.mkdir()
    dataset = data_root / "NIFTY_F1.csv"
    dataset.write_text(
        "timestamp,open,high,low,close,volume,symbol\n"
        "2024-01-01T09:15:00+05:30,100,101,99,100.5,10,NIFTY_F1\n",
        encoding="utf-8",
    )
    output = tmp_path / "evidence"

    monkeypatch.setattr(
        generator_module,
        "discover_root_inventory",
        lambda _repo: (
            [
                {
                    "root_id": "TRADEBOT_DATA",
                    "root_class": "EXTERNAL_ROOT",
                    "available": True,
                    "is_directory": True,
                }
            ],
            {
                "root_paths": {"TRADEBOT_DATA": str(data_root)},
                "worktree_command": {"exit_code": 0, "timed_out": False, "stdout_lines": []},
            },
        ),
    )
    monkeypatch.setattr(
        generator_module,
        "build_git_search_manifest",
        lambda _repo: [
            {
                "command": ["git", "log", "--all", "-S", "NIFTY_F1", "--oneline"],
                "exit_code": 0,
                "timed_out": False,
                "stdout_lines": ["abc123 dataset"],
                "stderr": "",
            }
        ],
    )

    summary = generator_module.generate(
        repo,
        output,
        max_candidates_per_root=10,
        max_seconds_per_root=10,
        max_hash_bytes=10 * 1024 * 1024,
    )

    assert summary["conclusion"] == SOURCE_RESOLVED
    assert summary["accepted_candidate_count"] == 1
    assert (output / "run_status.json").exists()
    assert (output / "root_inventory.json").exists()
    assert (output / "git_search_manifest.json").exists()
    assert (output / "candidate_inventory.jsonl").exists()
    assert (output / "source_search_manifest.json").exists()
    assert (output / "source_search_summary.json").exists()
    run_status = json.loads((output / "run_status.json").read_text(encoding="utf-8"))
    assert run_status["status"] == "COMPLETE"
