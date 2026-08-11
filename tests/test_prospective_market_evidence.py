from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import inspect
import json

import pytest

import core.prospective_market_evidence as pme
from core.ohlc_buffer import OhlcBuffer

IST = ZoneInfo("Asia/Kolkata")
D = date(2026, 8, 11)
KEY = "test-attestation-key-32-bytes-minimum-0001"
ATTACKER_KEY = "attacker-selected-key-32-bytes-minimum-0002"
TOKENS = {"NIFTY": 256265, "BANKNIFTY": 260105, "SENSEX": 265}


@pytest.fixture(autouse=True)
def trusted_attestation_key(monkeypatch):
    monkeypatch.setenv("TRADEBOT_LIVE_SESSION_ATTESTATION_KEY", KEY)


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
    token = instrument_token or TOKENS[symbol]
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
    return {s: bars(s) for s in pme.REQUIRED}


def signed_attestation(
    *,
    code_sha="candidate-sha",
    key=KEY,
    session_id="live-1",
    attested_at="2026-08-11T15:31:00+05:30",
    tokens=None,
):
    token_map = tokens or TOKENS
    raw = {
        "schema": pme.ATTESTATION_SCHEMA,
        "source": pme.ATTESTATION_SOURCE,
        "status": "VERIFIED_LIVE_SESSION",
        "session_date": D.isoformat(),
        "attested_at_ist": attested_at,
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "live_feed_session_id": session_id,
        "code_sha": code_sha,
        "indices": {
            symbol: {"symbol": symbol, "instrument_token": token_map[symbol]}
            for symbol in pme.REQUIRED
        },
    }
    return pme.sign_live_session_attestation(raw, attestation_key=key)


def finalize(tmp_path, candidate=None, *, code_sha="candidate-sha", attestation=None):
    return pme.finalize_session(
        session_date=D,
        bars_by_symbol=candidate if candidate is not None else good(),
        output_root=tmp_path,
        code_sha=code_sha,
        live_attestation=attestation or signed_attestation(code_sha=code_sha),
    )


def test_seals_complete_attested_live_session_and_volume_stays_missing(tmp_path):
    result = finalize(tmp_path)
    assert result["status"] == "SEALED"
    payload = json.loads((tmp_path / "2026-08-11.json").read_text())
    assert payload["broker_write_authority"] is False
    assert payload["order_authority"] is False
    assert payload["paper_authorized"] is False
    assert payload["live_authorized"] is False
    assert payload["code_sha"] == "candidate-sha"
    assert payload["created_at_ist"] == "2026-08-11T15:31:00+05:30"
    assert payload["live_attestation_sha256"]
    assert payload["indices"]["NIFTY"]["volume"] is None
    assert payload["indices"]["NIFTY"]["volume_status"] == "MISSING_NOT_ZERO"
    assert payload["indices"]["SENSEX"]["source_identity"]["provider"] == "kite"


def test_self_declared_live_metadata_without_independent_attestation_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="LIVE_ATTESTATION_REQUIRED"):
        pme.finalize_session(
            session_date=D,
            bars_by_symbol=good(),
            output_root=tmp_path,
            code_sha="candidate-sha",
        )


def test_verification_key_is_not_a_finalize_session_caller_argument(tmp_path):
    with pytest.raises(TypeError, match="attestation_key"):
        pme.finalize_session(
            session_date=D,
            bars_by_symbol=good(),
            output_root=tmp_path,
            code_sha="candidate-sha",
            live_attestation=signed_attestation(),
            attestation_key=ATTACKER_KEY,
        )


def test_missing_trusted_verification_key_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("TRADEBOT_LIVE_SESSION_ATTESTATION_KEY", raising=False)
    with pytest.raises(ValueError, match="TRUSTED_LIVE_ATTESTATION_KEY_REQUIRED"):
        finalize(tmp_path)


def test_forged_or_attacker_selected_key_attestation_is_rejected(tmp_path):
    att = signed_attestation()
    att["live_feed_session_id"] = "forged-session"
    with pytest.raises(ValueError, match="LIVE_ATTESTATION_SIGNATURE_INVALID"):
        finalize(tmp_path, attestation=att)

    attacker_signed = signed_attestation(key=ATTACKER_KEY)
    with pytest.raises(ValueError, match="LIVE_ATTESTATION_SIGNATURE_INVALID"):
        finalize(tmp_path, attestation=attacker_signed)


def test_consistently_wrong_tokens_in_bars_and_signed_attestation_are_rejected(tmp_path):
    wrong_tokens = {"NIFTY": 999999, "BANKNIFTY": 888888, "SENSEX": 777777}
    candidate = {
        symbol: bars(symbol, instrument_token=wrong_tokens[symbol])
        for symbol in pme.REQUIRED
    }
    attestation = signed_attestation(tokens=wrong_tokens)
    with pytest.raises(ValueError, match="LIVE_ATTESTATION_INDEX_IDENTITY_INVALID"):
        finalize(tmp_path, candidate, attestation=attestation)


def test_future_attestation_timestamp_is_rejected_even_with_trusted_signature(tmp_path):
    attestation = signed_attestation(attested_at="2099-01-01T16:00:00+05:30")
    with pytest.raises(ValueError, match="LIVE_ATTESTATION_TIMESTAMP_INVALID"):
        finalize(tmp_path, attestation=attestation)


def test_attestation_from_different_calendar_date_is_rejected(tmp_path):
    attestation = signed_attestation(attested_at="2026-08-12T15:31:00+05:30")
    with pytest.raises(ValueError, match="LIVE_ATTESTATION_TIMESTAMP_INVALID"):
        finalize(tmp_path, attestation=attestation)


def test_feed_stop_at_1400_is_rejected(tmp_path):
    partial = {s: bars(s, 285) for s in pme.REQUIRED}
    with pytest.raises(ValueError, match="SESSION_INCOMPLETE"):
        finalize(tmp_path, partial)


@pytest.mark.parametrize("missing", pme.REQUIRED)
def test_each_missing_index_is_rejected(tmp_path, missing):
    candidate = good()
    candidate.pop(missing)
    with pytest.raises(ValueError, match=f"SESSION_INCOMPLETE:{missing}"):
        finalize(tmp_path, candidate)


def test_duplicate_and_nonmonotonic_bars_are_rejected(tmp_path):
    duplicate = good()
    duplicate["NIFTY"][1]["ts"] = duplicate["NIFTY"][0]["ts"]
    with pytest.raises(ValueError, match="TIMESTAMP_ORDER_INVALID"):
        finalize(tmp_path, duplicate)

    nonmonotonic = good()
    nonmonotonic["NIFTY"][10], nonmonotonic["NIFTY"][11] = (
        nonmonotonic["NIFTY"][11],
        nonmonotonic["NIFTY"][10],
    )
    with pytest.raises(ValueError, match="TIMESTAMP_ORDER_INVALID"):
        finalize(tmp_path, nonmonotonic)


def test_gap_is_rejected_even_when_bar_count_is_375(tmp_path):
    candidate = good()
    for bar in candidate["BANKNIFTY"][120:]:
        bar["ts"] += timedelta(minutes=1)
    with pytest.raises(ValueError, match="SESSION_BOUNDARY_INVALID|SESSION_GAP"):
        finalize(tmp_path, candidate)


def test_invalid_ohlc_and_nonfinite_values_are_rejected(tmp_path):
    candidate = good()
    candidate["SENSEX"][20]["high"] = candidate["SENSEX"][20]["low"] - 1
    with pytest.raises(ValueError, match="OHLC_INVALID"):
        finalize(tmp_path, candidate)

    candidate = good()
    candidate["NIFTY"][20]["close"] = float("nan")
    with pytest.raises(ValueError, match="OHLC_INVALID"):
        finalize(tmp_path, candidate)


def test_future_timestamp_cannot_be_hidden_by_target_date_filter(tmp_path):
    candidate = good()
    candidate["NIFTY"].append(
        {**candidate["NIFTY"][-1], "ts": candidate["NIFTY"][-1]["ts"] + timedelta(days=1)}
    )
    with pytest.raises(ValueError, match="FUTURE_BAR_PRESENT"):
        finalize(tmp_path, candidate)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"replay": True},
        {"fallback": True},
        {"synthetic": True},
        {"source_type": "historical_seed"},
    ],
)
def test_declared_replay_fallback_synthetic_and_seed_cannot_certify_live(tmp_path, kwargs):
    candidate = good()
    candidate["NIFTY"] = bars("NIFTY", **kwargs)
    with pytest.raises(ValueError, match="NON_LIVE_PROVENANCE|LIVE_PROVENANCE_INCOMPLETE"):
        finalize(tmp_path, candidate)


def test_missing_identity_on_one_bar_is_rejected_not_ignored(tmp_path):
    candidate = good()
    candidate["NIFTY"][100]["bar_provenance"].pop("instrument_token")
    with pytest.raises(ValueError, match="LIVE_PROVENANCE_INCOMPLETE:NIFTY:instrument_token"):
        finalize(tmp_path, candidate)


def test_stable_but_wrong_instrument_token_is_rejected_against_attestation(tmp_path):
    candidate = good()
    candidate["NIFTY"] = bars("NIFTY", instrument_token=999999)
    with pytest.raises(ValueError, match="SOURCE_IDENTITY_MISMATCH:NIFTY:instrument_token"):
        finalize(tmp_path, candidate)


def test_source_and_session_identity_conflicts_are_rejected(tmp_path):
    candidate = good()
    candidate["SENSEX"] = bars("SENSEX", provider="other-provider")
    with pytest.raises(ValueError, match="SOURCE_IDENTITY_MISMATCH:SENSEX:provider"):
        finalize(tmp_path, candidate)

    candidate = good()
    candidate["SENSEX"] = bars("SENSEX", session_id="other")
    with pytest.raises(ValueError, match="SOURCE_IDENTITY_MISMATCH:SENSEX:live_feed_session_id"):
        finalize(tmp_path, candidate)


def test_declared_symbol_mismatch_is_rejected(tmp_path):
    candidate = good()
    candidate["BANKNIFTY"][0]["bar_provenance"]["symbol"] = "NIFTY"
    with pytest.raises(ValueError, match="SOURCE_IDENTITY_MISMATCH:BANKNIFTY:symbol"):
        finalize(tmp_path, candidate)


def test_immutable_conflict_idempotency_and_payload_tamper_detection(tmp_path):
    candidate = good()
    first = finalize(tmp_path, candidate, code_sha="sha-a")
    assert first["status"] == "SEALED"
    second = finalize(tmp_path, candidate, code_sha="sha-a")
    assert second["status"] == "IDEMPOTENT"

    path = tmp_path / "2026-08-11.json"
    payload = json.loads(path.read_text())
    payload["indices"]["NIFTY"]["close"] += 100
    path.write_text(json.dumps(payload))
    with pytest.raises(FileExistsError, match="IMMUTABLE_EVIDENCE_CONFLICT"):
        finalize(tmp_path, candidate, code_sha="sha-a")


def test_created_at_tamper_is_detected(tmp_path):
    candidate = good()
    finalize(tmp_path, candidate, code_sha="sha-a")
    path = tmp_path / "2026-08-11.json"
    payload = json.loads(path.read_text())
    payload["created_at_ist"] = "2026-08-11T16:45:00+05:30"
    path.write_text(json.dumps(payload))
    with pytest.raises(FileExistsError, match="IMMUTABLE_EVIDENCE_CONFLICT"):
        finalize(tmp_path, candidate, code_sha="sha-a")


def test_code_sha_change_for_same_session_is_not_idempotent(tmp_path):
    candidate = good()
    finalize(tmp_path, candidate, code_sha="sha-a")
    with pytest.raises(FileExistsError, match="IMMUTABLE_EVIDENCE_CONFLICT"):
        finalize(tmp_path, candidate, code_sha="sha-b")


def test_safe_wrapper_fails_closed_without_attestation(monkeypatch, tmp_path):
    monkeypatch.delenv("TRADEBOT_LIVE_SESSION_ATTESTATION_PATH", raising=False)
    result = pme.safe_finalize_live_session(session_date=D, output_root=tmp_path)
    assert result["status"] == "NOT_SEALED"
    assert "LIVE_ATTESTATION_PATH_REQUIRED" in result["reason"]
    assert result["broker_write_authority"] is False
    assert result["order_authority"] is False
    assert result["paper_authorized"] is False
    assert result["live_authorized"] is False


def test_safe_wrapper_fails_closed_without_trusted_key(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADEBOT_LIVE_SESSION_ATTESTATION_PATH", "ignored.json")
    monkeypatch.delenv("TRADEBOT_LIVE_SESSION_ATTESTATION_KEY", raising=False)
    result = pme.safe_finalize_live_session(session_date=D, output_root=tmp_path)
    assert result["status"] == "NOT_SEALED"
    assert "TRUSTED_LIVE_ATTESTATION_KEY_REQUIRED" in result["reason"]


def test_safe_wrapper_contains_sidecar_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADEBOT_LIVE_SESSION_ATTESTATION_PATH", "ignored.json")
    monkeypatch.setenv("TRADEBOT_CODE_SHA", "candidate-sha")
    monkeypatch.setattr(pme, "_load_runtime_attestation", lambda _path: signed_attestation())

    def explode(**_kwargs):
        raise RuntimeError("sidecar failed")

    monkeypatch.setattr(pme, "finalize_session", explode)
    result = pme.safe_finalize_live_session(session_date=D, output_root=tmp_path)
    assert result["status"] == "NOT_SEALED"
    assert "sidecar failed" in result["reason"]
    assert result["broker_write_authority"] is False
    assert result["order_authority"] is False


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


def test_buffer_integration_preserves_identity_but_still_requires_attestation(tmp_path):
    buffers = {symbol: OhlcBuffer() for symbol in pme.REQUIRED}
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

    with pytest.raises(ValueError, match="LIVE_ATTESTATION_REQUIRED"):
        pme.finalize_session(
            session_date=D,
            bars_by_symbol=assembled,
            output_root=tmp_path,
            code_sha="integration-sha",
        )

    result = finalize(tmp_path, assembled, code_sha="integration-sha")
    assert result["status"] == "SEALED"
