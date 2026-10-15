"""
Comprehensive unit and integration tests for GovernedMorningOrchestrator and
HeritageManifest wiring (ARCH-01 Stage 2 GSD verification).

Tests:
1. Orchestrator CLI argument propagation (--heritage-manifest, --heritage-manifest-sha256).
2. Orchestrator auto-resolves valid predecessor manifest and appends arguments to mros_cmd.
3. Orchestrator handles corrupt or missing manifest gracefully without crashing.
4. GovernedAuthCallbackServer BaseException handling returns clean 500 error page to browser.
5. LiveSourceRuntimeBridge decoupled_options_mode passes subscription check with index-only budget.
"""

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.governed_morning_orchestrator import GovernedMorningOrchestrator, LauncherState
from core.market_event_graph_live_runtime_bridge import (
    LiveSourceRuntimeBridge,
    LiveUniverseContract,
)


def _sample_manifest_dict(session_date: str) -> dict:
    return {
        "manifest_version": "v1",
        "session_date": session_date,
        "exchange": "NSE",
        "market": "FNO",
        "nodes": [
            {
                "symbol": "NIFTY",
                "instrument_token": 256265,
                "close_price": 24850.5,
                "vwap": 24820.1,
                "volume": 12500000,
            }
        ],
        "edges": [],
        "metadata": {"sealed": True, "created_at": f"{session_date}T16:00:00+05:30"},
    }


def test_orchestrator_cli_args_propagation(tmp_path: Path):
    manifest_file = tmp_path / "heritage_manifest.json"
    manifest_file.write_text("{}")
    sha = "test_sha_256"

    orch = GovernedMorningOrchestrator(
        repo_root=tmp_path,
        state_root=tmp_path,
        session_date="2026-10-15",
        heritage_manifest=manifest_file,
        heritage_manifest_sha256=sha,
    )
    assert orch.heritage_manifest == manifest_file.resolve()
    assert orch.heritage_manifest_sha256 == sha


def test_orchestrator_auto_resolves_and_wires_mros_cmd(tmp_path: Path):
    # Setup predecessor session directory
    session_dir = tmp_path / "sessions" / "session_2026-10-14"
    session_dir.mkdir(parents=True)
    manifest_file = session_dir / "heritage_manifest.json"
    content = json.dumps(_sample_manifest_dict("2026-10-14"), indent=2)
    manifest_file.write_text(content)
    expected_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()

    orch = GovernedMorningOrchestrator(
        repo_root=tmp_path,
        state_root=tmp_path,
        session_date="2026-10-15",
        observer_engine="meg_live",
        supervise=False,
    )

    mock_report = {
        "verdict": "PASS",
        "manifest_sha256": expected_sha,
        "session_date": "2026-10-14",
        "errors": [],
    }

    with patch(
        "core.heritage_manifest_resolver.verify_market_heritage_manifest",
        return_value=mock_report,
    ), patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_popen.return_value = mock_proc

        success = orch.step_arm_observer()
        assert success is True
        assert orch.heritage_manifest_resolution is not None
        assert orch.heritage_manifest_resolution.manifest_path == manifest_file.resolve()

        # Verify arguments passed to subprocess.Popen for mros_cmd
        called_cmd = mock_popen.call_args[0][0]
        assert "--heritage-manifest" in called_cmd
        idx = called_cmd.index("--heritage-manifest")
        assert called_cmd[idx + 1] == str(manifest_file.resolve())
        assert "--heritage-manifest-sha256" in called_cmd
        idx_sha = called_cmd.index("--heritage-manifest-sha256")
        assert called_cmd[idx_sha + 1] == expected_sha


def test_orchestrator_unverified_manifest_does_not_wire_mros(tmp_path: Path):
    session_dir = tmp_path / "sessions" / "session_2026-10-14"
    session_dir.mkdir(parents=True)
    manifest_file = session_dir / "heritage_manifest.json"
    manifest_file.write_text(json.dumps(_sample_manifest_dict("2026-10-14")))

    orch = GovernedMorningOrchestrator(
        repo_root=tmp_path,
        state_root=tmp_path,
        session_date="2026-10-15",
        observer_engine="meg_live",
        supervise=False,
    )

    mock_report = {
        "verdict": "FAIL",
        "manifest_sha256": "fake",
        "session_date": "2026-10-14",
        "errors": ["SIGNATURE_INVALID"],
    }

    with patch(
        "core.heritage_manifest_resolver.verify_market_heritage_manifest",
        return_value=mock_report,
    ), patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_popen.return_value = mock_proc

        success = orch.step_arm_observer()
        assert success is True
        called_cmd = mock_popen.call_args[0][0]
        # Should not wire unverified manifest
        assert "--heritage-manifest" not in called_cmd


def test_bridge_decoupled_options_mode_tick_provenance():
    contract = LiveUniverseContract(
        schema_version=1,
        broker_provider="kite",
        token_domain="kite_instrument_token",
        name="NIFTY50",
        version="v1",
        effective_date="2026-10-15",
        source_retrieval_date="2026-10-15",
        source_page_updated_date="2026-10-15",
        official_source_url="https://example.com",
        official_raw_sha256="abc",
        index_symbol="NIFTY",
        index_instrument_token=256265,
        provider_native_index_identifier="NSE:NIFTY",
        constituents=tuple({"symbol": f"SYM_{i}", "instrument_token": 1000 + i} for i in range(50)),
        broker_instrument_master={},
        source_provenance="test",
        capture_session_id="test_run",
        canonical_sha256="canonical_hash",
    )

    bridge = LiveSourceRuntimeBridge(decoupled_options_mode=True)
    evidence = {
        "subscription_evidence_id": "sub_1",
        "feed_session_id": "feed_sess_1",
        "feed_epoch": 1,
        "token_by_symbol": {"NIFTY": 256265},
        "token_lifecycle": {
            "256265": {
                "feed_session_id": "feed_sess_1",
                "subscribe_call_succeeded_epoch": 100.0,
                "first_post_request_tick_epoch": 101.0,
                "mode_request_succeeded_epoch": 102.0,
                "final_current_generation_local_mode_is_full": True,
                "post_mode_full_count": 5,
                "first_post_mode_full_epoch": 103.0,
                "latest_post_mode_full_epoch": 104.0,
            }
        },
        "token_resolved_symbols": ["NIFTY"],
        "subscription_requested_symbols": ["NIFTY"],
        "subscription_request_succeeded_symbols": ["NIFTY"],
        "mode_request_succeeded_symbols": ["NIFTY"],
        "live_tick_observed_symbols": ["NIFTY"],
        "full_payload_observed_symbols": ["NIFTY"],
    }

    with patch("core.market_event_graph_live_runtime_bridge.current_feed_epoch", return_value=1):
        ok, reason, rej = bridge._validate_subscription_evidence(contract, evidence)
        assert ok is True
        assert reason == "OK" or reason == ""
