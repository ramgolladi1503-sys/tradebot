from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd

from research.option_e2e_recertification_v4.ce_pe_history_inventory_v1 import oracle
from research.option_e2e_recertification_v4.ce_pe_history_inventory_v1.build_inventory import (
    build,
)


def _manifest(path: Path, root: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "roots": [
                    {
                        "current_root_id": "ROOT",
                        "absolute_path": str(root),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_oracle_does_not_open_oversized_option_archive_member(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    parquet_bytes = io.BytesIO()
    pd.DataFrame(
        {
            "timestamp": ["2026-07-09T09:16:00"],
            "open": [10.0],
            "high": [10.0],
            "low": [10.0],
            "close": [10.0],
        }
    ).to_parquet(parquet_bytes, index=False)
    with zipfile.ZipFile(root / "replay.zip", "w") as archive:
        archive.writestr(
            "20260709/options/NIFTY 31JUL2026 25000 CE.parquet",
            parquet_bytes.getvalue(),
        )

    manifest = _manifest(tmp_path / "manifest.json", root)
    monkeypatch.setattr(oracle, "MAX_ZIP_PARQUET_MEMBER_BYTES", 1)

    result = oracle.oracle_inventory(manifest)

    assert result["oversized_option_members_not_opened"] == 1
    assert result["candidate_ids"] == []
    assert result["parquet_metadata_inspected"] == 0
    assert result["outcomes_read"] is False
    assert result["pnl_read"] is False
    assert result["holdout_outcomes_read"] is False


def test_multi_date_parquet_does_not_become_one_path_hint_session(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root" / "20260714"
    root.mkdir(parents=True)
    pd.DataFrame(
        {
            "ts": [1_783_555_200.0, 1_783_641_600.0],
            "instrument_key": ["NSE_FO|1", "NSE_FO|1"],
            "bid_price": [9.9, 10.0],
            "ask_price": [10.1, 10.2],
        }
    ).to_parquet(root / "multi_date_option_ticks.parquet", index=False)

    summary = build(
        machine_manifest=_manifest(tmp_path / "manifest.json", root.parent),
        output_dir=tmp_path / "out",
    )
    primary = json.loads(
        (tmp_path / "out" / "ce_pe_history_inventory.json").read_text(
            encoding="utf-8"
        )
    )
    candidate = next(
        row
        for row in primary["candidates"]
        if row.get("candidate_class") == "RAW_OPTION_TICK_DATASET"
    )

    assert summary["primary_oracle_agreement"] == "AGREEMENT"
    assert summary["valid_option_session_dates"] == []
    assert summary["chronological_coverage_verdict"] == "NO_VALID_OPTION_SESSIONS"
    assert candidate["session_dates"] == []
    assert (
        candidate["session_date_evidence"]
        == "MULTI_DATE_FOOTER_REQUIRES_DEEP_REVIEW"
    )
    assert summary["strategy_development_authorized"] is False
