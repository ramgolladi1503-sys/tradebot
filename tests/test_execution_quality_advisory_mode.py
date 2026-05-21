from __future__ import annotations

from core.execution_quality import evaluate_pretrade_execution_quality


def test_execution_quality_blocks_advisory_in_sim():
    candidate = {
        "execution_entry": 100.0,
        "entry_price": 101.0,
        "execution_entry_status": "non_executable",
        "quote_ok": True,
        "source_flags": {
            "execution_block_type": "advisory",
            "runtime_mode": "SIM",
        },
    }
    quality = evaluate_pretrade_execution_quality(candidate)
    assert quality.execution_ok is False
    assert quality.order_policy == "advisory"
    assert quality.reason_code == "degraded_data"


def test_execution_quality_blocks_advisory_in_live():
    candidate = {
        "execution_entry": None,
        "execution_entry_status": "non_executable",
        "quote_ok": True,
        "source_flags": {
            "execution_block_type": "advisory",
            "runtime_mode": "LIVE",
        },
    }
    quality = evaluate_pretrade_execution_quality(candidate)
    assert quality.execution_ok is False
    assert quality.order_policy == "advisory"
    assert quality.reason_code == "data_not_live"
