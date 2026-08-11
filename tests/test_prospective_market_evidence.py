from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import inspect
import json

import pytest

import core.prospective_market_evidence as pme
from core.ohlc_buffer import OhlcBuffer
from core.prospective_market_evidence import finalize_session

IST = ZoneInfo("Asia/Kolkata")
D = date(2026, 8, 11)


def bars(
    symbol,
    n=375,
    *,
    source_type="live_websocket",
    session_id="live-1",
    replay=False,
    fallback=False,
    synthetic=False,
    provider="kite",
    instrument_token=None,
):
    start = datetime(2026, 8, 11, 9, 15, tzinfo=IST)
    token = instrument_token or {
        "NIFTY": 256265,
        "BANKNIFTY": 260105,
        "SENSEX": 265,
    }.get(symbol, 1)
    out = []
    for i in range(n):
        px = 24000.0 + i / 10
        out.append(
            {
                "ts": start + timedelta(minutes=i),
                "open": px,
                "high": px + 1,
                "low": px - 1,
                "close": px + 0.25,
                # Index volume may be represented as zero upstream; the evidence
                # finalizer must not claim that as genuine observed volume.
                "volume": 0,
                "bar_provenance": {
                    "source_type": source_type,
                    "live_feed_session_id": session_id,
                    "provider": provider,
                    "token_domain": "kite_instrument_token",
                    "symbol": symbol,
                    "instrument_token": token,
                    "historical_seed": False,
                    "replay_fixture": replay,
                    "non_live_fallback": fallback,
                    "recovered_synthetic": synthetic,
                },
            }
        )
    return out


def good():
    return {s: bars(s) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}


def test_seals_complete_live_session_and_volume_stays_missing(tmp_path):
    result = finalize_session(
        session_date=D,
        bars_by_symbol=good(),
        output_root=tmp_path,
        code_sha="candidate-sha",
    )
    assert result["status"] == "SEALED"
    payload = json.loads((tmp_path / "2026-08-11.json").read_text())
    assert payload["broker_write_authority"] is False
    assert payload["order_authority"] is False
    assert payload["paper_authorized"] is False
    assert payload["live_authorized"] is False
    assert payload["code_sha"] == "candidate-sha"
    assert payload["indices"]["NIFTY"]["volume"] is None
    assert payload["indices"]["NIFTY"]["volume_status"] == "MISSING_NOT_ZERO"
    assert payload["indices"]["BANKNIFTY"]["minute_bars"] == 375
    assert payload["indices"]["SENSEX"]["source_identity"]["provider"] == "kite"


def test_feed_stop_at_1400_is_rejected(tmp_path):
    partial = {s: bars(s, 285) for s in ("NIFTY", "BANKNIFTY", "SENSEX")}
    with pytest.raises(ValueError, match="SESSION_INCOMPLETE"):
        finalize_session(session_date=D, bars_by_symbol=partial, output_root=tmp_path)


@pytest.mark.parametrize("missing", ["NIFTY", "BANKNIFTY", "SENSEX"])
def test_each_missing_index_is_rejected(tmp_path, missing):
    candidate = good()
    candidate.pop(missing)
    with pytest.raises(ValueError, match=f"SESSION_INCOMPLETE:{missing}"):
        finalize_session(session_date=D, bars_by_symbol=candidate, output_root=tmp_path)


def test_duplicate_and_nonmonotonic_bars_are_rejected(tmp_path):
    duplicate = good()
    duplicate["NIFTY"][1]["ts"] = duplicate["NIFTY"][0]["ts"]
    with pytest.raises(ValueError, match="TIMESTAMP_ORDER_INVALID"):
        finalize_session(session_date=D, bars_by_symbol=duplicate, output_root=tmp_path)

    nonmonotonic = good()
    nonmonotonic["NIFTY"][10], nonmonotonic["NIFTY"][11] = (
        nonmonotonic["NIFTY"][11],
        nonmonotonic["NIFTY"][10],
    )
    with pytest.raises(ValueError, match="TIMESTAMP_ORDER_INVALID"):
        finalize_session(session_date=D, bars_by_symbol=nonmonotonic, output_root=tmp_path)


def test_gap_is_rejected_even_when_bar_count_is_375(tmp_path):
    candidate = good()
    for bar in candidate["BANKNIFTY"][120:]:
        bar["ts"] += timedelta(minutes=1)
    with pytest.raises(ValueError, match="SESSION_BOUNDARY_INVALID|SESSION_GAP"):
        finalize_session(session_date=D, bars_by_symbol=candidate, output_root=tmp_path)


def test_invalid_ohlc_and_nonfinite_values_are_rejected(tmp_path):
    candidate = good()
    candidate["SENSEX"][20]["high"] = candidate["SENSEX"][20]["low"] - 1
    with pytest.raises(ValueError, match="OHLC_INVALID"):
        finalize_session(session_date=D, bars_by_symbol=candidate, output_root=tmp_path)

    candidate = good()
    candidate["NIFTY"][20]["close"] = float("nan")
    with pytest.raises(ValueError, match="OHLC_INVALID"):
        finalize_session(session_date=D, bars_by_symbol=candidate, output_root=tmp_path)


def test_future_timestamp_cannot_be_hidden_by_target_date_filter(tmp_path):
    candidate = good()
    candidate["NIFTY"].append({**candidate["NIFTY"][-1], "ts": candidate["NIFTY"][-1]["ts"] + timedelta(days=1)})
    with pytest.raises(ValueError, match="FUTURE_BAR_PRESENT"):
        finalize_session(session_date=D, bars_by_symbol=candidate, output_root=tmp_path)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"replay": True},
        {"fallback": True},
        {"synthetic": True},
        {"source_type": "historical_seed"},
    ],
)
def test_replay_fallback_synthetic_and_seed_cannot_certify_live(tmp_path, kwargs):
    candidate = good()
    candidate["NIFTY"] = bars("NIFTY", **kwargs)
    with pytest.raises(ValueError, match="NON_LIVE_PROVENANCE|LIVE_PROVENANCE_INCOMPLETE"):
        finalize_session(session_date=D, bars_by_symbol=candidate, output_root=tmp_path)


def test_cross_symbol_session_conflict_rejected(tmp_path):
    candidate = good()
    candidate["SENSEX"] = bars("SENSEX", session_id="other")
    with pytest.raises(ValueError, match="CROSS_SYMBOL_SESSION_ID_CONFLICT"):
        finalize_session(session_date=D, bars_by_symbol=candidate, output_root=tmp_path)


def test_source_identity_conflicts_are_rejected(tmp_path):
    candidate = good()
    candidate["NIFTY"][200]["bar_provenance"]["instrument_token"] = 999999
    with pytest.raises(ValueError, match="SOURCE_IDENTITY_MISMATCH:NIFTY:instrument_token"):
        finalize_session(session_date=D, bars_by_symbol=candidate, output_root=tmp_path)

    candidate = good()
    candidate["SENSEX"] = bars("SENSEX", provider="other-provider")
    with pytest.raises(ValueError, match="CROSS_SYMBOL_PROVIDER_CONFLICT"):
        finalize_session(session_date=D, bars_by_symbol=candidate, output_root=tmp_path)


def test_declared_symbol_mismatch_is_rejected(tmp_path):
    candidate = good()
    candidate["BANKNIFTY"][0]["bar_provenance"]["symbol"] = "NIFTY"
    with pytest.raises(ValueError, match="SOURCE_IDENTITY_MISMATCH:BANKNIFTY:symbol"):
        finalize_session(session_date=D, bars_by_symbol=candidate, output_root=tmp_path)


def test_immutable_conflict_identical_idempotency_and_tamper_detection(tmp_path):
    candidate = good()
    first = finalize_session(
        session_date=D,
        bars_by_symbol=candidate,
        output_root=tmp_path,
        code_sha="sha-a",
    )
    assert first["status"] == "SEALED"
    second = finalize_session(
        session_date=D,
        bars_by_symbol=candidate,
        output_root=tmp_path,
        code_sha="sha-a",
    )
    assert second["status"] == "IDEMPOTENT"

    path = tmp_path / "2026-08-11.json"
    payload = json.loads(path.read_text())
    payload["indices"]["NIFTY"]["close"] += 100
    # Keep the old claimed semantic hash to simulate an overwrite/tamper attempt.
    path.write_text(json.dumps(payload))
    with pytest.raises(FileExistsError, match="IMMUTABLE_EVIDENCE_CONFLICT"):
        finalize_session(
            session_date=D,
            bars_by_symbol=candidate,
            output_root=tmp_path,
            code_sha="sha-a",
        )


def test_code_sha_change_for_same_session_is_not_idempotent(tmp_path):
    candidate = good()
    finalize_session(
        session_date=D,
        bars_by_symbol=candidate,
        output_root=tmp_path,
        code_sha="sha-a",
    )
    with pytest.raises(FileExistsError, match="IMMUTABLE_EVIDENCE_CONFLICT"):
        finalize_session(
            session_date=D,
            bars_by_symbol=candidate,
            output_root=tmp_path,
            code_sha="sha-b",
        )


def test_safe_wrapper_contains_sidecar_failure(monkeypatch, tmp_path):
    def explode(**_kwargs):
        raise RuntimeError("sidecar failed")

    monkeypatch.setattr(pme, "finalize_session", explode)
    result = pme.safe_finalize_live_session(session_date=D, output_root=tmp_path)
    assert result["status"] == "NOT_SEALED"
    assert result["broker_write_authority"] is False
    assert result["order_authority"] is False
    assert result["paper_authorized"] is False
    assert result["live_authorized"] is False


def test_runtime_module_has_no_order_action_boundary_calls():
    text = inspect.getsource(pme)
    restricted = [
        "place" + "_order",
        "modify" + "_order",
        "cancel" + "_order",
        "exit" + "_order",
        "execution" + "_router",
        "Trade" + "Builder",
    ]
    assert not [marker for marker in restricted if marker in text]


def test_replay_style_buffer_integration_preserves_provenance_and_seals(tmp_path):
    buffers = {symbol: OhlcBuffer() for symbol in ("NIFTY", "BANKNIFTY", "SENSEX")}
    source = good()
    for symbol, buffer in buffers.items():
        for bar in source[symbol]:
            result = buffer.update_tick(
                symbol,
                bar["close"],
                volume=None,
                ts=bar["ts"],
                provenance=bar["bar_provenance"],
            )
            assert result["accepted"] is True
    assembled = {symbol: buffer.get_bars(symbol) for symbol, buffer in buffers.items()}
    result = finalize_session(
        session_date=D,
        bars_by_symbol=assembled,
        output_root=tmp_path,
        code_sha="integration-sha",
    )
    assert result["status"] == "SEALED"
