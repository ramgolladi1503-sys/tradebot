"""Offline Scenario B composition: durable bars and verified CAS after restart.

Fixtures are synthetic and prove repository code paths only. They are not
historical source authority or a live-service restart test.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from core import market_session_memory_contract as memory_contract
from core import ohlc_buffer as ohlc_module
from core.cas_primitive_producer import CASPrimitiveStore
from core.market_heritage_graph import (
    load_same_session_cas_references,
    publish_same_session_cas_manifest,
)
from core.market_session_store import MarketSessionStore
from core.market_snapshot_builder import build_market_snapshot, build_symbol_market_snapshot
from core.read_only_consumer_cycle import _evaluate_cas
import core.orchestrator as orchestrator
import core.runtime_snapshot_producer as producer
from core.runtime_snapshot_producer import _build_advisory_latest_payload as _real_advisory_builder


IST = ZoneInfo("Asia/Kolkata")
SESSION_DATE = "2026-10-02"
SESSION = {
    "trading_date": SESSION_DATE,
    "venue": "NSE",
    "calendar_id": "scenario-b-fixture-calendar",
    "calendar_version": "v1",
}
SOURCE_SHA = "b" * 40
TOKEN = 256265


def _captured_tick(*, run_id: str, price: float, epoch: float) -> dict:
    event = {
        "instrument_token": TOKEN,
        "underlying_symbol": "NIFTY",
        "last_price": price,
        "volume": 10,
        "oi": 20,
        "source_timestamp_field": "exchange_timestamp",
        "source_timestamp_epoch": epoch,
    }
    digest = hashlib.sha256(json.dumps(
        event, sort_keys=True, separators=(",", ":"), default=str
    ).encode()).hexdigest()
    return {
        **event,
        "timestamp_epoch": epoch,
        "timestamp_authority": "EXCHANGE_TIMESTAMP",
        "timestamp_source_field": "exchange_timestamp",
        "receive_timestamp_epoch": epoch,
        "timestamp_fallback_used": False,
        "source_event_id": f"feed:{run_id}:1:{TOKEN}:{digest[:16]}",
        "source_event_sha256": digest,
        "source_event_payload": event,
    }


def _publish_prior_run(root: Path, *, run_id="run-a", first_price=25000.0) -> Path:
    open_epoch = datetime.fromisoformat(f"{SESSION_DATE}T09:15:00+05:30").timestamp()
    ten_epoch = datetime.fromisoformat(f"{SESSION_DATE}T10:00:00+05:30").timestamp()
    captured_at = "2026-10-02T15:14:00+05:30"
    old_run = CASPrimitiveStore(
        root / run_id / "cas.json", session_id=run_id,
        source_sha=SOURCE_SHA, underlying_token=TOKEN,
    )
    old_run.capture("0915", open_epoch,
        _captured_tick(run_id=run_id, price=first_price, epoch=open_epoch + 0.5),
        capture_timestamp_ist=captured_at)
    old_run.capture("1000", ten_epoch,
        _captured_tick(run_id=run_id, price=25100.0, epoch=ten_epoch + 0.5),
        capture_timestamp_ist=captured_at)
    heritage_root = root / "heritage"
    published = publish_same_session_cas_manifest(
        heritage_root=heritage_root, session_identity=SESSION, run_id=run_id,
        source_sha=SOURCE_SHA, underlying_token=TOKEN, primitives=old_run.rows,
    )
    assert published["status"] == "PUBLISHED"
    old_run.persist()
    return heritage_root


def _runtime_outputs(
    tmp_path,
    monkeypatch,
    *,
    inherited,
    when,
    spot_healthy=True,
    spot_token=TOKEN,
    candidate_decisions_path=None,
    use_real_advisory=False,
):
    epoch = when.timestamp()
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: logs_root / "suggestions.jsonl")
    monkeypatch.setattr(producer, "MARKET_SNAPSHOT_PATH", runtime_root / "market_snapshot.json")
    monkeypatch.setattr(producer, "ADVISORY_LATEST_PATH", runtime_root / "advisory_latest.json")
    monkeypatch.setattr(producer, "FEED_RUNTIME_LATEST_PATH", runtime_root / "feed_runtime_latest.json")
    monkeypatch.setattr(producer, "TOKEN_RESOLUTION_LATEST_PATH", runtime_root / "token_resolution_latest.json")
    if use_real_advisory:
        monkeypatch.setattr(producer, "_build_advisory_latest_payload", _real_advisory_builder)
    else:
        monkeypatch.setattr(producer, "_build_advisory_latest_payload", lambda **_: {
            "rows": [], "row_count": 0, "source_path": "fixture", "notes": []
        })
    monkeypatch.setattr(producer, "_build_and_write_canonical_ranked_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(producer, "stages_build_feed_health_truth_latest_payload", lambda payload: (
        {"feed_ok": True, "feed_truth_state": "OK", "feed_truth_strict_live": True},
        SimpleNamespace(to_payload=lambda: {"feed_ok": True}),
    ))
    monkeypatch.setattr(producer, "load_current_feed_runtime", lambda _: {
        "valid": True,
        "payload": {"ws_connected": True, "effective_ws_connected": True},
    })
    monkeypatch.setattr(producer.time, "time", lambda: epoch)
    monkeypatch.setattr(producer, "now_ist", lambda: when)

    nifty = build_symbol_market_snapshot(
        spot=25100.0,
        ltp=25100.0,
        feed_health={
            "status": "HEALTHY" if spot_healthy else "STALE",
            "underlying_quote_age_sec": 0.2 if spot_healthy else 900.0,
        },
        quote_truth={
            "symbol": "NIFTY", "instrument_token": spot_token,
            "is_fresh": spot_healthy, "is_executable_quote": False,
        },
    )
    snapshot = build_market_snapshot(
        generated_at=when.isoformat(), market_open=True,
        symbols_payload={"NIFTY": nifty}, warnings=[], compute_ms=1.0,
        loop_id="run-b:restart-cycle",
    )
    return producer.produce_and_store_runtime_snapshots(
        market_snapshot=snapshot,
        producer="scenario_b_offline_fixture",
        loop_id="run-b:restart-cycle",
        session_id="run-b",
        source_sha=SOURCE_SHA,
        inherited_cas_references=inherited,
        trading_session_identity=SESSION,
        candidate_decisions_path=candidate_decisions_path,
    )


@pytest.fixture
def restart_context(tmp_path, monkeypatch):
    when = datetime(2026, 10, 2, 15, 14, 0, tzinfo=IST)
    heritage_root = _publish_prior_run(tmp_path)
    inherited = load_same_session_cas_references(
        heritage_root=heritage_root, session_identity=SESSION,
        current_run_id="run-b", source_sha=SOURCE_SHA,
        underlying_token=TOKEN,
    )
    assert inherited["status"] == "VERIFIED"

    # Simulate the prior process creating completed bars, then lose all of its
    # in-memory state and reopen the existing SQLite authority in a new buffer.
    store_path = tmp_path / "market-session.sqlite"
    report_root = tmp_path / "reports"
    store = MarketSessionStore(db_path=store_path, report_root=report_root)
    previous_store = getattr(ohlc_module.ohlc_buffer, "_session_store", None)
    monkeypatch.setattr(ohlc_module.ohlc_buffer, "_session_store", previous_store, raising=False)
    monkeypatch.setattr(memory_contract, "market_session_store", store)
    monkeypatch.setattr(memory_contract, "_INSTALLED", False)
    monkeypatch.setattr(memory_contract, "_INSTALL_STATUS", {})
    assert memory_contract.install()["status"] == "PERSISTENCE_READY"
    buffer = ohlc_module.OhlcBuffer(session_store=store)
    opened = datetime(2026, 10, 2, 9, 15, 5, tzinfo=IST)
    provenance = {
        "source_type": "deterministic_test",
        "synthetic_fixture": True,
        "fixture_id": "scenario-b-synthetic-bars-v1",
        "historical_seed": False,
        "non_live_fallback": False,
        "recovered_synthetic": False,
    }
    for minute in range(359):
        event_time = opened + timedelta(minutes=minute)
        accepted = buffer.update_tick(
            "NIFTY", 25000.0 + minute * 10.0, volume=1.0,
            ts=event_time, provenance=provenance,
        )
        assert accepted["accepted"] is True
    cutoff_tick = buffer.update_tick(
        "NIFTY", 28590.0, volume=1.0, ts=when, provenance=provenance,
    )
    assert cutoff_tick["accepted"] is True
    assert len(store.get_bars("NIFTY", as_of=when, timeframe="1m", session_date=SESSION_DATE)) == 359
    assert all(
        row["bar_provenance"]["source_type"] == "deterministic_test"
        and row["bar_provenance"]["first_live_tick_epoch"] is None
        and row["bar_provenance"]["last_live_tick_epoch"] is None
        for row in store.get_bars("NIFTY", as_of=when, timeframe="1m", session_date=SESSION_DATE)
    )

    # Restart boundary: a fresh store object and empty process-local OHLC cache.
    reopened = MarketSessionStore(db_path=store_path, report_root=report_root)
    future_start = datetime(2026, 10, 2, 15, 14, tzinfo=IST)
    assert reopened.persist_completed_bar("NIFTY", {
        "ts": future_start,
        "open": 28600.0,
        "high": 28610.0,
        "low": 28590.0,
        "close": 28605.0,
        "volume": 1.0,
        "bar_provenance": {
            "source_type": "deterministic_test",
            "historical_seed": False,
            "replay_fixture": False,
            "non_live_fallback": False,
            "recovered_synthetic": False,
        },
    }, completed_as_of=when + timedelta(minutes=1))["persisted"] is True
    restarted_buffer = ohlc_module.OhlcBuffer(session_store=reopened)
    restored = restarted_buffer.get_completed_bars("NIFTY", as_of=when)
    assert len(restored) == 359
    assert restored[0]["ts"] == datetime(2026, 10, 2, 9, 15, tzinfo=IST)
    assert restored[-1]["ts"] == datetime(2026, 10, 2, 15, 13, tzinfo=IST)
    before_completion = restarted_buffer.get_completed_bars(
        "NIFTY", as_of=when - timedelta(seconds=30),
    )
    assert len(before_completion) == 358
    assert all(row["ts"] < datetime(2026, 10, 2, 15, 13, tzinfo=IST) for row in before_completion)
    later = restarted_buffer.get_completed_bars("NIFTY", as_of=when + timedelta(minutes=1))
    assert len(later) == 360
    assert later[-1]["ts"] == future_start
    monkeypatch.setattr(orchestrator, "_global_market_session_store", reopened)
    return tmp_path, monkeypatch, inherited["primitives"], when, reopened


def test_scenario_b_restart_composes_restored_c1_memory_and_verified_cas_advisory(restart_context):
    root, monkeypatch, inherited, when, store = restart_context

    memory = store.get_persisted_market_memory(
        "NIFTY", as_of_timestamp=when, freshness_watermark=1.0,
        trace_id="scenario-b-restart",
    )
    assert memory.symbol == "NIFTY"
    assert memory.rolling_1m_bars_count == 359
    market_data = {
        "valid": True,
        "timestamp": when.timestamp(),
        "ltp_ts_epoch": when.timestamp(),
        "ltp_source": "live",
        "time_sanity": {"ok": True, "ltp_ts_epoch": when.timestamp()},
        "offhours_mode": False,
    }
    evaluations, candidates = orchestrator._evaluate_c1_c2_for_symbol(
        market_data=market_data, sym="NIFTY", trace_id="scenario-b-restart",
        ts_str=when.strftime("%Y-%m-%d %H:%M:%S%z"),
    )
    c1 = next(row for row in evaluations if row.strategy_id == "C1_INTRADAY_15M_IMPULSE")
    # C1's existing time window is closed by the 15:14 CAS cutoff. Its
    # out-of-window result is intentional; the separate 09:45 restart test
    # proves in-window C1 qualification from restored bars.
    assert c1.reason_code == "C1_OUT_OF_WINDOW"
    assert candidates == []

    outputs = _runtime_outputs(root, monkeypatch, inherited=inherited, when=when)
    assert outputs["cas_input_gate"]["state"] == "READY"
    for key, value in {
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "paper_authorized": False,
        "live_authorized": False,
        "append": False,
    }.items():
        assert outputs["cas_input_gate"][key] is value
    cas_input = outputs["cas_short_horizon_inputs"]
    assert cas_input["lineage_status"] == "INHERITED_VERIFIED"
    assert cas_input["source_run_ids"] == ["run-a"]
    assert cas_input["signal_input_09_15"] == 25000.0
    assert cas_input["signal_input_10_00"] == 25100.0

    before_cutoff = when - timedelta(seconds=1)
    early_outputs = _runtime_outputs(
        root, monkeypatch, inherited=inherited, when=before_cutoff,
    )
    early = _evaluate_cas(
        runtime_outputs=early_outputs, output_root=root / "cas-before-cutoff",
        session_id="run-b", source_sha=SOURCE_SHA, now=before_cutoff,
    )
    assert early["verdict"] == "PENDING"
    assert early["reason"] == "pre_cutoff_observation"
    assert not (root / "cas-before-cutoff" / "cas_v2_artifact.json").exists()

    result = _evaluate_cas(
        runtime_outputs=outputs, output_root=root / "cas-consumer",
        session_id="run-b", source_sha=SOURCE_SHA, now=when,
    )
    assert result["verdict"] == "PASS", result
    closed_authority = {
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "paper_authorized": False,
        "live_authorized": False,
        "append": False,
    }
    assert {key: result[key] for key in closed_authority} == closed_authority
    artifact = json.loads((root / "cas-consumer" / "cas_v2_artifact.json").read_text())
    assert artifact["execution_status"] == "advisory_only"
    assert artifact["read_only"] is True
    assert artifact["broker_write_authority"] is False
    assert artifact["order_authority"] is False
    assert artifact["paper_authorized"] is False
    assert artifact["live_execution_authorized"] is False
    assert artifact["broker_order_calls"] == 0
    assert {key: artifact[key] for key in closed_authority} == closed_authority
    readiness = json.loads((root / "cas-consumer" / "cas_readiness_latest.json").read_text())
    assert {key: readiness[key] for key in closed_authority} == closed_authority


def test_scenario_b_restart_rejects_cross_date_and_stale_spot(restart_context):
    root, monkeypatch, inherited, when, _store = restart_context
    wrong_day = {**SESSION, "trading_date": "2026-10-05"}
    cross_date = load_same_session_cas_references(
        heritage_root=root / "heritage", session_identity=wrong_day,
        current_run_id="run-b", source_sha=SOURCE_SHA,
        underlying_token=TOKEN,
    )
    assert cross_date["status"] == "BLOCKED"
    assert cross_date["primitives"] == {}

    outputs = _runtime_outputs(
        root, monkeypatch, inherited=inherited, when=when, spot_healthy=False,
    )
    assert outputs["cas_input_gate"]["state"] == "BLOCKED"
    assert outputs["cas_input_gate"]["reason_code"] == "cas_required_spot_unhealthy"
    result = _evaluate_cas(
        runtime_outputs=outputs, output_root=root / "blocked-cas-consumer",
        session_id="run-b", source_sha=SOURCE_SHA, now=when,
    )
    assert result["verdict"] == "PENDING"
    assert not (root / "blocked-cas-consumer" / "cas_v2_artifact.json").exists()

    mismatch = _runtime_outputs(
        root, monkeypatch, inherited=inherited, when=when, spot_token=TOKEN + 1,
    )
    assert mismatch["cas_input_gate"]["state"] == "BLOCKED"
    assert mismatch["cas_input_gate"]["reason_code"] == "cas_required_spot_identity_mismatch"


def test_scenario_b_restart_rejects_corrupted_heritage_manifest(tmp_path):
    heritage_root = _publish_prior_run(tmp_path)
    manifests = [path for path in heritage_root.glob("heritage-*.json")
                 if path.name != "heritage-index-v1.json"]
    assert len(manifests) == 1
    manifests[0].write_bytes(manifests[0].read_bytes() + b" ")
    blocked = load_same_session_cas_references(
        heritage_root=heritage_root, session_identity=SESSION,
        current_run_id="run-b", source_sha=SOURCE_SHA,
        underlying_token=TOKEN,
    )
    assert blocked["status"] == "BLOCKED"
    assert blocked["primitives"] == {}


def test_scenario_b_restart_rejects_ambiguous_same_session_heritage(tmp_path):
    heritage_root = _publish_prior_run(tmp_path, run_id="run-a", first_price=25000.0)
    conflicting = _publish_prior_run(tmp_path, run_id="run-c", first_price=25200.0)
    assert conflicting == heritage_root
    blocked = load_same_session_cas_references(
        heritage_root=heritage_root, session_identity=SESSION,
        current_run_id="run-b", source_sha=SOURCE_SHA,
        underlying_token=TOKEN,
    )
    assert blocked["status"] == "BLOCKED"
    assert blocked["primitives"] == {}
    assert {row["reason"] for row in blocked["blockers"]} == {
        "CONFLICTING_SAME_SESSION_CAS_SOURCES"
    }


def test_scenario_e_restart_keeps_stale_required_spot_blocked_and_projects_valid_empty_advisory(
    restart_context,
):
    root, monkeypatch, inherited, when, store = restart_context
    memory = store.get_persisted_market_memory(
        "NIFTY", as_of_timestamp=when, freshness_watermark=1.0,
        trace_id="scenario-e-restart",
    )
    assert memory.rolling_1m_bars_count == 359

    # This is an explicitly valid-empty ledger, distinct from an absent source.
    decision_ledger = root / "scenario-e" / "candidate_decisions.jsonl"
    decision_ledger.parent.mkdir(parents=True)
    decision_ledger.write_bytes(b"")
    outputs = _runtime_outputs(
        root,
        monkeypatch,
        inherited=inherited,
        when=when,
        spot_healthy=False,
        candidate_decisions_path=decision_ledger,
        use_real_advisory=True,
    )

    assert outputs["cas_input_gate"]["state"] == "BLOCKED"
    assert outputs["cas_input_gate"]["reason_code"] == "cas_required_spot_unhealthy"
    assert outputs["advisory_latest"]["rows"] == []
    assert outputs["advisory_latest"]["row_count"] == 0
    assert Path(outputs["advisory_latest"]["source_path"]).resolve() == decision_ledger.resolve()
    assert f"fallback_source:{decision_ledger}" in outputs["advisory_latest"]["notes"]
    expected_closed_authority = {
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "paper_authorized": False,
        "live_authorized": False,
        "append": False,
    }
    assert {key: outputs["cas_input_gate"][key] for key in expected_closed_authority} == expected_closed_authority

    result = _evaluate_cas(
        runtime_outputs=outputs,
        output_root=root / "scenario-e" / "cas-consumer",
        session_id="run-b",
        source_sha=SOURCE_SHA,
        now=when,
    )
    assert result["verdict"] == "PENDING"
    assert result["reason"] == "short_horizon_inputs_missing"
    assert {key: result[key] for key in expected_closed_authority} == expected_closed_authority
    cas_root = root / "scenario-e" / "cas-consumer"
    assert not (cas_root / "cas_v2_artifact.json").exists()
    receipt = json.loads((cas_root / "cas_readiness_latest.json").read_text())
    assert {key: receipt[key] for key in expected_closed_authority} == expected_closed_authority
    assert receipt["broker_write_authority"] is False
    assert receipt["order_authority"] is False

    malformed_root = root / "scenario-e" / "malformed-cas-consumer"
    malformed = _evaluate_cas(
        runtime_outputs={"cas_short_horizon_inputs": {"symbol": "NIFTY"}},
        output_root=malformed_root,
        session_id="run-b",
        source_sha=SOURCE_SHA,
        now=when,
    )
    assert malformed["verdict"] == "PENDING"
    assert {key: malformed[key] for key in expected_closed_authority} == expected_closed_authority
    malformed_receipt = json.loads((malformed_root / "cas_readiness_latest.json").read_text())
    assert {key: malformed_receipt[key] for key in expected_closed_authority} == expected_closed_authority
    assert malformed_receipt["broker_write_authority"] is False
    assert malformed_receipt["order_authority"] is False
    assert not (malformed_root / "cas_v2_artifact.json").exists()
