from __future__ import annotations


def test_annotate_iv_oi_tolerates_none_changes(monkeypatch):
    import core.option_chain as oc

    # Minimal row that exercises the OI/price-change comparisons.
    chain = [
        {
            "instrument_token": 111,
            "iv": None,
            "oi": None,
            "ltp": None,
            "days_to_expiry": 1,
            "type": "CE",
        }
    ]
    out = oc._annotate_iv_oi(chain)
    assert isinstance(out, list)
    assert out[0].get("oi_build") in {"FLAT", "LONG", "SHORT", "SHORT_COVER", "LONG_LIQ"}

