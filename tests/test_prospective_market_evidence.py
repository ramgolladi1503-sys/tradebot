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
SHA_A = "a" * 40
SHA_B = "b" * 40
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
    code_sha=SHA_A,
    key=KEY,
    session_id="live-1",
    attested_at="2026-08-11T15:31:00+05:30",
    tokens=None,
    bar_source=None,
):
    token_map = tokens or TOKENS
    digest_source = bar_source or good()
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
            symbol: {
                "symbol": symbol,
                "instrument_token": token_map[symbol],
                "bars_sha256": pme.bar_content_sha256(symbol, digest_source[symbol]),
            }
            for symbol in pme.REQUIRED
        },
    }
    return pme.sign_live_session_attestation(raw, attestation_key=key)


def finalize(tmp_path, candidate=None, *, code_sha=SHA_A, attestation=None):
    return pme.finalize_session(
        session_date=D,
        bars_by_symbol=candidate if candidate is not None else good(),
        output_root=tmp_path,
        code_sha=code_sha,
        live_attestation=attestation or signed_attestation(code_sha=code_sha),
    )


def test_seals_complete_attested_live_session_and_missing_volume(tmp_path):
    result = finalize(tmp_path)
    assert result["status"] == "SEALED"
    payload = json.loads((tmp_path / "2026-08-11.json").read_text())
    assert payload["broker_write_authority"] is False
    assert payload["order_authority"] is False
    assert payload["paper_authorized"] is False
    assert payload["live_authorized"] is False
    assert payload["code_sha"] == SHA_A
    assert payload["indices"]["NIFTY"]["volume"] is None
    assert payload["indices"]["NIFTY"]["volume_status"] == "MISSING_NOT_ZERO"
    assert payload["indices"]["NIFTY"]["bars_sha256"] == pme.bar_content_sha256("NIFTY", good()["NIFTY"])


def test_exact_git_sha_is_required(tmp_path):
    for invalid in (None, "", "UNKNOWN", "candidate-sha", "A" * 40, "a" * 39, "g" * 40):
        with pytest.raises(ValueError, match="CODE_SHA_EXACT_REQUIRED"):
            pme.finalize_session(
                session_date=D,
                bars_by_symbol=good(),
                output_root=tmp_path,
                code_sha=invalid,
                live_attestation=signed_attestation(),
            )


def test_attestation_requires_signed_bar_digest_for_every_index(tmp_path):
    raw = {
        "schema": pme.ATTESTATION_SCHEMA,
        "source": pme.ATTESTATION_SOURCE,
        "status": "VERIFIED_LIVE_SESSION",
        "session_date": D.isoformat(),
        "attested_at_ist": "2026-08-11T15:31:00+05:30",
        "provider": "kite",
        "token_domain": "kite_instrument_token",
        "live_feed_session_id": "live-1",
        "code_sha": SHA_A,
        "indices": {s: {"symbol": s, "instrument_token": TOKENS[s]} for s in pme.REQUIRED},
    }
    att = pme.sign_live_session_attestation(raw, attestation_key=KEY)
    with pytest.raises(ValueError, match="LIVE_ATTESTATION_BAR_DIGEST_INVALID:NIFTY"):
        finalize(tmp_path, attestation=att)


def test_valid_signed_attestation_cannot_be_reused_with_different_ohlc(tmp_path):
    original = good()
    attestation = signed_attestation(bar_source=original)
    substituted = good()
    substituted["NIFTY"][200]["close"] += 0.5
    # Keep OHLC geometry valid so the bar-content binding, not geometry, kills it.
    with pytest.raises(ValueError, match="LIVE_BAR_DIGEST_MISMATCH:NIFTY"):
        finalize(tmp_path, substituted, attestation=attestation)


def test_valid_signed_attestation_cannot_be_reused_with_relabelled_replay_content(tmp_path):
    original = good()
    attestation = signed_attestation(bar_source=original)
    substituted = good()
    # Simulate a different historical price stream relabelled with otherwise-valid
    # live provenance and timestamps.
    for bar in substituted["BANKNIFTY"]:
        for field in ("open", "high", "low", "close"):
            bar[field] += 50.0
    with pytest.raises(ValueError, match="LIVE_BAR_DIGEST_MISMATCH:BANKNIFTY"):
        finalize(tmp_path, substituted, attestation=attestation)


def test_forged_or_attacker_selected_key_is_rejected(tmp_path):
    att = signed_attestation()
    att["live_feed_session_id"] = "forged-session"
    with pytest.raises(ValueError, match="LIVE_ATTESTATION_SIGNATURE_INVALID"):
        finalize(tmp_path, attestation=att)
    with pytest.raises(ValueError, match="LIVE_ATTESTATION_SIGNATURE_INVALID"):
        finalize(tmp_path, attestation=signed_attestation(key=ATTACKER_KEY))


def test_self_declared_metadata_without_attestation_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="LIVE_ATTESTATION_REQUIRED"):
        pme.finalize_session(
            session_date=D, bars_by_symbol=good(), output_root=tmp_path, code_sha=SHA_A
        )


def test_missing_trusted_key_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("TRADEBOT_LIVE_SESSION_ATTESTATION_KEY", raising=False)
    with pytest.raises(ValueError, match="TRUSTED_LIVE_ATTESTATION_KEY_REQUIRED"):
        finalize(tmp_path)


def test_consistently_wrong_tokens_are_rejected(tmp_path):
    wrong = {"NIFTY": 999999, "BANKNIFTY": 888888, "SENSEX": 777777}
    candidate = {s: bars(s, instrument_token=wrong[s]) for s in pme.REQUIRED}
    attestation = signed_attestation(tokens=wrong)
    with pytest.raises(ValueError, match="LIVE_ATTESTATION_INDEX_IDENTITY_INVALID"):
        finalize(tmp_path, candidate, attestation=attestation)


def test_attestation_chronology_is_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="LIVE_ATTESTATION_TIMESTAMP_INVALID"):
        finalize(tmp_path, attestation=signed_attestation(attested_at="2099-01-01T16:00:00+05:30"))
    with pytest.raises(ValueError, match="LIVE_ATTESTATION_TIMESTAMP_INVALID"):
        finalize(tmp_path, attestation=signed_attestation(attested_at="2026-08-12T15:31:00+05:30"))


def test_incomplete_missing_duplicate_nonmonotonic_and_gap_are_rejected(tmp_path):
    partial = {s: bars(s, 285) for s in pme.REQUIRED}
    with pytest.raises(ValueError, match="SESSION_INCOMPLETE"):
        finalize(tmp_path, partial)

    missing = good()
    missing.pop("SENSEX")
    with pytest.raises(ValueError, match="SESSION_INCOMPLETE:SENSEX"):
        finalize(tmp_path, missing)

    duplicate = good()
    duplicate["NIFTY"][1]["ts"] = duplicate["NIFTY"][0]["ts"]
    with pytest.raises(ValueError, match="TIMESTAMP_ORDER_INVALID"):
        finalize(tmp_path, duplicate)

    nonmonotonic = good()
    nonmonotonic["NIFTY"][10], nonmonotonic["NIFTY"][11] = nonmonotonic["NIFTY"][11], nonmonotonic["NIFTY"][10]
    with pytest.raises(ValueError, match="TIMESTAMP_ORDER_INVALID"):
        finalize(tmp_path, nonmonotonic)

    gap = good()
    for bar in gap["BANKNIFTY"][120:]:
        bar["ts"] += timedelta(minutes=1)
    with pytest.raises(ValueError, match="SESSION_BOUNDARY_INVALID|SESSION_GAP"):
        finalize(tmp_path, gap)


def test_invalid_nonfinite_and_future_bars_are_rejected(tmp_path):
    invalid = good()
    invalid["SENSEX"][20]["high"] = invalid["SENSEX"][20]["low"] - 1
    with pytest.raises(ValueError, match="OHLC_INVALID"):
        finalize(tmp_path, invalid)

    nonfinite = good()
    nonfinite["NIFTY"][20]["close"] = float("nan")
    with pytest.raises(ValueError, match="OHLC_INVALID"):
        finalize(tmp_path, nonfinite)

    future = good()
    future["NIFTY"].append({**future["NIFTY"][-1], "ts": future["NIFTY"][-1]["ts"] + timedelta(days=1)})
    with pytest.raises(ValueError, match="FUTURE_BAR_PRESENT"):
        finalize(tmp_path, future)


@pytest.mark.parametrize(
    "kwargs",
    [{"replay": True}, {"fallback": True}, {"synthetic": True}, {"source_type": "historical_seed"}],
)
def test_declared_non_live_provenance_cannot_certify(tmp_path, kwargs):
    candidate = good()
    candidate["NIFTY"] = bars("NIFTY", **kwargs)
    with pytest.raises(ValueError, match="NON_LIVE_PROVENANCE|LIVE_PROVENANCE_INCOMPLETE"):
        finalize(tmp_path, candidate)


def test_missing_or_mismatched_identity_is_rejected(tmp_path):
    candidate = good()
    candidate["NIFTY"][100]["bar_provenance"].pop("instrument_token")
    with pytest.raises(ValueError, match="LIVE_PROVENANCE_INCOMPLETE:NIFTY:instrument_token"):
        finalize(tmp_path, candidate)

    candidate = good()
    candidate["SENSEX"] = bars("SENSEX", provider="other-provider")
    with pytest.raises(ValueError, match="SOURCE_IDENTITY_MISMATCH:SENSEX:provider"):
        finalize(tmp_path, candidate)

    candidate = good()
    candidate["BANKNIFTY"][0]["bar_provenance"]["symbol"] = "NIFTY"
    with pytest.raises(ValueError, match="SOURCE_IDENTITY_MISMATCH:BANKNIFTY:symbol"):
        finalize(tmp_path, candidate)


def test_immutable_idempotency_and_tamper_detection(tmp_path):
    candidate = good()
    assert finalize(tmp_path, candidate)["status"] == "SEALED"
    assert finalize(tmp_path, candidate)["status"] == "IDEMPOTENT"
    path = tmp_path / "2026-08-11.json"
    payload = json.loads(path.read_text())
    payload["created_at_ist"] = "2026-08-11T16:45:00+05:30"
    path.write_text(json.dumps(payload))
    with pytest.raises(FileExistsError, match="IMMUTABLE_EVIDENCE_CONFLICT"):
        finalize(tmp_path, candidate)


def test_code_sha_change_is_not_idempotent(tmp_path):
    candidate = good()
    finalize(tmp_path, candidate, code_sha=SHA_A)
    with pytest.raises(FileExistsError, match="IMMUTABLE_EVIDENCE_CONFLICT"):
        finalize(tmp_path, candidate, code_sha=SHA_B, attestation=signed_attestation(code_sha=SHA_B))


def test_safe_wrapper_failures_are_contained(monkeypatch, tmp_path):
    monkeypatch.delenv("TRADEBOT_LIVE_SESSION_ATTESTATION_PATH", raising=False)
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


def test_buffer_integration_requires_content_bound_attestation(tmp_path):
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
            session_date=D, bars_by_symbol=assembled, output_root=tmp_path, code_sha=SHA_A
        )
    result = finalize(
        tmp_path,
        assembled,
        code_sha=SHA_A,
        attestation=signed_attestation(bar_source=assembled),
    )
    assert result["status"] == "SEALED"
