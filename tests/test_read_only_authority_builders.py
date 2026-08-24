import json

import pytest

from core.read_only_instrument_authority import build_instrument_authority
from core.read_only_launch_plan import build_current_launch_plan


def _rows():
    return [
        {"name": "NIFTY", "exchange": "NSE", "instrument_token": 1},
        {"name": "BANKNIFTY", "exchange": "NSE", "instrument_token": 2},
        {"name": "NIFTY26AUG25000CE", "exchange": "NFO", "instrument_token": 3, "expiry": "2026-08-27", "strike": 25000, "instrument_type": "CE"},
    ]


def test_current_instrument_authority_is_session_and_source_bound(tmp_path):
    manifest = build_instrument_authority(rows=_rows(), session_date="2026-08-24", source_sha="a" * 40, output_root=tmp_path)
    assert manifest["verdict"] == "PASS"
    assert manifest["broker_write_authority"] is False
    assert manifest["raw_instrument_sha256"]
    assert json.loads((tmp_path / "instrument_authority_manifest.json").read_text())["session_date"] == "2026-08-24"


def test_launch_plan_rejects_stale_authority(tmp_path):
    manifest = build_instrument_authority(rows=_rows(), session_date="2026-08-24", source_sha="a" * 40, output_root=tmp_path)
    with pytest.raises(ValueError, match="authority_mismatch"):
        build_current_launch_plan(
            session_id="s1", session_date="2026-08-25", source_sha="a" * 40,
            runtime_root=tmp_path, instrument_manifest=manifest, subscription_tokens=[1],
            consumer_registry_path=str(tmp_path / "CONSUMERS.json"),
        )


def test_launch_plan_derives_tokens_and_preserves_safety(tmp_path):
    manifest = build_instrument_authority(rows=_rows(), session_date="2026-08-24", source_sha="a" * 40, output_root=tmp_path)
    plan = build_current_launch_plan(
        session_id="s1", session_date="2026-08-24", source_sha="a" * 40,
        runtime_root=tmp_path, instrument_manifest=manifest, subscription_tokens=[2, 1, 2],
        consumer_registry_path=str(tmp_path / "CONSUMERS.json"),
    )
    assert plan["subscription_tokens"] == [1, 2]
    assert plan["subscription_count"] == 2
    assert plan["execution_status"] == "advisory_only"
    assert plan["order_authority"] is False
