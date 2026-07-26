from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pandas as pd

from research.option_e2e_recertification_v4.ce_pe_history_inventory_v1.build_inventory import build
from research.option_e2e_recertification_v4.ce_pe_history_inventory_v1.inventory import (
    build_inventory,
    classify_parquet,
)


def _manifest(
    path: Path, root: Path, *, allowed: list[str] | None = None
) -> Path:
    path.write_text(
        json.dumps(
            {
                "roots": [
                    {
                        "current_root_id": "ROOT",
                        "absolute_path": str(root),
                        "allowed_candidate_classes": allowed
                        or ["UNDERLYING_DATASET"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_classify_parquet_requires_option_relevance() -> None:
    assert (
        classify_parquet(
            ["timestamp", "open", "high", "low", "close"],
            path_hint="nifty.parquet",
        )
        is None
    )
    assert (
        classify_parquet(
            ["ts", "instrument_key", "bid_price", "ask_price", "ltp"],
            path_hint="combined.parquet",
        )
        == "RAW_OPTION_TICK_DATASET"
    )


def test_metadata_first_inventory_does_not_use_pandas_read_parquet(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    pd.DataFrame(
        {
            "ts": [1_784_006_404.0],
            "instrument_key": ["NSE_FO|1"],
            "bid_price": [9.9],
            "ask_price": [10.1],
            "ltp": [10.0],
        }
    ).to_parquet(root / "option_ticks.parquet")
    pd.DataFrame(
        {
            "timestamp": ["2026-07-14T09:15:00"],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
        }
    ).to_parquet(root / "broad_underlying.parquet")
    monkeypatch.setattr(
        pd,
        "read_parquet",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("full dataframe read forbidden")
        ),
    )

    result = build_inventory(_manifest(tmp_path / "manifest.json", root))

    option_ids = [
        row["candidate_id"]
        for row in result["candidates"]
        if row.get("candidate_class") == "RAW_OPTION_TICK_DATASET"
    ]
    assert option_ids == ["ROOT:option_ticks.parquet"]
    assert result["parquet_metadata_inspected"] == 2
    assert result["candidate_limit"] is None


def test_stale_allowed_classes_do_not_hide_option_files(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    pd.DataFrame(
        {
            "ts": [1_784_006_404.0],
            "instrument_token": ["1"],
            "best_bid": [9.9],
            "best_ask": [10.1],
        }
    ).to_parquet(root / "hidden_option.parquet")

    result = build_inventory(
        _manifest(
            tmp_path / "manifest.json",
            root,
            allowed=["UNDERLYING_DATASET"],
        )
    )

    assert result["option_candidate_count"] == 1
    assert result["root_records"][0]["allowed_class_filter_applied"] is False


def test_denied_outcome_file_is_metadata_only(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    denied = root / "strategy_pnl_results.json"
    denied.write_text("not-json-and-must-not-be-opened", encoding="utf-8")

    result = build_inventory(_manifest(tmp_path / "manifest.json", root))

    assert result["denied_metadata_only_count"] == 1
    assert result["denied_metadata_only"][0]["content_opened"] is False
    assert "physical_sha256" not in result["denied_metadata_only"][0]


def test_archive_option_date_is_session_directory_not_expiry_name(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    option = pd.DataFrame(
        {
            "timestamp": ["2026-07-09T09:16:00"],
            "open": [10.0],
            "high": [10.0],
            "low": [10.0],
            "close": [10.0],
        }
    )
    underlying = pd.DataFrame(
        {
            "timestamp": ["2024-01-01T09:16:00"],
            "open": [100.0],
            "high": [100.0],
            "low": [100.0],
            "close": [100.0],
        }
    )
    option_bytes = io.BytesIO()
    underlying_bytes = io.BytesIO()
    option.to_parquet(option_bytes, index=False)
    underlying.to_parquet(underlying_bytes, index=False)
    with zipfile.ZipFile(root / "replay.zip", "w") as archive:
        archive.writestr(
            "20260709/options/NIFTY 31JUL2026 25000 CE.parquet",
            option_bytes.getvalue(),
        )
        archive.writestr(
            "20240101/underlying/NIFTY.parquet",
            underlying_bytes.getvalue(),
        )
        archive.writestr(
            "__MACOSX/20260709/options/._NIFTY 31JUL2026 25000 CE.parquet",
            b"appledouble-metadata-must-not-be-opened",
        )

    manifest = _manifest(tmp_path / "manifest.json", root)
    summary = build(
        machine_manifest=manifest,
        output_dir=tmp_path / "archive-evidence",
    )
    result = build_inventory(manifest)

    option_rows = [
        row
        for row in result["candidates"]
        if row.get("candidate_class") == "OPTION_CONTRACT_DATASET"
    ]
    assert [row["archive_member"] for row in option_rows] == [
        "20260709/options/NIFTY 31JUL2026 25000 CE.parquet"
    ]
    assert option_rows[0]["session_dates"] == ["2026-07-09"]
    assert result["valid_option_session_dates"] == ["2026-07-09"]
    assert result["zip_members_inspected"] == 3
    assert summary["primary_oracle_agreement"] == "AGREEMENT"
    assert summary["strategy_development_authorized"] is False


def test_build_requires_primary_oracle_agreement_and_no_go(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    pd.DataFrame(
        {
            "ts": [1_784_006_404.0],
            "instrument_key": ["NSE_FO|1"],
            "bid_price": [9.9],
            "ask_price": [10.1],
        }
    ).to_parquet(root / "option_ticks.parquet")

    summary = build(
        machine_manifest=_manifest(tmp_path / "manifest.json", root),
        output_dir=tmp_path / "out",
    )

    assert summary["primary_oracle_agreement"] == "AGREEMENT"
    assert summary["strategy_development_authorized"] is False
    assert summary["candidate_limit"] is None
    assert summary["next_gate"] == "LOCAL_EXTERNAL_ROOT_EXECUTION_REQUIRED"


def test_committed_tracked_archive_evidence_is_hash_bound_and_no_go() -> None:
    evidence = Path(
        "research/option_e2e_recertification_v4/ce_pe_history_inventory_v1/"
        "tracked_replay_archive_option_history_compact_v1.json"
    )
    sidecar = evidence.with_suffix(evidence.suffix + ".sha256")
    expected_sha256, expected_name = sidecar.read_text(encoding="utf-8").split()

    assert expected_name == evidence.name
    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == expected_sha256

    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["source_archive_sha256"] == (
        "4357f109ed631802b3774c34db9c318f71742f8e99de307408af71bf00810707"
    )
    assert payload["source_full_audit_sha256"] == (
        "f9c4d7b92deb45bae64fb3b9bc3eabdfef516864a9eb6988c5a5042fc65aa2d9"
    )
    assert payload["option_member_count"] == 126
    assert payload["option_session_directories"] == ["20260709"]
    assert payload["option_type_counts"] == {"CE": 63, "PE": 63}
    assert payload["underlying_counts"] == {
        "BANKNIFTY": 42,
        "NIFTY": 42,
        "SENSEX": 42,
    }
    assert payload["chronological_coverage_verdict"] == "ONE_SESSION_SMOKE_ONLY"
    assert payload["development_validation_holdout_authorized"] is False
    assert payload["outcomes_read"] is False
    assert payload["pnl_read"] is False
    assert payload["holdout_outcomes_read"] is False
