from __future__ import annotations

from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any, Callable

import pytest


BundleFactory = Callable[..., Path]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _deep_update(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _valid_artifacts() -> dict[str, Any]:
    controls = {
        "future_mutation": True,
        "timing_shift": True,
        "cost_sensitivity": True,
    }
    raw_tests = {
        "collected": 75,
        "passed": 75,
        "failed": 0,
        "errors": 0,
        "repository_commit": "qa-commit-001",
    }
    return {
        "source/option_replay_wfa_report.json": {
            "engine_module": "core.option_backtest.engine.OptionBacktestEngine",
            "run_id": "qa-run-001",
            "frozen_config_hash": "c" * 64,
            "frozen_config": {
                "base_config": {"research_mode": "REAL_EXECUTABLE_RESEARCH"}
            },
            "partitions": {
                "validation": {"status": "completed"},
                "holdout": {"status": "skipped_validation_failed"},
            },
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
        },
        "source/negative_controls_input.json": {"controls": deepcopy(controls)},
        "source/test_results_input.json": deepcopy(raw_tests),
        "source/validation/summary.json": {"certifiable": True},
        "source/validation/trade_journal.json": [],
        "source/validation/decision_samples.json": [],
        "source_index.json": {
            "producer": "core.ai_certification.exporter.export_option_replay_wfa_bundle",
            "wfa_report": "source/option_replay_wfa_report.json",
            "dataset": {"file_sha256": "a" * 64, "size_bytes": 4096},
            "copied_files": [
                {
                    "artifact": "source/option_replay_wfa_report.json",
                    "role": "wfa_report",
                },
                {
                    "artifact": "source/negative_controls_input.json",
                    "role": "controls_input",
                },
                {
                    "artifact": "source/test_results_input.json",
                    "role": "tests_input",
                },
                {
                    "artifact": "source/validation/summary.json",
                    "role": "validation_summary.json",
                },
                {
                    "artifact": "source/validation/trade_journal.json",
                    "role": "validation_trade_journal.json",
                },
                {
                    "artifact": "source/validation/decision_samples.json",
                    "role": "validation_decision_samples.json",
                },
            ],
        },
        "dataset_manifest.json": {
            "dataset_sha256": "a" * 64,
            "row_count": 2000,
            "time_start": "2026-01-01T09:15:00+05:30",
            "time_end": "2026-06-30T15:30:00+05:30",
            "provider": "upstox",
            "symbol": "NIFTY26JUL25000CE",
            "expiry": "2026-07-30",
            "duplicate_timestamp_count": 0,
            "missing_timestamp_count": 0,
            "malformed_timestamp_count": 0,
            "stale_quote_count": 0,
            "post_expiry_row_count": 0,
            "invalid_ohlc_count": 0,
            "quote_columns_complete": True,
            "contract_metadata_complete": True,
        },
        "engine_identity.json": {
            "engine_module": "core.option_backtest.engine.OptionBacktestEngine",
            "wfa_engine_module": "core.option_backtest.wfa.run_option_replay_wfa",
            "legacy_or_proxy_path_used": False,
            "hardcoded_metrics_used": False,
        },
        "run_configuration.json": {
            "execution_mode": "REAL_EXECUTABLE_RESEARCH",
            "frozen_config_hash": "c" * 64,
        },
        "timing_evidence.json": {
            "signals_checked": 150,
            "same_event_entry_count": 0,
            "chronology_violation_count": 0,
            "missing_timing_provenance_count": 0,
            "future_data_dependency_count": 0,
            "future_mutation_stable": True,
            "elapsed_hold_verified": True,
        },
        "fill_evidence.json": {
            "entries_use_executable_side": True,
            "exits_use_executable_side": True,
            "strict_liquidity_mode": True,
            "cost_monotonicity_verified": True,
            "fallback_liquidity_fill_count": 0,
            "proxy_exit_mark_count": 0,
            "missing_bid_ask_accepted_count": 0,
            "synthetic_liquidity_fill_count": 0,
        },
        "cost_reconciliation.json": {
            "gross_pnl": 120.0,
            "total_costs": 135.0,
            "net_pnl": -15.0,
            "trade_net_pnl_sum": -15.0,
            "total_trades": 150,
            "winning_trades": 60,
            "losing_trades": 90,
            "flat_trades": 0,
            "ambiguity_count": 0,
            "tolerance": 1e-8,
        },
        "wfa_partition_plan.json": {
            "chronological": True,
            "non_overlapping": True,
            "purge_embargo_applied": True,
            "validation_before_holdout": True,
            "holdout_isolated_from_selection": True,
        },
        "wfa_results.json": {
            "repeated_holdout_run_count": 0,
            "contamination_count": 0,
            "known_setup_regime_oos": True,
            "holdout_fraction": 0.25,
        },
        "negative_controls.json": {
            "controls": deepcopy(controls),
            "source": "source/negative_controls_input.json",
        },
        "test_results.json": {
            **deepcopy(raw_tests),
            "commit_matches_bundle": True,
            "source": "source/test_results_input.json",
        },
        "strategy_result.json": {
            "verdict": "NO_STRUCTURAL_EDGE",
            "trades": 150,
            "after_cost_expectancy": -0.1,
            "profit_factor": 0.82,
        },
    }


@pytest.fixture
def qa_bundle_factory(tmp_path: Path) -> BundleFactory:
    counter = itertools.count(1)

    def factory(
        *,
        artifact_overrides: dict[str, dict[str, Any]] | None = None,
        manifest_overrides: dict[str, Any] | None = None,
        omit: set[str] | None = None,
        raw_artifacts: dict[str, str] | None = None,
        extra_artifacts: dict[str, Any] | None = None,
    ) -> Path:
        root = tmp_path / f"qa_bundle_{next(counter)}"
        root.mkdir()
        artifacts = _valid_artifacts()
        overrides = artifact_overrides or {}
        for name, patch in overrides.items():
            if name not in artifacts:
                artifacts[name] = {}
            if not isinstance(artifacts[name], dict):
                raise TypeError(f"artifact is not patchable JSON: {name}")
            _deep_update(artifacts[name], patch)

        if (
            "negative_controls.json" in overrides
            and "source/negative_controls_input.json" not in overrides
        ):
            artifacts["source/negative_controls_input.json"]["controls"] = deepcopy(
                artifacts["negative_controls.json"]["controls"]
            )
        if (
            "test_results.json" in overrides
            and "source/test_results_input.json" not in overrides
        ):
            normalized_tests = artifacts["test_results.json"]
            raw_tests = artifacts["source/test_results_input.json"]
            for field in (
                "collected",
                "passed",
                "failed",
                "errors",
                "repository_commit",
            ):
                if field in normalized_tests:
                    raw_tests[field] = normalized_tests[field]

        artifacts.update(extra_artifacts or {})
        for name in omit or set():
            artifacts.pop(name, None)

        for name, payload in artifacts.items():
            path = root / name
            if name in (raw_artifacts or {}):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(raw_artifacts[name], encoding="utf-8")
            elif isinstance(payload, str):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(payload, encoding="utf-8")
            else:
                _write_json(path, payload)

        manifest: dict[str, Any] = {
            "bundle_schema_version": "1.0",
            "run_id": "qa-run-001",
            "strategy_id": "OPENING_RANGE_BREAKOUT",
            "repository_commit": "qa-commit-001",
            "created_at": "2026-07-17T10:30:00Z",
            "policy_version": "backtest-certification-v1",
            "artifacts": {
                name: _sha256(root / name)
                for name in artifacts
            },
        }
        _deep_update(manifest, manifest_overrides or {})
        _write_json(root / "bundle_manifest.json", manifest)
        return root

    return factory


@pytest.fixture
def qa_rehash_manifest() -> Callable[[Path], None]:
    def rehash(root: Path) -> None:
        manifest_path = root / "bundle_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"] = {
            path.relative_to(root).as_posix(): _sha256(path)
            for path in sorted(root.rglob("*"))
            if path.is_file() and path.name != "bundle_manifest.json"
        }
        _write_json(manifest_path, manifest)

    return rehash
