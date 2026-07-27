from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research.option_e2e_recertification_v4.local_unresolved_source_audit_v1.build_evidence import (
    OutputDirectoryInsideDeclaredRootError,
    OutputDirectoryNotEmptyError,
    build,
)
from research.option_e2e_recertification_v4.local_unresolved_source_audit_v1.oracle import (
    oracle_root_facts,
    oracle_trace_facts,
    reconcile_primary_oracle,
)
from research.option_e2e_recertification_v4.local_unresolved_source_audit_v1.root_scan import (
    InvalidRootSpecError,
    OverlappingResolvedRootError,
    RootSpec,
    UnsupportedFilesystemEntryError,
    scan_declared_roots,
)
from research.option_e2e_recertification_v4.local_unresolved_source_audit_v1.trace_audit import (
    OutcomeBearingFieldError,
    TraceFormatError,
    audit_execution_entry_trace,
)


def _record(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "ts_epoch": 1785000000.0,
        "timestamp": "2026-07-25T18:00:00+00:00",
        "module": "core.trade_builder",
        "stage": "entry_resolution",
        "trade_id": "secret-trade-id",
        "symbol": "NIFTY",
        "strategy": "opening_range_retest_v1",
        "execution_allowed": False,
        "tradable": False,
    }
    row.update(overrides)
    return row


def _write_trace(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_trace_audit_streams_metadata_without_publishing_record_values(
    tmp_path: Path,
) -> None:
    trace = tmp_path / "execution_entry_trace.jsonl"
    _write_trace(
        trace,
        [
            _record(),
            _record(
                timestamp="2026-07-25T18:01:00+00:00",
                module="core.orchestrator",
                stage="candidate_emit",
                trade_id="another-secret",
            ),
        ],
    )

    result = audit_execution_entry_trace(trace)
    serialized = json.dumps(result, sort_keys=True)

    assert result["record_count"] == 2
    assert result["source_disposition"] == "EXECUTION_TRACE_OBSERVATIONAL_ONLY"
    assert result["canonical_signal_source_count"] == 0
    assert result["record_values_published"] is False
    assert "secret-trade-id" not in serialized
    assert "another-secret" not in serialized


def test_trace_audit_rejects_outcome_or_pnl_fields(tmp_path: Path) -> None:
    trace = tmp_path / "execution_entry_trace.jsonl"
    _write_trace(trace, [_record(extra={"realized_pnl": 100})])

    with pytest.raises(OutcomeBearingFieldError):
        audit_execution_entry_trace(trace)


def test_trace_audit_rejects_malformed_jsonl(tmp_path: Path) -> None:
    trace = tmp_path / "execution_entry_trace.jsonl"
    trace.write_text('{"timestamp":\n', encoding="utf-8")

    with pytest.raises(TraceFormatError):
        audit_execution_entry_trace(trace)


def test_trace_audit_rejects_oversized_line(tmp_path: Path) -> None:
    trace = tmp_path / "execution_entry_trace.jsonl"
    _write_trace(trace, [_record(extra={"blob": "x" * 200})])

    with pytest.raises(TraceFormatError):
        audit_execution_entry_trace(trace, max_line_bytes=50)


def test_root_scan_is_unlimited_hashes_candidates_and_groups_duplicates(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "notes.txt").write_text("not a source candidate", encoding="utf-8")
    (first / "signal_ledger.json").write_text('{"rows":[]}', encoding="utf-8")
    (second / "copy_signal_ledger.json").write_text('{"rows":[]}', encoding="utf-8")
    (second / "market_data.parquet").write_bytes(b"PAR1test")

    result = scan_declared_roots(
        [RootSpec("ROOT_A", first), RootSpec("ROOT_B", second)],
        expected_root_count=2,
    )
    serialized = json.dumps(result, sort_keys=True)

    assert result["candidate_limit"] is None
    assert result["scan_complete"] is True
    assert result["total_file_count"] == 4
    assert result["source_candidate_count"] == 3
    assert result["denied_outcome_or_pnl_candidate_count"] == 0
    assert result["exact_duplicate_group_count"] == 1
    assert str(first.resolve()) not in serialized
    assert str(second.resolve()) not in serialized


def test_root_scan_keeps_outcome_candidate_metadata_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    denied = root / "signal_realized_pnl.json"
    denied.write_text('{"realized_pnl":100}', encoding="utf-8")
    original_open = Path.open

    def guarded_open(self: Path, *args: object, **kwargs: object):
        if self == denied:
            raise AssertionError("outcome-bearing candidate content was opened")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    result = scan_declared_roots(
        [RootSpec("ROOT_A", root)], expected_root_count=1
    )

    candidate = result["source_candidates"][0]
    assert candidate["denied_by_policy"] is True
    assert candidate["content_opened"] is False
    assert candidate["sha256"] is None
    assert result["denied_outcome_or_pnl_candidate_count"] == 1
    assert result["outcomes_read"] is False
    assert result["pnl_read"] is False
    assert result["holdout_outcomes_read"] is False


def test_root_scan_excludes_virtual_environment_tree_and_its_symlinks(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    environment = root / ".venv"
    environment.mkdir()
    target = environment / "python-real"
    target.write_text("binary", encoding="utf-8")
    link = environment / "python"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")
    (root / "candidate_manifest.json").write_text("{}", encoding="utf-8")

    result = scan_declared_roots(
        [RootSpec("ROOT_A", root)], expected_root_count=1
    )

    assert result["excluded_directory_count"] == 1
    assert result["total_file_count"] == 1
    assert result["source_candidate_count"] == 1
    assert result["root_records"][0]["excluded_directory_count"] == 1


def test_root_scan_fails_closed_on_in_scope_symlink(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = root / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = root / "linked.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")

    with pytest.raises(UnsupportedFilesystemEntryError):
        scan_declared_roots([RootSpec("ROOT_A", root)], expected_root_count=1)


def test_root_scan_requires_exact_declared_root_count(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(InvalidRootSpecError):
        scan_declared_roots([RootSpec("ROOT_A", root)], expected_root_count=27)


def test_root_scan_rejects_nested_declared_roots(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)

    with pytest.raises(OverlappingResolvedRootError):
        scan_declared_roots(
            [RootSpec("ROOT_A", parent), RootSpec("ROOT_B", child)],
            expected_root_count=2,
        )


def test_primary_and_independent_oracle_agree(tmp_path: Path) -> None:
    trace = tmp_path / "execution_entry_trace.jsonl"
    _write_trace(trace, [_record()])
    root = tmp_path / "root"
    root.mkdir()
    (root / "candidate_manifest.json").write_text("{}", encoding="utf-8")
    (root / "signal_holdout_result.json").write_text(
        '{"holdout_result":"redacted"}', encoding="utf-8"
    )
    excluded = root / ".pytest_cache"
    excluded.mkdir()
    (excluded / "signal_ledger.json").write_text("{}", encoding="utf-8")
    specs = [RootSpec("ROOT_A", root)]

    trace_primary = audit_execution_entry_trace(trace)
    root_primary = scan_declared_roots(specs, expected_root_count=1)
    trace_oracle = oracle_trace_facts(trace)
    root_oracle = oracle_root_facts(specs, expected_root_count=1)
    agreement = reconcile_primary_oracle(
        trace_primary, root_primary, trace_oracle, root_oracle
    )

    assert agreement["status"] == "AGREEMENT"
    assert all(agreement["checks"].values())
    assert root_primary["denied_outcome_or_pnl_candidate_count"] == 1
    assert root_oracle["denied_outcome_or_pnl_candidate_count"] == 1
    assert root_primary["excluded_directory_count"] == 1
    assert root_oracle["excluded_directory_count"] == 1


def test_build_rejects_output_inside_declared_root(tmp_path: Path) -> None:
    trace = tmp_path / "execution_entry_trace.jsonl"
    _write_trace(trace, [_record()])
    root = tmp_path / "root"
    root.mkdir()
    output = root / "audit-output"

    with pytest.raises(OutputDirectoryInsideDeclaredRootError):
        build(
            trace_path=trace,
            root_specs=[RootSpec("ROOT_A", root)],
            output_dir=output,
            expected_root_count=1,
        )

    assert not output.exists()


def test_build_rejects_non_empty_output_directory(tmp_path: Path) -> None:
    trace = tmp_path / "execution_entry_trace.jsonl"
    _write_trace(trace, [_record()])
    root = tmp_path / "root"
    root.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    stale = output / "stale.json"
    stale.write_text("{}", encoding="utf-8")

    with pytest.raises(OutputDirectoryNotEmptyError):
        build(
            trace_path=trace,
            root_specs=[RootSpec("ROOT_A", root)],
            output_dir=output,
            expected_root_count=1,
        )

    assert stale.read_text(encoding="utf-8") == "{}"
    assert sorted(path.name for path in output.iterdir()) == ["stale.json"]


def test_build_is_byte_deterministic_and_hash_bound(tmp_path: Path) -> None:
    trace = tmp_path / "execution_entry_trace.jsonl"
    _write_trace(trace, [_record()])
    root = tmp_path / "root"
    root.mkdir()
    (root / "candidate_manifest.json").write_text("{}", encoding="utf-8")
    specs = [RootSpec("ROOT_A", root)]
    first = tmp_path / "first"
    second = tmp_path / "second"

    summary_a = build(
        trace_path=trace,
        root_specs=specs,
        output_dir=first,
        expected_root_count=1,
    )
    summary_b = build(
        trace_path=trace,
        root_specs=specs,
        output_dir=second,
        expected_root_count=1,
    )

    assert summary_a == summary_b
    assert sorted(path.name for path in first.iterdir()) == sorted(
        path.name for path in second.iterdir()
    )
    for path in first.iterdir():
        assert path.read_bytes() == (second / path.name).read_bytes()
    manifest = json.loads((first / "external_evidence_manifest.json").read_text())
    for name, expected in manifest["artifacts"].items():
        actual = hashlib.sha256((first / name).read_bytes()).hexdigest()
        assert actual == expected


def test_build_never_grants_canonical_or_execution_authority(tmp_path: Path) -> None:
    trace = tmp_path / "execution_entry_trace.jsonl"
    _write_trace(trace, [_record()])
    root = tmp_path / "root"
    root.mkdir()
    output = tmp_path / "output"

    summary = build(
        trace_path=trace,
        root_specs=[RootSpec("ROOT_A", root)],
        output_dir=output,
        expected_root_count=1,
    )

    assert summary["canonical_signal_source_count"] == 0
    assert summary["canonical_dataset_source_count"] == 0
    assert summary["allowed_for_live_execution"] is False
    assert summary["replacement_signal_ledger_required"] is True
    assert summary["outcomes_read"] is False
    assert summary["pnl_read"] is False
