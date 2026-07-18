from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from research.opening_range_retest.replay_contract import build_replay_contract_matrix
from research.opening_range_retest.replay_controls import (
    PROJECTED_SESSION_COLUMNS,
    SessionFileRecord,
    ReplaySourceSelectionError,
    normalize_underlying_symbol,
    read_session_bars,
    resolve_inventory_artifact,
    select_session_files,
)
from research.opening_range_retest.replay_engine import (
    LEDGER_ARTIFACT_FILENAME,
    _canonical_session_key,
    _partition_assignment,
    merge_replay_artifacts,
    replay_session_bars,
    run_replay,
    write_replay_artifacts,
)
from research.opening_range_retest.replay_oracle import evaluate_oracle_direction
from tests.test_opening_range_retest_temporal_fixture_contract import (
    CALL_INVALIDATION_ROWS,
    CALL_VALID_ROWS,
    OPENING_RANGE_ROWS,
    _bars,
)


@pytest.fixture(autouse=True)
def _certifying_git_state(monkeypatch: pytest.MonkeyPatch) -> None:
    from research.opening_range_retest.replay_engine import GitExecutionState

    monkeypatch.setattr(
        "research.opening_range_retest.replay_engine._git_execution_state",
        lambda: GitExecutionState(
            commit_sha="f743620eda4eafccaff43a1ae70a7a7336f839d2",
            worktree_clean=True,
            dirty_path_count=0,
            status_output=(),
            error=None,
        ),
    )


def _write_session_parquet(path: Path, rows: tuple[tuple[int, float, float, float, float], ...], *, symbol: str = "NSE_INDEX|NIFTY 50") -> None:
    bars = _bars(rows)
    frame = pd.DataFrame(
        {
            "timestamp": [row["ts"] for row in bars],
            "symbol": [symbol] * len(bars),
            "open": [row["open"] for row in bars],
            "high": [row["high"] for row in bars],
            "low": [row["low"] for row in bars],
            "close": [row["close"] for row in bars],
            "volume": [row["volume"] or 0.0 for row in bars],
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def _full_session_rows(rows: tuple[tuple[int, float, float, float, float], ...]) -> tuple[tuple[int, float, float, float, float], ...]:
    out = list(rows)
    last = out[-1]
    last_close = float(last[4])
    for offset in range(int(last[0]) + 1, 375):
        out.append((offset, last_close, last_close, last_close, last_close))
    return tuple(out)


def test_contract_matrix_matches_verified_current_behavior() -> None:
    contract = build_replay_contract_matrix()
    assert contract.strategy_id == "opening_range_retest_v1"
    assert contract.temporal_contract_version == "opening_range_retest_temporal_v1"
    assert contract.opening_range_bar_count == 15
    assert contract.breakout_to_retest_max_age == 5
    assert contract.retest_to_continuation_max_age == 3
    assert contract.permitted_source_symbols == ("NIFTY", "BANKNIFTY", "SENSEX")
    assert contract.production_callable.endswith("generate_opening_range_retest_candidates")


def test_replay_session_bars_emits_only_when_candidate_first_becomes_legal() -> None:
    bars = list(_bars(OPENING_RANGE_ROWS + CALL_VALID_ROWS))
    emissions = replay_session_bars(bars, symbol="NIFTY", session_date="2026-07-14")
    assert tuple(item.direction for item in emissions) == ("BUY_CALL",)
    emission = emissions[0]
    assert emission.direction == "BUY_CALL"
    assert emission.proposal_ready_at_iso == "2026-07-14T09:34:00+05:30"
    oracle = evaluate_oracle_direction(bars, direction="BUY_CALL")
    assert getattr(oracle, "proposal_ready_at_iso", None) == emission.proposal_ready_at_iso


def test_future_mutation_stability_holds_for_fixture_session() -> None:
    bars = list(_bars(OPENING_RANGE_ROWS + CALL_VALID_ROWS))
    baseline = replay_session_bars(bars, symbol="NIFTY", session_date="2026-07-14")
    mutated = list(_bars(OPENING_RANGE_ROWS + CALL_VALID_ROWS[:4] + ((19, 22614.0, 23000.0, 21000.0, 22000.0),)))
    replayed = replay_session_bars(mutated, symbol="NIFTY", session_date="2026-07-14")
    assert [item.semantic_payload for item in baseline] == [item.semantic_payload for item in replayed]


def test_invalidated_setup_does_not_revive() -> None:
    bars = list(_bars(OPENING_RANGE_ROWS + CALL_INVALIDATION_ROWS))
    emissions = replay_session_bars(bars, symbol="NIFTY", session_date="2026-07-14")
    assert emissions == ()


def test_read_session_bars_fails_closed_on_missing_bar(tmp_path: Path) -> None:
    path = tmp_path / "underlying" / "NSE_INDEX|NIFTY 50_20260714.parquet"
    rows = _full_session_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS)
    # remove one minute to create a cadence gap
    gapped = rows[:10] + rows[11:]
    _write_session_parquet(path, gapped)
    with pytest.raises(ReplaySourceSelectionError, match="unexpected_session_row_count|non_one_minute_cadence"):
        read_session_bars(path)


def _write_sidecar(path: Path) -> None:
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(f"{sha}  {path.name}\n", encoding="utf-8")


def _inventory_payload(paths: list[Path], root: Path) -> dict[str, object]:
    files: dict[str, object] = {}
    for index, path in enumerate(paths, start=1):
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        logical = str(path.relative_to(root.parent.parent))
        session_date = path.stem.rsplit("_", 1)[-1]
        symbol_value = path.stem.rsplit("_", 1)[0]
        files[f"file-{index}"] = {
            "absolute_path": str(path),
            "logical_path": logical,
            "source_root": str(root),
            "data_role": "UNDERLYING_CANDLES",
            "quality_status": "ACCEPTED",
            "session_status": "FULL_SESSION",
            "sha256": sha,
            "row_count": 375,
            "byte_size": path.stat().st_size,
            "symbol_values": [symbol_value],
            "bar_interval": "1minute",
            "timestamp_min": f"{session_date[:4]}-{session_date[4:6]}-{session_date[6:8]}T09:15:00+05:30",
            "timestamp_max": f"{session_date[:4]}-{session_date[4:6]}-{session_date[6:8]}T15:29:00+05:30",
        }
    return {
        "schema_version": 1,
        "requested_source_roots": [str(root)],
        "source_roots": [str(root)],
        "source_root_authority": [],
        "files": files,
        "families": {},
        "composites": {},
    }


def _write_inventory(path: Path, root: Path, data_file: Path | list[Path]) -> str:
    files = data_file if isinstance(data_file, list) else [data_file]
    payload = _inventory_payload(files, root)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    _write_sidecar(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_resolve_inventory_artifact_uses_repo_relative_canonical_when_provenance_path_is_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docs_dir = tmp_path / "docs" / "agent_reviews"
    root = tmp_path / "runtime" / "upstox_candidate_replay"
    data_path = root / "20260714" / "underlying" / "NSE_INDEX|NIFTY 50_20260714.parquet"
    _write_session_parquet(data_path, _full_session_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS))
    inventory_path = docs_dir / "upstox_corpus_inventory_v2.json"
    docs_dir.mkdir(parents=True, exist_ok=True)
    inventory_sha = _write_inventory(inventory_path, root, data_path)
    manifest = {
        "inventory_path": str(tmp_path / "missing" / "upstox_corpus_inventory_v2.json"),
        "inventory_sha256": inventory_sha,
    }
    monkeypatch.setattr("research.opening_range_retest.replay_controls.PROJECT_ROOT", tmp_path)
    resolution = resolve_inventory_artifact(manifest, project_root=tmp_path)
    assert resolution.original_provenance_path.endswith("upstox_corpus_inventory_v2.json")
    assert resolution.resolved_runtime_path == str(inventory_path.resolve())
    assert resolution.inventory_sha256 == inventory_sha
    assert resolution.sidecar_verified is True


def test_resolve_inventory_artifact_missing_sidecar_fails_closed(tmp_path: Path) -> None:
    inventory_path = tmp_path / "docs" / "agent_reviews" / "upstox_corpus_inventory_v2.json"
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_text(json.dumps({"schema_version": 1, "files": {}}), encoding="utf-8")
    with pytest.raises(ReplaySourceSelectionError, match="inventory_sidecar_missing"):
        resolve_inventory_artifact({}, project_root=tmp_path)


def test_resolve_inventory_artifact_manifest_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    inventory_path = tmp_path / "docs" / "agent_reviews" / "upstox_corpus_inventory_v2.json"
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_text(json.dumps({"schema_version": 1, "files": {}}), encoding="utf-8")
    _write_sidecar(inventory_path)
    with pytest.raises(ReplaySourceSelectionError, match="inventory_manifest_hash_mismatch"):
        resolve_inventory_artifact({"inventory_sha256": "0" * 64}, project_root=tmp_path)


def test_resolve_inventory_artifact_malformed_inventory_fails_closed(tmp_path: Path) -> None:
    inventory_path = tmp_path / "docs" / "agent_reviews" / "upstox_corpus_inventory_v2.json"
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_text("{bad json", encoding="utf-8")
    _write_sidecar(inventory_path)
    with pytest.raises(ReplaySourceSelectionError, match="inventory_sidecar_hash_mismatch|inventory_json_malformed"):
        resolve_inventory_artifact({}, project_root=tmp_path)


def test_resolve_inventory_artifact_unsupported_schema_fails_closed(tmp_path: Path) -> None:
    inventory_path = tmp_path / "docs" / "agent_reviews" / "upstox_corpus_inventory_v2.json"
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_text(json.dumps({"schema_version": 99, "files": {}}), encoding="utf-8")
    _write_sidecar(inventory_path)
    with pytest.raises(ReplaySourceSelectionError, match="inventory_schema_unsupported"):
        resolve_inventory_artifact({}, project_root=tmp_path)


def test_select_session_files_uses_inventory_without_fallback_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "runtime" / "upstox_candidate_replay"
    data_path = root / "20260714" / "underlying" / "NSE_INDEX|NIFTY 50_20260714.parquet"
    _write_session_parquet(data_path, _full_session_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS))
    docs_dir = tmp_path / "docs" / "agent_reviews"
    docs_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = docs_dir / "upstox_corpus_inventory_v2.json"
    inventory_sha = _write_inventory(inventory_path, root, data_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "requested_source_roots": [str(root)],
                "inventory_path": str(tmp_path / "missing_inventory.json"),
                "inventory_sha256": inventory_sha,
                "composite_corpora": [{"strategy_id": "opening_range_retest_v1", "underlying_identity": "NIFTY"}],
                "source_roots": [str(root)],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("research.opening_range_retest.replay_controls.PROJECT_ROOT", tmp_path)

    def _unexpected(*args, **kwargs):
        raise AssertionError("fallback_scan_should_not_run")

    monkeypatch.setattr("research.opening_range_retest.replay_controls._fallback_select_by_scan", _unexpected)
    resolution, selected = select_session_files(manifest_path=manifest_path, strategy_id="opening_range_retest_v1", require_inventory=True)
    assert resolution.sidecar_verified is True
    assert tuple((row.symbol, row.session_date) for row in selected) == (("NIFTY", "2026-07-14"),)


def test_select_session_files_classifies_nifty_bank_as_banknifty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "runtime" / "upstox_candidate_replay"
    data_path = root / "20260714" / "underlying" / "NSE_INDEX|Nifty Bank_20260714.parquet"
    _write_session_parquet(data_path, _full_session_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS), symbol="NSE_INDEX|Nifty Bank")
    docs_dir = tmp_path / "docs" / "agent_reviews"
    docs_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = docs_dir / "upstox_corpus_inventory_v2.json"
    inventory_sha = _write_inventory(inventory_path, root, data_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "requested_source_roots": [str(root)],
                "inventory_path": str(tmp_path / "missing_inventory.json"),
                "inventory_sha256": inventory_sha,
                "composite_corpora": [{"strategy_id": "opening_range_retest_v1", "underlying_identity": "BANKNIFTY"}],
                "source_roots": [str(root)],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("research.opening_range_retest.replay_controls.PROJECT_ROOT", tmp_path)
    _, selected = select_session_files(manifest_path=manifest_path, strategy_id="opening_range_retest_v1", require_inventory=True)
    assert normalize_underlying_symbol("NSE_INDEX|Nifty Bank") == "BANKNIFTY"
    assert tuple((row.symbol, row.session_date) for row in selected) == (("BANKNIFTY", "2026-07-14"),)


def test_select_session_files_result_independent_of_checkout_directory_name(tmp_path: Path) -> None:
    for dirname in ("repo_alpha", "repo_beta"):
        repo_root = tmp_path / dirname
        root = repo_root / "runtime" / "upstox_candidate_replay"
        data_path = root / "20260714" / "underlying" / "NSE_INDEX|NIFTY 50_20260714.parquet"
        _write_session_parquet(data_path, _full_session_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS))
        docs_dir = repo_root / "docs" / "agent_reviews"
        docs_dir.mkdir(parents=True, exist_ok=True)
        inventory_path = docs_dir / "upstox_corpus_inventory_v2.json"
        inventory_sha = _write_inventory(inventory_path, root, data_path)
        manifest = {
            "requested_source_roots": [str(root)],
            "inventory_path": str(repo_root / "stale" / "upstox_corpus_inventory_v2.json"),
            "inventory_sha256": inventory_sha,
            "composite_corpora": [{"strategy_id": "opening_range_retest_v1", "underlying_identity": "NIFTY"}],
            "source_roots": [str(root)],
        }
        manifest_path = repo_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    first_resolution, first_selected = select_session_files(
        manifest_path=tmp_path / "repo_alpha" / "manifest.json",
        strategy_id="opening_range_retest_v1",
        require_inventory=True,
    )
    second_resolution, second_selected = select_session_files(
        manifest_path=tmp_path / "repo_beta" / "manifest.json",
        strategy_id="opening_range_retest_v1",
        require_inventory=True,
    )
    assert (
        first_resolution.resolved_runtime_path,
        second_resolution.resolved_runtime_path,
    ) == (
        str((tmp_path / "repo_alpha" / "docs" / "agent_reviews" / "upstox_corpus_inventory_v2.json").resolve()),
        str((tmp_path / "repo_beta" / "docs" / "agent_reviews" / "upstox_corpus_inventory_v2.json").resolve()),
    )
    assert [row.symbol for row in first_selected] == [row.symbol for row in second_selected]
    assert [row.session_date for row in first_selected] == [row.session_date for row in second_selected]


def test_read_session_bars_projects_required_columns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "underlying" / "NSE_INDEX|NIFTY 50_20260714.parquet"
    _write_session_parquet(path, _full_session_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS))
    captured: dict[str, object] = {}
    real_read_parquet = pd.read_parquet

    def _wrapped(*args, **kwargs):
        captured["columns"] = kwargs.get("columns")
        return real_read_parquet(*args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", _wrapped)
    loaded = read_session_bars(path)
    assert loaded.metrics["projected_columns"] == list(PROJECTED_SESSION_COLUMNS)
    assert captured["columns"] == list(PROJECTED_SESSION_COLUMNS)


def test_run_replay_reads_selected_file_no_more_than_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "runtime" / "upstox_candidate_replay"
    data_path = root / "20260714" / "underlying" / "NSE_INDEX|NIFTY 50_20260714.parquet"
    _write_session_parquet(data_path, _full_session_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS))
    docs_dir = tmp_path / "docs" / "agent_reviews"
    docs_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = docs_dir / "upstox_corpus_inventory_v2.json"
    inventory_sha = _write_inventory(inventory_path, root, data_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "requested_source_roots": [str(root)],
                "inventory_path": str(tmp_path / "missing_inventory.json"),
                "inventory_sha256": inventory_sha,
                "composite_corpora": [{"strategy_id": "opening_range_retest_v1", "underlying_identity": "NIFTY"}],
                "source_roots": [str(root)],
            }
        ),
        encoding="utf-8",
    )
    read_count = 0
    real_read_parquet = pd.read_parquet

    def _wrapped(*args, **kwargs):
        nonlocal read_count
        read_count += 1
        return real_read_parquet(*args, **kwargs)

    monkeypatch.setattr("research.opening_range_retest.replay_controls.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(pd, "read_parquet", _wrapped)
    run_replay(manifest_path=manifest_path, require_inventory=True)
    assert read_count == 1


def test_diagnostic_fallback_cannot_produce_certifying_verdict(tmp_path: Path) -> None:
    root = tmp_path / "runtime" / "upstox_candidate_replay"
    _write_session_parquet(
        root / "20260714" / "underlying" / "NSE_INDEX|NIFTY 50_20260714.parquet",
        _full_session_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS),
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "requested_source_roots": [str(root)],
                "inventory_path": str(tmp_path / "missing_inventory.json"),
                "composite_corpora": [{"strategy_id": "opening_range_retest_v1", "underlying_identity": "NIFTY"}],
                "source_roots": [str(root)],
            }
        ),
        encoding="utf-8",
    )
    run = run_replay(manifest_path=manifest_path, require_inventory=False)
    assert run.summary["diagnostic_mode"] is True
    assert run.summary["phase1_verdict"] == "AUDIT_INVALID"


def test_run_replay_and_write_artifacts_are_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "runtime" / "upstox_candidate_replay"
    data_path = root / "20260714" / "underlying" / "NSE_INDEX|NIFTY 50_20260714.parquet"
    _write_session_parquet(data_path, _full_session_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS))
    docs_dir = tmp_path / "docs" / "agent_reviews"
    docs_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = docs_dir / "upstox_corpus_inventory_v2.json"
    inventory_sha = _write_inventory(inventory_path, root, data_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "requested_source_roots": [str(root)],
                "inventory_path": str(tmp_path / "missing_inventory.json"),
                "inventory_sha256": inventory_sha,
                "composite_corpora": [{"strategy_id": "opening_range_retest_v1", "underlying_identity": "NIFTY"}],
                "source_roots": [str(root)],
            }
        ),
        encoding="utf-8",
    )
    run_a = run_replay(manifest_path=manifest_path, require_inventory=True)
    run_b = run_replay(manifest_path=manifest_path, require_inventory=True)
    assert run_a.summary["candidate_semantic_hash"] == run_b.summary["candidate_semantic_hash"]
    assert run_a.summary["canonical_summary_semantic_hash"] == run_b.summary["canonical_summary_semantic_hash"]
    out_a = tmp_path / "artifacts_a"
    out_b = tmp_path / "artifacts_b"
    write_replay_artifacts(run_a, output_dir=out_a, ledger_path=tmp_path / "ledger_a.json")
    write_replay_artifacts(run_b, output_dir=out_b, ledger_path=tmp_path / "ledger_b.json")
    summary_a = json.loads((out_a / "opening_range_retest_causal_replay_summary_v1.json").read_text())
    summary_b = json.loads((out_b / "opening_range_retest_causal_replay_summary_v1.json").read_text())
    source_manifest_a = json.loads((out_a / "opening_range_retest_causal_replay_source_manifest_v1.json").read_text())
    assert summary_a["candidate_semantic_hash"] == summary_b["candidate_semantic_hash"]
    assert summary_a["canonical_summary_semantic_hash"] == summary_b["canonical_summary_semantic_hash"]
    assert (tmp_path / "ledger_a.json.sha256").exists()
    assert summary_a["execution_identity"]["git_commit_sha"]
    assert isinstance(summary_a["execution_identity"]["worktree_clean"], bool)
    assert summary_a["execution_identity"]["requested_profile_id"] == "opening_range_retest_v1"
    assert summary_a["execution_identity"]["resolved_profile_id"] == "opening_range_breakout_v1"
    assert source_manifest_a["shard_metadata"]["merged_from_shards"] is False
    assert source_manifest_a["shard_metadata"]["merged_shard_indexes"] == [0]
    assert source_manifest_a["shard_metadata"]["selected_record_count_before_sharding"] == (
        summary_a["shard_metadata"]["selected_file_count_before_sharding"]
    )
    assert source_manifest_a["shard_metadata"]["selected_record_count_after_sharding"] == (
        summary_a["shard_metadata"]["selected_file_count_after_sharding"]
    )
    for payload in (
        json.loads((out_a / "opening_range_retest_causal_replay_contract_v1.json").read_text()),
        json.loads((out_a / "opening_range_retest_causal_replay_source_manifest_v1.json").read_text()),
        summary_a,
    ):
        assert payload["mode"] == "RESEARCH_REPLAY_ARTIFACT"
        assert payload["candidate_id"] == "opening_range_retest_causal_replay_phase1"
        assert payload["decision"] == "OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY"
        assert payload["reason"]
        assert payload["timestamp"]
        assert payload["is_order_action"] is False
        assert payload["broker_api_called"] is False
        assert payload["source"]


def test_run_replay_shards_merge_back_to_full_result(tmp_path: Path) -> None:
    root = tmp_path / "runtime" / "upstox_candidate_replay"
    data_path_a = root / "20260714" / "underlying" / "NSE_INDEX|NIFTY 50_20260714.parquet"
    data_path_b = root / "20260715" / "underlying" / "NSE_INDEX|NIFTY 50_20260715.parquet"
    _write_session_parquet(data_path_a, _full_session_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS))
    _write_session_parquet(data_path_b, _full_session_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS))
    docs_dir = tmp_path / "docs" / "agent_reviews"
    docs_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = docs_dir / "upstox_corpus_inventory_v2.json"
    inventory_sha = _write_inventory(inventory_path, root, [data_path_a, data_path_b])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "requested_source_roots": [str(root)],
                "inventory_path": str(tmp_path / "missing_inventory.json"),
                "inventory_sha256": inventory_sha,
                "composite_corpora": [{"strategy_id": "opening_range_retest_v1", "underlying_identity": "NIFTY"}],
                "source_roots": [str(root)],
            }
        ),
        encoding="utf-8",
    )
    full_run = run_replay(manifest_path=manifest_path, require_inventory=True)
    shard_a = run_replay(manifest_path=manifest_path, require_inventory=True, shard_count=2, shard_index=0)
    shard_b = run_replay(manifest_path=manifest_path, require_inventory=True, shard_count=2, shard_index=1)
    shard_dir_a = tmp_path / "shard_a"
    shard_dir_b = tmp_path / "shard_b"
    write_replay_artifacts(shard_a, output_dir=shard_dir_a, ledger_path=shard_dir_a / LEDGER_ARTIFACT_FILENAME)
    write_replay_artifacts(shard_b, output_dir=shard_dir_b, ledger_path=shard_dir_b / LEDGER_ARTIFACT_FILENAME)
    merged = merge_replay_artifacts(shard_artifact_dirs=[shard_dir_a, shard_dir_b])
    assert merged.summary["phase1_verdict"] == "OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY"
    assert merged.summary["candidate_semantic_hash"] == full_run.summary["candidate_semantic_hash"]
    assert merged.summary["canonical_summary_semantic_hash"] == full_run.summary["canonical_summary_semantic_hash"]
    assert merged.summary["shard_metadata"]["merged_from_shards"] is True
    assert merged.summary["selected_file_count"] == full_run.summary["selected_file_count"]
    assert merged.source_manifest["shard_metadata"]["partition_rule"] == "sha256(canonical_session_key) mod shard_count"


def test_run_replay_rejects_invalid_shard_index(tmp_path: Path) -> None:
    root = tmp_path / "runtime" / "upstox_candidate_replay"
    data_path = root / "20260714" / "underlying" / "NSE_INDEX|NIFTY 50_20260714.parquet"
    _write_session_parquet(data_path, _full_session_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS))
    docs_dir = tmp_path / "docs" / "agent_reviews"
    docs_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = docs_dir / "upstox_corpus_inventory_v2.json"
    inventory_sha = _write_inventory(inventory_path, root, data_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "requested_source_roots": [str(root)],
                "inventory_path": str(tmp_path / "missing_inventory.json"),
                "inventory_sha256": inventory_sha,
                "composite_corpora": [{"strategy_id": "opening_range_retest_v1", "underlying_identity": "NIFTY"}],
                "source_roots": [str(root)],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="shard_index_out_of_range"):
        run_replay(manifest_path=manifest_path, require_inventory=True, shard_count=2, shard_index=2)


def test_partition_assignment_is_stable_and_checkout_independent() -> None:
    alpha = SessionFileRecord(
        absolute_path="/tmp/repo-alpha/runtime/upstox_candidate_replay/20260714/underlying/NSE_INDEX|NIFTY 50_20260714.parquet",
        logical_path="runtime/upstox_candidate_replay/20260714/underlying/NSE_INDEX|NIFTY 50_20260714.parquet",
        symbol="NIFTY",
        session_date="2026-07-14",
        source_root="/tmp/repo-alpha/runtime/upstox_candidate_replay",
        sha256="a" * 64,
        row_count=375,
        byte_size=1024,
        projected_columns=tuple(PROJECTED_SESSION_COLUMNS),
        selected_via="inventory_verified_repo_relative",
    )
    beta = SessionFileRecord(
        absolute_path="/tmp/repo-beta/runtime/upstox_candidate_replay/20260714/underlying/NSE_INDEX|NIFTY 50_20260714.parquet",
        logical_path="runtime/upstox_candidate_replay/20260714/underlying/NSE_INDEX|NIFTY 50_20260714.parquet",
        symbol="NIFTY",
        session_date="2026-07-14",
        source_root="/tmp/repo-beta/runtime/upstox_candidate_replay",
        sha256="a" * 64,
        row_count=375,
        byte_size=1024,
        projected_columns=tuple(PROJECTED_SESSION_COLUMNS),
        selected_via="inventory_verified_repo_relative",
    )
    key_alpha = _canonical_session_key(alpha)
    key_beta = _canonical_session_key(beta)
    assert key_alpha == key_beta
    assert _partition_assignment(alpha, shard_count=12) == _partition_assignment(beta, shard_count=12)


def test_partition_assignment_is_file_order_independent_and_complete(tmp_path: Path) -> None:
    root = tmp_path / "runtime" / "upstox_candidate_replay"
    data_paths = [
        root / "20260714" / "underlying" / "NSE_INDEX|NIFTY 50_20260714.parquet",
        root / "20260715" / "underlying" / "NSE_INDEX|NIFTY 50_20260715.parquet",
        root / "20260716" / "underlying" / "NSE_INDEX|NIFTY 50_20260716.parquet",
    ]
    for path in data_paths:
        _write_session_parquet(path, _full_session_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS))
    docs_dir = tmp_path / "docs" / "agent_reviews"
    docs_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = docs_dir / "upstox_corpus_inventory_v2.json"
    inventory_sha = _write_inventory(inventory_path, root, data_paths)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "requested_source_roots": [str(root)],
                "inventory_path": str(tmp_path / "missing_inventory.json"),
                "inventory_sha256": inventory_sha,
                "composite_corpora": [{"strategy_id": "opening_range_retest_v1", "underlying_identity": "NIFTY"}],
                "source_roots": [str(root)],
            }
        ),
        encoding="utf-8",
    )
    resolution, selected = select_session_files(manifest_path=manifest_path, strategy_id="opening_range_retest_v1", require_inventory=True)
    assert resolution.sidecar_verified is True
    ordered = list(selected)
    reversed_selected = list(reversed(selected))
    expected_keys = {record.logical_path for record in selected}
    shard_union: set[str] = set()
    for shard_index in range(3):
        from_ordered = {
            record.logical_path for record in ordered if _partition_assignment(record, shard_count=3) == shard_index
        }
        from_reversed = {
            record.logical_path for record in reversed_selected if _partition_assignment(record, shard_count=3) == shard_index
        }
        assert from_ordered == from_reversed
        assert shard_union.isdisjoint(from_ordered)
        shard_union.update(from_ordered)
    assert shard_union == expected_keys


def test_different_shard_counts_reconstruct_identical_full_semantics(tmp_path: Path) -> None:
    root = tmp_path / "runtime" / "upstox_candidate_replay"
    data_paths = [
        root / "20260714" / "underlying" / "NSE_INDEX|NIFTY 50_20260714.parquet",
        root / "20260715" / "underlying" / "NSE_INDEX|NIFTY 50_20260715.parquet",
        root / "20260716" / "underlying" / "NSE_INDEX|NIFTY 50_20260716.parquet",
    ]
    for path in data_paths:
        _write_session_parquet(path, _full_session_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS))
    docs_dir = tmp_path / "docs" / "agent_reviews"
    docs_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = docs_dir / "upstox_corpus_inventory_v2.json"
    inventory_sha = _write_inventory(inventory_path, root, data_paths)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "requested_source_roots": [str(root)],
                "inventory_path": str(tmp_path / "missing_inventory.json"),
                "inventory_sha256": inventory_sha,
                "composite_corpora": [{"strategy_id": "opening_range_retest_v1", "underlying_identity": "NIFTY"}],
                "source_roots": [str(root)],
            }
        ),
        encoding="utf-8",
    )
    full_run = run_replay(manifest_path=manifest_path, require_inventory=True)
    merged_hashes: set[tuple[str, str]] = set()
    for shard_count in (2, 3):
        shard_dirs: list[Path] = []
        for shard_index in range(shard_count):
            shard = run_replay(manifest_path=manifest_path, require_inventory=True, shard_count=shard_count, shard_index=shard_index)
            shard_dir = tmp_path / f"shards-{shard_count}" / f"{shard_index}"
            write_replay_artifacts(shard, output_dir=shard_dir, ledger_path=shard_dir / LEDGER_ARTIFACT_FILENAME)
            shard_dirs.append(shard_dir)
        merged = merge_replay_artifacts(shard_artifact_dirs=shard_dirs)
        merged_hashes.add((merged.summary["candidate_semantic_hash"], merged.summary["canonical_summary_semantic_hash"]))
        assert merged.summary["candidate_semantic_hash"] == full_run.summary["candidate_semantic_hash"]
        assert merged.summary["canonical_summary_semantic_hash"] == full_run.summary["canonical_summary_semantic_hash"]
    assert merged_hashes == {
        (
            full_run.summary["candidate_semantic_hash"],
            full_run.summary["canonical_summary_semantic_hash"],
        )
    }
