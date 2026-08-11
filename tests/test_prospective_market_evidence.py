from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import json
import pytest

from core.prospective_market_evidence import finalize_session

IST = ZoneInfo("Asia/Kolkata")
D = date(2026, 8, 11)


def bars(symbol, n=375, *, source_type="live_websocket", session_id="live-1", replay=False):
    start = datetime(2026, 8, 11, 9, 15, tzinfo=IST)
    out = []
    for i in range(n):
        px = 24000.0 + i / 10
        out.append({
            "ts": start + timedelta(minutes=i), "open": px, "high": px + 1,
            "low": px - 1, "close": px + .25, "volume": 0,
            "bar_provenance": {
                "source_type": source_type, "live_feed_session_id": session_id,
                "historical_seed": False, "replay_fixture": replay,
                "non_live_fallback": False, "recovered_synthetic": False,
            },
        })
    return out


def good():
    return {s: bars(s) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}


def test_seals_complete_live_session_and_volume_stays_missing(tmp_path):
    result = finalize_session(session_date=D, bars_by_symbol=good(), output_root=tmp_path)
    assert result["status"] == "SEALED"
    payload = json.loads((tmp_path / "2026-08-11.json").read_text())
    assert payload["broker_write_authority"] is False
    assert payload["order_authority"] is False
    assert payload["indices"]["NIFTY"]["volume"] is None
    assert payload["indices"]["NIFTY"]["volume_status"] == "MISSING_NOT_ZERO"


def test_feed_stop_at_1400_is_rejected(tmp_path):
    partial = {s: bars(s, 285) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}
    with pytest.raises(ValueError, match="SESSION_INCOMPLETE"):
        finalize_session(session_date=D, bars_by_symbol=partial, output_root=tmp_path)


def test_missing_index_rejected(tmp_path):
    x = good(); x.pop("SENSEX")
    with pytest.raises(ValueError, match="SESSION_INCOMPLETE:SENSEX"):
        finalize_session(session_date=D, bars_by_symbol=x, output_root=tmp_path)


def test_duplicate_or_nonmonotonic_rejected(tmp_path):
    x = good(); x["NIFTY"][1]["ts"] = x["NIFTY"][0]["ts"]
    with pytest.raises(ValueError, match="TIMESTAMP_ORDER_INVALID"):
        finalize_session(session_date=D, bars_by_symbol=x, output_root=tmp_path)


def test_replay_and_historical_seed_cannot_certify_live(tmp_path):
    x = good(); x["NIFTY"] = bars("NIFTY", replay=True)
    with pytest.raises(ValueError, match="NON_LIVE_PROVENANCE"):
        finalize_session(session_date=D, bars_by_symbol=x, output_root=tmp_path)
    x = good(); x["NIFTY"][0]["bar_provenance"]["historical_seed"] = True
    with pytest.raises(ValueError, match="NON_LIVE_PROVENANCE"):
        finalize_session(session_date=D, bars_by_symbol=x, output_root=tmp_path)


def test_cross_symbol_session_conflict_rejected(tmp_path):
    x = good(); x["SENSEX"] = bars("SENSEX", session_id="other")
    with pytest.raises(ValueError, match="CROSS_SYMBOL_SESSION_ID_CONFLICT"):
        finalize_session(session_date=D, bars_by_symbol=x, output_root=tmp_path)


def test_immutable_conflict_and_identical_idempotency(tmp_path):
    x = good()
    first = finalize_session(session_date=D, bars_by_symbol=x, output_root=tmp_path)
    assert first["status"] == "SEALED"
    second = finalize_session(session_date=D, bars_by_symbol=x, output_root=tmp_path)
    assert second["status"] == "IDEMPOTENT"
    payload = json.loads((tmp_path / "2026-08-11.json").read_text())
    payload["semantic_sha256"] = "tampered"
    (tmp_path / "2026-08-11.json").write_text(json.dumps(payload))
    with pytest.raises(FileExistsError, match="IMMUTABLE_EVIDENCE_CONFLICT"):
        finalize_session(session_date=D, bars_by_symbol=x, output_root=tmp_path)


def test_future_day_bars_do_not_substitute_for_target(tmp_path):
    x = good()
    for s in x:
        x[s] = [{**b, "ts": b["ts"] + timedelta(days=1)} for b in x[s]]
    with pytest.raises(ValueError, match="SESSION_INCOMPLETE"):
        finalize_session(session_date=D, bars_by_symbol=x, output_root=tmp_path)
