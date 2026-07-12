from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import core.replay_candidate_handoff_entrypoint as replay_handoff


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


class _FakeRank:
    def __init__(self, *, candidate_id: str = "cand-1", strategy_id: str = "strategy-1", executable_candidate: bool = True, rank_reason: str = "ok") -> None:
        self.candidate_id = candidate_id
        self.strategy_id = strategy_id
        self.executable_candidate = executable_candidate
        self.rank_reason = rank_reason

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "strategy_id": self.strategy_id,
            "executable_candidate": self.executable_candidate,
            "rank_reason": self.rank_reason,
        }


def _fake_success_report() -> SimpleNamespace:
    rank = _FakeRank()
    return SimpleNamespace(
        raw_candidate_count=1,
        normalized_candidate_count=1,
        ranked_candidate_count=1,
        executable_rank_count=1,
        rankable_candidates=1,
        suppressed_rank_count=0,
        symbol="NIFTY",
        generated_epoch=1_000.0,
        candidate_pool=SimpleNamespace(candidate_count=1, candidates=()),
        ranking=SimpleNamespace(ranks=(rank,), ranked_report_id="ranked-report-1"),
    )


def test_isolated_output_is_used_by_default(tmp_path, monkeypatch):
    source = tmp_path / "replay.jsonl"
    _write_jsonl(source, [{"event_id": "evt-001", "ts": 1_783_049_403.7, "symbol": "NIFTY26JUL58400CE", "ltp": 855.85, "vol": 10}])
    output_root = tmp_path / ".runtime" / "replay_candidate_handoff"
    prod_handoff = tmp_path / ".runtime" / "runtime_candidate_handoff_latest.json"
    prod_journal = tmp_path / ".runtime" / "candidates" / "candidate_journal.jsonl"
    prod_handoff.parent.mkdir(parents=True, exist_ok=True)
    prod_journal.parent.mkdir(parents=True, exist_ok=True)
    prod_handoff.write_text("sentinel-handoff", encoding="utf-8")
    prod_journal.write_text("sentinel-journal", encoding="utf-8")

    monkeypatch.setattr(replay_handoff, "build_market_snapshot_from_raw_tick", lambda *args, **kwargs: {"snapshot": True})
    monkeypatch.setattr(replay_handoff, "_strategy_context_from_market_symbol", lambda *args, **kwargs: SimpleNamespace(symbol="NIFTY"))
    monkeypatch.setattr(replay_handoff, "build_ranked_opportunity_report", lambda *args, **kwargs: _fake_success_report())

    result = replay_handoff.run_replay_candidate_handoff(source_path=source, output_root=output_root, run_id="run-001")

    assert result.verdict == "FULLY_PROVEN_FROM_REPLAY_INPUT"
    assert result.output_dir == str(output_root / "run-001")
    assert result.handoff_path == str(output_root / "run-001" / "runtime_candidate_handoff_latest.json")
    assert result.journal_path == str(output_root / "run-001" / "candidate_journal.jsonl")
    assert (output_root / "run-001" / "runtime_candidate_handoff_latest.json").exists()
    assert (output_root / "run-001" / "candidate_journal.jsonl").exists()
    assert prod_handoff.read_text(encoding="utf-8") == "sentinel-handoff"
    assert prod_journal.read_text(encoding="utf-8") == "sentinel-journal"
    assert result.replay_only is True
    assert result.broker_api_called is False
    assert result.order_action is False
    assert result.live_feed_used is False
    assert result.append is False
    assert result.output_isolated is True
    assert result.production_artifacts_written is False


def test_missing_replay_input_fails_closed(tmp_path):
    result = replay_handoff.run_replay_candidate_handoff(source_path=tmp_path / "missing.jsonl", output_root=tmp_path / ".runtime")
    assert result.verdict == "BLOCKED_NO_REPLAY_INPUT"
    assert result.blocker == "BLOCKED_NO_REPLAY_INPUT"
    assert result.replay_only is True
    assert result.output_isolated is True


def test_write_production_artifacts_is_forbidden_in_tests(tmp_path):
    source = tmp_path / "replay.jsonl"
    _write_jsonl(source, [{"event_id": "evt-001", "ts": 1_783_049_403.7, "symbol": "NIFTY26JUL58400CE", "ltp": 855.85, "vol": 10}])
    with pytest.raises(RuntimeError, match="write_production_artifacts_forbidden_in_tests"):
        replay_handoff.run_replay_candidate_handoff(
            source_path=source,
            output_root=tmp_path / ".runtime",
            write_production_artifacts=True,
        )


def test_missing_candidate_and_ranking_rejection_are_explicit(tmp_path, monkeypatch):
    source = tmp_path / "replay.jsonl"
    _write_jsonl(source, [{"event_id": "evt-001", "ts": 1_783_049_403.7, "symbol": "NIFTY26JUL58400CE", "ltp": 855.85, "vol": 10}])
    monkeypatch.setattr(replay_handoff, "build_market_snapshot_from_raw_tick", lambda *args, **kwargs: {"snapshot": True})
    monkeypatch.setattr(replay_handoff, "_strategy_context_from_market_symbol", lambda *args, **kwargs: SimpleNamespace(symbol="NIFTY"))

    no_candidate_report = SimpleNamespace(
        raw_candidate_count=1,
        normalized_candidate_count=0,
        ranked_candidate_count=0,
        executable_rank_count=0,
        rankable_candidates=0,
        suppressed_rank_count=0,
        symbol="NIFTY",
        generated_epoch=1_000.0,
        candidate_pool=SimpleNamespace(candidate_count=0, candidates=()),
        ranking=SimpleNamespace(ranks=(), ranked_report_id="ranked-report-2"),
    )
    monkeypatch.setattr(replay_handoff, "build_ranked_opportunity_report", lambda *args, **kwargs: no_candidate_report)
    no_candidate_result = replay_handoff.run_replay_candidate_handoff(source_path=source, output_root=tmp_path / ".runtime", run_id="run-002")
    assert no_candidate_result.verdict == "BLOCKED_NO_CANDIDATE"
    assert any(item["verdict"] == "BLOCKED" and item["stage"] == "candidate" for item in no_candidate_result.stage_evidence)

    rejected_report = SimpleNamespace(
        raw_candidate_count=1,
        normalized_candidate_count=1,
        ranked_candidate_count=1,
        executable_rank_count=0,
        rankable_candidates=1,
        suppressed_rank_count=1,
        symbol="NIFTY",
        generated_epoch=1_000.0,
        candidate_pool=SimpleNamespace(candidate_count=1, candidates=()),
        ranking=SimpleNamespace(ranks=(_FakeRank(executable_candidate=False, rank_reason="feed_hold"),), ranked_report_id="ranked-report-3"),
    )
    monkeypatch.setattr(replay_handoff, "build_ranked_opportunity_report", lambda *args, **kwargs: rejected_report)
    rejected_result = replay_handoff.run_replay_candidate_handoff(source_path=source, output_root=tmp_path / ".runtime", run_id="run-003")
    assert rejected_result.verdict == "BLOCKED_RANKING_REJECTED"
    assert any(item["stage"] == "ranking" and item["verdict"] == "BLOCKED" for item in rejected_result.stage_evidence)


def test_inconsistent_oos_context_fails_closed(tmp_path):
    source = tmp_path / "replay.jsonl"
    _write_jsonl(source, [{"event_id": "evt-001", "ts": 1_783_049_403.7, "symbol": "NIFTY26JUL58400CE", "ltp": 855.85, "vol": 10}])
    result = replay_handoff.run_replay_candidate_handoff(
        source_path=source,
        output_root=tmp_path / ".runtime",
        run_id="run-invalid-oos",
        oos_context={
            "is_oos": True,
            "oos_label": "IS",
            "oos_source": "explicit_replay_run_context",
            "partition_id": "holdout",
        },
    )
    assert result.verdict == "BLOCKED_INVALID_OOS_CONTEXT"
    assert result.blocker == "BLOCKED_INVALID_OOS_CONTEXT"
    assert any(item["stage"] == "oos_context" and item["verdict"] == "BLOCKED" for item in result.stage_evidence)


def test_candidate_and_journal_persistence_use_isolated_output(tmp_path, monkeypatch):
    source = tmp_path / "replay.jsonl"
    _write_jsonl(source, [{"event_id": "evt-001", "ts": 1_783_049_403.7, "symbol": "NIFTY26JUL58400CE", "ltp": 855.85, "vol": 10}])
    monkeypatch.setattr(replay_handoff, "build_market_snapshot_from_raw_tick", lambda *args, **kwargs: {"snapshot": True})
    monkeypatch.setattr(replay_handoff, "_strategy_context_from_market_symbol", lambda *args, **kwargs: SimpleNamespace(symbol="NIFTY"))
    monkeypatch.setattr(replay_handoff, "build_ranked_opportunity_report", lambda *args, **kwargs: _fake_success_report())

    result = replay_handoff.run_replay_candidate_handoff(source_path=source, output_root=tmp_path / ".runtime", run_id="run-004")

    assert result.handoff_path.endswith("run-004/runtime_candidate_handoff_latest.json")
    assert result.journal_path.endswith("run-004/candidate_journal.jsonl")
    assert Path(result.handoff_path).exists()
    assert Path(result.journal_path).exists()
    bundle_root = tmp_path / ".runtime" / "replay_context_bundles"
    assert (bundle_root / "run-004" / "replay_context_bundle_evt-001.json").exists()
    assert (bundle_root / "run-004" / "replay_context_bundle_latest.json").exists()


def test_explicit_oos_context_is_preserved(tmp_path, monkeypatch):
    source = tmp_path / "replay.jsonl"
    _write_jsonl(source, [{"event_id": "evt-001", "ts": 1_783_049_403.7, "symbol": "NIFTY26JUL58400CE", "ltp": 855.85, "vol": 10}])
    monkeypatch.setattr(replay_handoff, "build_market_snapshot_from_raw_tick", lambda *args, **kwargs: {"snapshot": True})
    monkeypatch.setattr(replay_handoff, "_strategy_context_from_market_symbol", lambda *args, **kwargs: SimpleNamespace(symbol="NIFTY"))
    monkeypatch.setattr(replay_handoff, "build_ranked_opportunity_report", lambda *args, **kwargs: _fake_success_report())

    result = replay_handoff.run_replay_candidate_handoff(
        source_path=source,
        output_root=tmp_path / ".runtime",
        run_id="run-oos",
        oos_context={
            "is_oos": True,
            "oos_label": "OOS",
            "oos_source": "explicit_replay_run_context",
            "partition_id": "holdout",
            "split_name": "holdout",
        },
    )

    audit = json.loads(Path(result.audit_json_path).read_text(encoding="utf-8"))
    handoff = json.loads(Path(result.handoff_path).read_text(encoding="utf-8"))
    journal = Path(result.journal_path).read_text(encoding="utf-8").strip().splitlines()[-1]
    journal_row = json.loads(journal)
    bundle = json.loads((tmp_path / ".runtime" / "replay_context_bundles" / "run-oos" / "replay_context_bundle_evt-001.json").read_text(encoding="utf-8"))

    assert result.verdict == "FULLY_PROVEN_FROM_REPLAY_INPUT"
    assert audit["oos_context"]["is_oos"] is True
    assert audit["oos_context"]["oos_label"] == "OOS"
    assert audit["oos_context"]["oos_source"] == "explicit_replay_run_context"
    assert handoff["is_oos"] is True
    assert handoff["oos_label"] == "OOS"
    assert handoff["oos_source"] == "explicit_replay_run_context"
    assert journal_row["is_oos"] is True
    assert journal_row["oos_label"] == "OOS"
    assert journal_row["oos_source"] == "explicit_replay_run_context"
    assert bundle["replay_context"]["is_oos"] is True
    assert bundle["replay_context"]["oos_label"] == "OOS"
