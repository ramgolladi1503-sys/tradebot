from __future__ import annotations

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

    result = build_inventory(_manifest(tmp_path / "manifest.json", root))

    option_rows = [
        row
        for row in result["candidates"]
        if row.get("candidate_class") == "OPTION_CONTRACT_DATASET"
    ]
    assert len(option_rows) == 1
    assert option_rows[0]["session_dates"] == ["2026-07-09"]
    assert result["valid_option_session_dates"] == ["2026-07-09"]
    assert result["zip_members_inspected"] == 2


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
