from __future__ import annotations

from core.fallback_lineage import stamp_fallback_lineage


def test_lineage_helper_marks_spread_and_liquidity_defaults():
    row = stamp_fallback_lineage(
        {
            "trade_id": "T-LINEAGE",
            "phase2_spread_fallback_used": True,
            "phase2_liquidity_fallback_used": True,
            "quote_source": "live_broker",
        }
    )

    assert "spread_pct" in row["fallback_fields"]
    assert "liquidity_score" in row["fallback_fields"]
    assert row["spread_lineage"] == "FALLBACK_DEFAULT"
    assert row["liquidity_lineage"] == "FALLBACK_DEFAULT"
    assert row["data_lineage"]["spread"] == "FALLBACK_DEFAULT"
    assert row["data_lineage"]["liquidity"] == "FALLBACK_DEFAULT"


def test_lineage_helper_marks_unknown_quote_source():
    row = stamp_fallback_lineage({"quote_source": "unknown"})

    assert row["price_lineage"] == "UNKNOWN"
    assert row["data_lineage"]["ltp"] == "UNKNOWN"


def test_lineage_helper_marks_recovered_entry_source():
    row = stamp_fallback_lineage({"execution_entry_source": "recovered_fallback"})

    assert "execution_entry" in row["fallback_fields"]
    assert row["execution_entry_lineage"] == "RECOVERED_FALLBACK"
    assert row["data_lineage"]["execution_entry"] == "RECOVERED_FALLBACK"


def test_lineage_helper_dedupes_existing_fields():
    row = stamp_fallback_lineage(
        {
            "fallback_fields": ["spread_pct"],
            "phase2_spread_fallback_used": True,
        }
    )

    assert row["fallback_fields"].count("spread_pct") == 1
