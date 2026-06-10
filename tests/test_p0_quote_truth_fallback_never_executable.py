"""P0 regression: RECOVERED_FALLBACK and all FALLBACK_QUOTE_SOURCES members
must never produce execution_eligible=True.

Gap closed: GAP-02 from qa-coverage-gaps-20260610.md

Invariant under test:
  For every source in FALLBACK_QUOTE_SOURCES:
    classify_quote_truth(payload).execution_eligible  == False
    classify_quote_truth(payload).rank_eligible       == False
    classify_quote_truth(payload).source_trust        == "fallback"
    QUOTE_SOURCE_FALLBACK_REASON in classify_quote_truth(payload).reasons

  Additionally tests:
  - quote_source absent / None still blocks when option_ltp_source is fallback
  - RECOVERED_FALLBACK specifically (the highest-profile source from audit)

No production code is modified by this file.
"""
from __future__ import annotations

import pytest

from core.quote_truth import (
    FALLBACK_QUOTE_SOURCES,
    QUOTE_SOURCE_FALLBACK_REASON,
    classify_quote_truth,
)


# ---------------------------------------------------------------------------
# Shared fixture helpers – mirrors test_edge42_quote_truth_contract.py pattern
# ---------------------------------------------------------------------------

def _candidate(**overrides):
    payload = {
        "candidate_class": "EXECUTABLE",
        "execution_entry_status": "executable",
        "instrument_token": 12345,
        "quote_source": "live",
        "option_ltp_source": "live",
        "current_ltp": 100.0,
        "best_bid": 99.5,
        "best_ask": 100.5,
        "quote_ts_epoch": 1_700_000_000.0,
        "ts_epoch": 1_700_000_001.0,
        "quote_age_sec": 1.0,
        "ltp_age_sec": 1.0,
        "bid_age_sec": 1.0,
        "ask_age_sec": 1.0,
        "chain_snapshot_age_sec": 1.0,
        "market_mode": "LIVE",
        "spread_ok": True,
        "liquidity_ok": True,
        "data_confidence": 0.9,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# P0 — RECOVERED_FALLBACK specifically (highest-profile source from audit)
# ---------------------------------------------------------------------------

def test_recovered_fallback_quote_source_is_never_execution_eligible():
    """
    A candidate whose quote_source is RECOVERED_FALLBACK must be classified as
    source_trust='fallback' and must have execution_eligible=False.

    This is the primary audit gap: the condition depends on reasons being
    non-empty (execution_eligible = truth_ok AND source_trust in trusted set).
    Verifying both fields explicitly proves the entire chain is correct.
    """
    decision = classify_quote_truth(
        _candidate(
            quote_source="RECOVERED_FALLBACK",
            option_ltp_source="RECOVERED_FALLBACK",
        ),
        require_source=True,
    )

    assert decision.execution_eligible is False, (
        "RECOVERED_FALLBACK source must never be execution_eligible"
    )
    assert decision.rank_eligible is False, (
        "RECOVERED_FALLBACK source must never be rank_eligible"
    )
    assert decision.truth_ok is False, (
        "RECOVERED_FALLBACK source must produce truth_ok=False"
    )
    assert decision.source_trust == "fallback"
    assert QUOTE_SOURCE_FALLBACK_REASON in decision.reasons


def test_recovered_fallback_blocks_without_require_source():
    """
    Even without require_source=True, RECOVERED_FALLBACK is in
    FALLBACK_QUOTE_SOURCES and the source_trust path must still fire,
    producing execution_eligible=False.
    """
    decision = classify_quote_truth(
        _candidate(
            quote_source="RECOVERED_FALLBACK",
            option_ltp_source="RECOVERED_FALLBACK",
        ),
        require_source=False,
    )

    assert decision.execution_eligible is False
    assert decision.source_trust == "fallback"
    assert QUOTE_SOURCE_FALLBACK_REASON in decision.reasons


# ---------------------------------------------------------------------------
# P0 — Parametrized: every FALLBACK_QUOTE_SOURCES member must block
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source", sorted(FALLBACK_QUOTE_SOURCES))
def test_every_fallback_quote_source_member_blocks_execution(source):
    """
    Parametrized across all 8 members of FALLBACK_QUOTE_SOURCES.
    Each must produce:
      - execution_eligible = False
      - rank_eligible      = False
      - source_trust       = "fallback"
      - QUOTE_SOURCE_FALLBACK_REASON in reasons

    This catches the regression where a new source added to the set is not
    handled by the _source_trust() function.
    """
    decision = classify_quote_truth(
        _candidate(quote_source=source, option_ltp_source=source),
        require_source=True,
    )

    assert decision.execution_eligible is False, (
        f"fallback source {source!r} must not be execution_eligible"
    )
    assert decision.rank_eligible is False, (
        f"fallback source {source!r} must not be rank_eligible"
    )
    assert decision.source_trust == "fallback", (
        f"fallback source {source!r} must produce source_trust='fallback'"
    )
    assert QUOTE_SOURCE_FALLBACK_REASON in decision.reasons, (
        f"fallback source {source!r} must append QUOTE_SOURCE_FALLBACK_REASON to reasons"
    )


# ---------------------------------------------------------------------------
# P0 — Edge case: quote_source=None but option_ltp_source is fallback
# ---------------------------------------------------------------------------

def test_fallback_option_ltp_source_blocks_when_quote_source_is_none():
    """
    If quote_source is absent but option_ltp_source is a fallback source,
    the source union (_all_sources) must still pick up the fallback tag.

    Regression: a caller constructs a payload from a dict that omits
    quote_source (e.g. from an older pipeline stage) but sets
    option_ltp_source = 'RECOVERED_FALLBACK'.
    """
    decision = classify_quote_truth(
        _candidate(quote_source=None, option_ltp_source="RECOVERED_FALLBACK"),
        require_source=False,
    )

    assert decision.execution_eligible is False
    assert decision.source_trust == "fallback"
    assert QUOTE_SOURCE_FALLBACK_REASON in decision.reasons


# ---------------------------------------------------------------------------
# P0 — Edge case: fallback sourced from nested source_flags, not top-level key
# ---------------------------------------------------------------------------

def test_fallback_source_in_nested_source_flags_blocks_execution():
    """
    Some candidates carry quote_truth inside source_flags rather than at the
    top level. The _source_flags() resolution must reach into this nested dict
    and still classify the source as fallback.
    """
    candidate = _candidate(
        quote_source=None,
        option_ltp_source=None,
        source_flags={
            "quote_truth": {
                "quote_source": "FALLBACK_RECOVERED",
                "option_ltp_source": "FALLBACK_RECOVERED",
            }
        },
    )

    decision = classify_quote_truth(candidate, require_source=False)

    assert decision.execution_eligible is False
    assert decision.source_trust == "fallback"
    assert QUOTE_SOURCE_FALLBACK_REASON in decision.reasons


# ---------------------------------------------------------------------------
# Baseline sanity: confirm live source passes — ensures parametrized test
# failure is due to fallback logic, not a broken fixture
# ---------------------------------------------------------------------------

def test_live_quote_source_remains_execution_eligible():
    """Confirms the fixture and module are correct when source is live."""
    decision = classify_quote_truth(
        _candidate(quote_source="LIVE", option_ltp_source="LIVE"),
        require_source=True,
    )

    assert decision.execution_eligible is True
    assert decision.source_trust == "trusted_live"
    assert QUOTE_SOURCE_FALLBACK_REASON not in decision.reasons
