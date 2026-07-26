from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd

from research.option_e2e_recertification_v4.ce_pe_history_inventory_v1 import oracle


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

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
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
    monkeypatch.setattr(oracle, "MAX_ZIP_PARQUET_MEMBER_BYTES", 1)

    result = oracle.oracle_inventory(manifest)

    assert result["oversized_option_members_not_opened"] == 1
    assert result["candidate_ids"] == []
    assert result["parquet_metadata_inspected"] == 0
    assert result["outcomes_read"] is False
    assert result["pnl_read"] is False
    assert result["holdout_outcomes_read"] is False
