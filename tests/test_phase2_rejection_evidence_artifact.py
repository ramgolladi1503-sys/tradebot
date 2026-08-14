from __future__ import annotations

import json
import os

import pytest

from config import config as cfg
from core.engine_phase2_adapter import build_candidates_phase2
from core.runtime_phase2_rejection_evidence import build_phase2_rejection_evidence_payload, write_phase2_rejection_evidence_latest


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_valid_runtime_artifact(path):
    from tests.fixtures.canonical_feed_factory import make_valid_canonical_feed_pair

    _, runtime_path = make_valid_canonical_feed_pair(path.parent)
    if runtime_path != path:
        path.write_text(runtime_path.read_text(encoding="utf-8"), encoding="utf-8")


@pytest.fixture()
def _runtime_dirs(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = tmp_path / "logs"
    runtime_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(logs_root))
    monkeypatch.setenv("REPO_LOG_DIR", str(logs_root))
    return runtime_root, logs_root


def test_phase2_rejection_evidence_counts_missing_quote_age(_runtime_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    runtime_root, logs_root = _runtime_dirs

    payload = build_phase2_rejection_evidence_payload(
        phase2_state=None,
        raw_candidates=[
            {
                "trade_id": "T1",
                "symbol": "NIFTY",
                "instrument": "OPT",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "quote_age_sec": None,
                "spread_pct": 0.002,
                "liquidity_score": 1.0,
                "quote_source": "option_chain_live",
            }
        ],
        ranked_candidates=[],
        drop_reason_counts={"missing_live_timing_context": 1},
    )
    assert payload["phase2_input_count"] == 1
    assert payload["phase2_output_count"] == 0
    assert payload["missing_quote_age_count"] == 1


def test_phase2_rejection_evidence_counts_missing_spread(_runtime_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    _runtime_dirs

    payload = build_phase2_rejection_evidence_payload(
        phase2_state=None,
        raw_candidates=[
            {
                "trade_id": "T2",
                "symbol": "NIFTY",
                "instrument": "OPT",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "quote_age_sec": 1.0,
                "spread_pct": None,
                "liquidity_score": 1.0,
                "quote_source": "option_chain_live",
            }
        ],
        ranked_candidates=[],
        drop_reason_counts={"missing_spread_context": 1},
    )
    assert payload["phase2_input_count"] == 1
    assert payload["phase2_output_count"] == 0
    assert payload["missing_spread_count"] == 1


def test_phase2_rejection_evidence_counts_missing_liquidity(_runtime_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    _runtime_dirs

    payload = build_phase2_rejection_evidence_payload(
        phase2_state=None,
        raw_candidates=[
            {
                "trade_id": "T3",
                "symbol": "NIFTY",
                "instrument": "OPT",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "quote_age_sec": 1.0,
                "spread_pct": 0.002,
                "liquidity_score": None,
                "quote_source": "option_chain_live",
            }
        ],
        ranked_candidates=[],
        drop_reason_counts={"missing_liquidity_context": 1},
    )
    assert payload["phase2_input_count"] == 1
    assert payload["phase2_output_count"] == 0
    assert payload["missing_liquidity_count"] == 1


def test_phase2_rejection_evidence_counts_unknown_quote_source(_runtime_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    _runtime_dirs
    from core.paths import logs_dir
    logs_dir().mkdir(parents=True, exist_ok=True)
    _write_valid_runtime_artifact(logs_dir() / "feed_runtime_latest.json")

    out = build_candidates_phase2(
        [
            {
                "trade_id": "T4",
                "symbol": "NIFTY",
                "instrument": "OPT",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "quote_age_sec": 1.0,
                "spread_pct": 0.002,
                "liquidity_score": 1.0,
                "quote_source": "unknown",
            }
        ]
    )
    assert out

    from core.paths import logs_dir

    payload = _read_json(logs_dir() / "phase2_rejection_latest.json")
    assert payload["input_candidate_count"] == 1
    assert payload["unknown_quote_source_count"] == 1
    assert int(payload.get("drop_reason_counts", {}).get("strict_unknown_quote_source", 0)) == 1


def test_phase2_rejection_evidence_does_not_change_output(_runtime_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    runtime_root, logs_root = _runtime_dirs

    candidate = {
        "trade_id": "T5",
        "symbol": "NIFTY",
        "instrument": "OPT",
        "execution_allowed": True,
        "tradable": True,
        "execution_ok": True,
        "quote_age_sec": 1.0,
        "spread_pct": 0.002,
        "liquidity_score": 1.0,
        "quote_source": "option_chain_live",
    }

    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", False, raising=False)
    out_no = build_candidates_phase2([dict(candidate)])

    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    out_yes = build_candidates_phase2([dict(candidate)])

    assert out_no == out_yes
    assert (logs_root / "phase2_rejection_latest.json").exists()
    assert (runtime_root / "phase2_rejection_latest.json").exists()


def test_phase2_evidence_does_not_reuse_stale_counts_across_calls(_runtime_dirs, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_REJECTION_EVIDENCE_ENABLE", True, raising=False)
    runtime_root, logs_root = _runtime_dirs

    build_candidates_phase2(
        [
            {
                "trade_id": "S1",
                "symbol": "NIFTY",
                "instrument": "OPT",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "quote_age_sec": None,
                "spread_pct": 0.002,
                "liquidity_score": 1.0,
                "quote_source": "option_chain_live",
            }
        ]
    )
    first = _read_json(logs_root / "phase2_rejection_latest.json")
    assert first["missing_quote_age_count"] == 1

    build_candidates_phase2([])
    second = _read_json(logs_root / "phase2_rejection_latest.json")
    assert second["input_candidate_count"] == 0
    assert second["missing_quote_age_count"] == 0


def test_phase2_no_input_emits_starvation_evidence(monkeypatch):
    payload = build_phase2_rejection_evidence_payload(
        phase2_state=None,
        raw_candidates=[],
        ranked_candidates=[],
        drop_reason_counts={},
    )

    assert payload["phase2_input_count"] == 0
    assert payload["phase2_output_count"] == 0
    assert payload["phase2_input_state"] == "NO_INPUT"
    assert payload["phase2_starvation_reason"] == "upstream_starvation"
    assert payload["phase2_drop_reasons_by_category"] == {}
    assert payload["hard_execution"] == 0


def test_phase2_hard_execution_drops_emit_explicit_counts():
    payload = build_phase2_rejection_evidence_payload(
        phase2_state=None,
        raw_candidates=[
            {
                "trade_id": "T1",
                "symbol": "NIFTY",
                "execution_ok": False,
                "hard_blockers": ["hard_execution"],
                "candidate_status": "blocked",
                "execution_status": "blocked",
            },
            {
                "trade_id": "T2",
                "symbol": "BANKNIFTY",
                "execution_ok": False,
                "hard_blockers": ["hard_execution"],
                "candidate_status": "blocked",
                "execution_status": "blocked",
            },
        ],
        ranked_candidates=[],
        drop_reason_counts={"hard_execution": 2},
    )

    assert payload["phase2_input_count"] == 2
    assert payload["phase2_output_count"] == 0
    assert payload["phase2_input_state"] == "INPUT_DROPPED"
    assert payload["phase2_drop_counts"]["hard_execution"] == 2
    assert payload["phase2_drop_reasons_by_category"]["hard_execution"] == 2


def test_phase2_missing_context_drop_categories_are_counted():
    payload = build_phase2_rejection_evidence_payload(
        phase2_state=None,
        raw_candidates=[
            {
                "trade_id": "T1",
                "symbol": "NIFTY",
                "spread_pct": None,
                "liquidity_score": None,
                "quote_age_sec": None,
                "quote_source": "unknown",
            }
        ],
        ranked_candidates=[],
        drop_reason_counts={"hard_execution": 1},
    )

    assert payload["phase2_input_state"] == "INPUT_DROPPED"
    assert payload["phase2_drop_reasons_by_category"]["missing_live_timing_context"] == 1


def test_phase2_feed_truth_blocked_candidates_are_counted():
    payload = build_phase2_rejection_evidence_payload(
        phase2_state=None,
        raw_candidates=[
            {
                "trade_id": "T1",
                "symbol": "SENSEX",
                "execution_ok": False,
                "execution_status": "blocked",
                "candidate_status": "blocked",
                "execution_block_reason": "stale_option_ltp",
                "hard_blockers": ["feed_truth_blocked"],
            }
        ],
        ranked_candidates=[],
        drop_reason_counts={"hard_execution": 1},
    )

    assert payload["phase2_drop_reasons_by_category"]["feed_truth_blocked"] == 1


def test_phase2_advisory_synthetic_fallback_categories_are_counted():
    payload = build_phase2_rejection_evidence_payload(
        phase2_state=None,
        raw_candidates=[
            {
                "trade_id": "T1",
                "symbol": "NIFTY",
                "candidate_status": "advisory_only",
                "execution_status": "advisory_only",
            },
            {
                "trade_id": "T2",
                "symbol": "BANKNIFTY",
                "synthetic_candidate": True,
                "source_flags": {"recovered_fallback": True},
            },
        ],
        ranked_candidates=[],
        drop_reason_counts={"advisory_only": 1, "hard_execution": 1},
    )

    assert payload["phase2_drop_reasons_by_category"]["advisory_or_queue_only"] == 1
    assert payload["phase2_drop_reasons_by_category"]["synthetic_or_fallback"] == 1


def test_phase2_accept_path_preserves_existing_behavior():
    payload = build_phase2_rejection_evidence_payload(
        phase2_state=None,
        raw_candidates=[
            {
                "trade_id": "PASS",
                "symbol": "NIFTY",
                "execution_ok": True,
                "tradable": True,
                "spread_pct": 0.01,
                "liquidity_score": 0.9,
                "quote_age_sec": 1.0,
                "quote_source": "option_chain_live",
            }
        ],
        ranked_candidates=[
            {
                "trade_id": "PASS",
                "symbol": "NIFTY",
                "execution_ok": True,
                "tradable": True,
                "spread_pct": 0.01,
                "liquidity_score": 0.9,
                "quote_age_sec": 1.0,
                "quote_source": "option_chain_live",
            }
        ],
        drop_reason_counts={},
    )

    assert payload["phase2_input_count"] == 1
    assert payload["phase2_output_count"] == 1
    assert payload["phase2_input_state"] == "ACCEPTED"


def test_phase2_evidence_failure_does_not_crash_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr("core.runtime_phase2_rejection_evidence.write_json_atomic", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("REPO_LOG_DIR", str(tmp_path / "logs"))
    feed_path = tmp_path / "logs" / "feed_runtime_latest.json"
    feed_path.parent.mkdir(parents=True, exist_ok=True)
    _write_valid_runtime_artifact(feed_path)

    payload = build_candidates_phase2(
        [
            {
                "trade_id": "PASS",
                "symbol": "NIFTY",
                "execution_allowed": True,
                "tradable": True,
                "execution_ok": True,
                "quote_age_sec": 1.0,
                "spread_pct": 0.01,
                "liquidity_score": 0.9,
                "quote_source": "option_chain_live",
            }
        ]
    )

    assert payload
