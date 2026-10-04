import pytest
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor

from core.cas_primitive_producer import CASPrimitiveStore, build_cas_input, verify_primitive

def tick(price, ts):
    payload={"instrument_token":1,"underlying_symbol":"NIFTY","last_price":price,"volume":None,"oi":None,"source_timestamp_field":"exchange_timestamp","source_timestamp_epoch":ts}
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
    return {"instrument_token":1,"underlying_symbol":"NIFTY","last_price":price,"timestamp_epoch":ts,"timestamp_authority":"EXCHANGE_TIMESTAMP","timestamp_source_field":"exchange_timestamp","source_timestamp_epoch":ts,"receive_timestamp_epoch":ts,"timestamp_fallback_used":False,"source_event_id":f"feed:1:1:{digest[:16]}","source_event_sha256":digest,"source_event_payload":payload}

def test_capture_input_and_immutable_restart(tmp_path):
    p=tmp_path/"cas.json"; s=CASPrimitiveStore(p,session_id="s",source_sha="x",underlying_token=1)
    a=s.capture("0915",100,tick(100,100.5),capture_timestamp_ist="2026-09-04T09:15:00+05:30")
    b=s.capture("1000",200,tick(110,200.5),capture_timestamp_ist="2026-09-04T10:00:00+05:30")
    assert verify_primitive(a,session_id="s",source_sha="x",underlying_token=1)[0]
    assert build_cas_input({"0915":a,"1000":b},session_id="s",source_sha="x",cycle_id="c")["signal_direction"]=="DOWN"
    assert CASPrimitiveStore(p,session_id="s",source_sha="x",underlying_token=1).rows["0915"]["price"]==100

def test_ineligible_or_late_tick_does_not_capture(tmp_path):
    s=CASPrimitiveStore(tmp_path/"cas.json",session_id="s",source_sha="x",underlying_token=1)
    row=s.capture("0915",100,{**tick(100,102.1),"timestamp_authority":"GOVERNED_RECEIVE_TIMESTAMP"},capture_timestamp_ist="x")
    assert row["capture_status"]=="BLOCKED"

def test_up_and_zero_signals_use_only_two_frozen_prices(tmp_path):
    for first, second, expected in ((100, 90, "UP"), (100, 100, "NO_SIGNAL")):
        s=CASPrimitiveStore(tmp_path/f"{expected}.json",session_id="s",source_sha="x",underlying_token=1)
        a=s.capture("0915",100,tick(first,100.5),capture_timestamp_ist="2026-09-04T15:14:00+00:00")
        b=s.capture("1000",200,tick(second,200.5),capture_timestamp_ist="2026-09-04T15:14:00+00:00")
        assert build_cas_input({"0915":a,"1000":b},session_id="s",source_sha="x",cycle_id="c")["signal_direction"]==expected

def test_duplicate_capture_and_wrong_identity_fail_closed(tmp_path):
    s=CASPrimitiveStore(tmp_path/"cas.json",session_id="s",source_sha="x",underlying_token=1)
    first=s.capture("0915",100,tick(100,100.5),capture_timestamp_ist="x")
    second=s.capture("0915",100,tick(999,100.6),capture_timestamp_ist="y")
    assert second["price"]==first["price"]
    assert verify_primitive(first,session_id="other",source_sha="x",underlying_token=1)[0] is False

def test_late_tick_is_not_prospectively_admissible(tmp_path):
    s=CASPrimitiveStore(tmp_path/"cas.json",session_id="s",source_sha="x",underlying_token=1)
    late=s.capture("1000",200,tick(100,202.001),capture_timestamp_ist="x")
    assert late["capture_status"]=="BLOCKED"
    assert late["admissible_for_prospective_campaign"] is False


def test_future_exchange_event_is_not_admissible(tmp_path):
    future_epoch = time.time() + 60
    store = CASPrimitiveStore(tmp_path/"future.json", session_id="s", source_sha="x", underlying_token=1)
    row = store.capture("0915", future_epoch - 0.5, tick(100, future_epoch), capture_timestamp_ist="future")
    assert row["capture_status"] == "BLOCKED"
    assert row["price"] is None

def test_selected_receipt_time_cannot_substitute_for_late_exchange_event(tmp_path):
    s=CASPrimitiveStore(tmp_path/"cas.json",session_id="s",source_sha="x",underlying_token=1)
    # Exchange time is a whole second after the 09:15 target; receipt time is
    # artificially made target-exact. No source/receipt relaxation is allowed.
    late={**tick(100,100.0),"source_timestamp_epoch":101.0,"receive_timestamp_epoch":100.0}
    row=s.capture("0915",100,late,capture_timestamp_ist="x")
    assert row["capture_status"]=="BLOCKED"
    assert row["timestamp_authority"]=="UNKNOWN"

def test_exchange_selection_time_and_local_receive_time_remain_distinct(tmp_path):
    store=CASPrimitiveStore(tmp_path/"delayed-receive.json",session_id="s",source_sha="x",underlying_token=1)
    selected=tick(100,100.5)
    selected["receive_timestamp_epoch"]=104.25
    row=store.capture("0915",100,selected,capture_timestamp_ist="x")
    assert row["capture_status"]=="CAPTURED"
    assert row["timestamp_epoch"]==row["source_timestamp_epoch"]==100.5
    assert row["receive_timestamp_epoch"]==104.25
    assert verify_primitive(row,session_id="s",source_sha="x",underlying_token=1)==(True,"ok")

def test_pre_target_whole_second_event_is_rejected_even_after_target_receive(tmp_path):
    store=CASPrimitiveStore(tmp_path/"whole-second-boundary.json",session_id="s",source_sha="x",underlying_token=1)
    early=tick(100,99.0)
    early["receive_timestamp_epoch"]=100.1
    row=store.capture("0915",100,early,capture_timestamp_ist="x")
    assert row["capture_status"]=="BLOCKED"
    assert row["price"] is None

def test_primitive_verifier_recomputes_frozen_target_window(tmp_path):
    import core.cas_primitive_producer as producer
    store=CASPrimitiveStore(tmp_path/"target.json",session_id="s",source_sha="x",underlying_token=1)
    row=store.capture("0915",100,tick(100,100.5),capture_timestamp_ist="x")
    wrong_target={**row,"target_timestamp_ist":"10:00:00.000"}
    wrong_target["record_sha256"]=producer._hash(wrong_target)
    assert verify_primitive(wrong_target,session_id="s",source_sha="x",underlying_token=1)==(False,"target_identity")
    wrong_lateness={**row,"lateness_ms":0}
    wrong_lateness["record_sha256"]=producer._hash(wrong_lateness)
    assert verify_primitive(wrong_lateness,session_id="s",source_sha="x",underlying_token=1)==(False,"window")

def test_event_payload_hash_binds_price_token_and_source_time(tmp_path):
    s=CASPrimitiveStore(tmp_path/"cas.json",session_id="s",source_sha="x",underlying_token=1)
    good=tick(100,100.5)
    assert s.capture("0915",100,good,capture_timestamp_ist="x")["capture_status"]=="CAPTURED"
    for index,overrides in enumerate((
        {"last_price": 101.0},
        {"instrument_token": 2},
        {"source_timestamp_epoch": 101.0},
        {"source_event_payload": {"last_price": "not-a-number"}},
    )):
        changed={**tick(100,100.5),**overrides}
        assert CASPrimitiveStore(tmp_path/f"event-case-{index}.json",session_id="s",source_sha="x",underlying_token=1).capture(
            "0915",100,changed,capture_timestamp_ist="x")["capture_status"]=="BLOCKED"

    import core.cas_primitive_producer as producer
    row = CASPrimitiveStore(tmp_path/"persisted.json",session_id="s",source_sha="x",underlying_token=1).capture(
        "0915",100,good,capture_timestamp_ist="x")
    tampered = dict(row)
    tampered["source_event_payload"] = {**tampered["source_event_payload"], "last_price": 101.0}
    tampered["record_sha256"] = producer._hash(tampered)
    assert verify_primitive(tampered,session_id="s",source_sha="x",underlying_token=1) == (False,"source_event_hash_mismatch")

def test_primitive_verifier_rejects_self_consistent_wrong_underlying_identity(tmp_path):
    import core.cas_primitive_producer as producer

    store = CASPrimitiveStore(tmp_path / "wrong-underlying.json", session_id="s", source_sha="x", underlying_token=1)
    row = store.capture("0915", 100, tick(100, 100.5), capture_timestamp_ist="x")
    payload = {**row["source_event_payload"], "underlying_symbol": "BANKNIFTY"}
    event_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    forged = {
        **row,
        "underlying_symbol": "BANKNIFTY",
        "source_event_payload": payload,
        "source_event_sha256": event_hash,
        "source_event_id": f"feed:s:1:1:{event_hash[:16]}",
    }
    forged["record_sha256"] = producer._hash(forged)

    assert verify_primitive(forged, session_id="s", source_sha="x", underlying_token=1) == (False, "identity")

@pytest.mark.parametrize("bad_token", [True, 1.0, "1", 0, -1])
def test_capture_rejects_self_consistent_malformed_instrument_tokens(tmp_path, bad_token):
    valid_tick = tick(100, 100.5)
    payload = {**valid_tick["source_event_payload"], "instrument_token": bad_token}
    event_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    malformed = {
        **valid_tick,
        "instrument_token": bad_token,
        "source_event_payload": payload,
        "source_event_sha256": event_hash,
        "source_event_id": f"feed:s:1:1:{event_hash[:16]}",
    }

    store = CASPrimitiveStore(tmp_path / "bad-token.json", session_id="s", source_sha="x", underlying_token=1)
    row = store.capture("0915", 100, malformed, capture_timestamp_ist="x")

    assert row["capture_status"] == "BLOCKED"
    assert row["price"] is None

@pytest.mark.parametrize("bad_token", [True, 1.0, "1", 0, -1])
def test_verifier_rejects_self_consistent_malformed_event_tokens(tmp_path, bad_token):
    import core.cas_primitive_producer as producer

    store = CASPrimitiveStore(tmp_path / "bad-event-token.json", session_id="s", source_sha="x", underlying_token=1)
    row = store.capture("0915", 100, tick(100, 100.5), capture_timestamp_ist="x")
    payload = {**row["source_event_payload"], "instrument_token": bad_token}
    event_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    malformed = {
        **row,
        "source_event_payload": payload,
        "source_event_sha256": event_hash,
        "source_event_id": f"feed:s:1:1:{event_hash[:16]}",
    }
    malformed["record_sha256"] = producer._hash(malformed)

    valid, reason = verify_primitive(malformed, session_id="s", source_sha="x", underlying_token=1)

    assert valid is False
    assert reason == "source_event_binding_invalid"

@pytest.mark.parametrize("bad_token", [True, 1.0, "1", 0, -1])
def test_verifier_rejects_malformed_persisted_row_tokens(tmp_path, bad_token):
    import core.cas_primitive_producer as producer

    store = CASPrimitiveStore(tmp_path / "bad-row-token.json", session_id="s", source_sha="x", underlying_token=1)
    row = store.capture("0915", 100, tick(100, 100.5), capture_timestamp_ist="x")
    malformed = {**row, "underlying_token": bad_token}
    malformed["record_sha256"] = producer._hash(malformed)

    assert verify_primitive(malformed, session_id="s", source_sha="x", underlying_token=1) == (False, "identity")

@pytest.mark.parametrize("bad_expected_token", [True, 1.0, "1", 0, -1])
def test_verifier_rejects_malformed_expected_token(tmp_path, bad_expected_token):
    store = CASPrimitiveStore(tmp_path / "expected-token.json", session_id="s", source_sha="x", underlying_token=1)
    row = store.capture("0915", 100, tick(100, 100.5), capture_timestamp_ist="x")

    assert verify_primitive(row, session_id="s", source_sha="x", underlying_token=bad_expected_token) == (False, "identity")

def test_capture_with_missing_expected_token_never_persists_captured_primitive(tmp_path):
    store = CASPrimitiveStore(tmp_path / "missing-config-token.json", session_id="s", source_sha="x", underlying_token=None)

    row = store.capture("0915", 100, tick(100, 100.5), capture_timestamp_ist="x")

    assert row["capture_status"] == "BLOCKED"
    assert row["price"] is None
    assert verify_primitive(row, session_id="s", source_sha="x", underlying_token=None) == (False, "identity")

def test_blocked_attempt_does_not_prevent_later_valid_same_run_capture(tmp_path):
    p=tmp_path/"cas.json"; s=CASPrimitiveStore(p,session_id="s",source_sha="x",underlying_token=1)
    blocked=s.capture("0915",100,{**tick(100,101.0),"timestamp_authority":"UNKNOWN"},capture_timestamp_ist="first")
    assert blocked["capture_status"]=="BLOCKED"
    valid_tick=tick(100,100.5)
    valid_tick["receive_timestamp_epoch"]=100.5
    captured=s.capture("0915",100,valid_tick,capture_timestamp_ist="second")
    assert captured["capture_status"]=="CAPTURED"
    assert verify_primitive(captured,session_id="s",source_sha="x",underlying_token=1)==(True,"ok")

def test_two_distinct_captured_values_are_a_conflict(tmp_path):
    p=tmp_path/"cas.json"; first=CASPrimitiveStore(p,session_id="s",source_sha="x",underlying_token=1)
    first.capture("0915",100,tick(100,100.5),capture_timestamp_ist="x")
    second=CASPrimitiveStore(p,session_id="s",source_sha="x",underlying_token=1)
    second.rows["0915"]={**first.rows["0915"],"price":101}
    with pytest.raises(ValueError,match="CAS_PRIMITIVE_CONFLICT"):
        second.persist()

def test_concurrent_writers_merge_distinct_targets_without_lost_update(tmp_path):
    p=tmp_path/"cas.json"
    first=CASPrimitiveStore(p,session_id="s",source_sha="x",underlying_token=1)
    second=CASPrimitiveStore(p,session_id="s",source_sha="x",underlying_token=1)
    a=tick(100,100.5); b=tick(110,200.5)
    with ThreadPoolExecutor(max_workers=2) as pool:
        left=pool.submit(first.capture,"0915",100,a,capture_timestamp_ist="a")
        right=pool.submit(second.capture,"1000",200,b,capture_timestamp_ist="b")
        assert left.result()["capture_status"]=="CAPTURED"
        assert right.result()["capture_status"]=="CAPTURED"
    reopened=CASPrimitiveStore(p,session_id="s",source_sha="x",underlying_token=1)
    assert set(reopened.rows)=={"0915","1000"}

def test_stale_restart_cannot_replace_an_existing_captured_primitive(tmp_path):
    p=tmp_path/"cas.json"
    first=CASPrimitiveStore(p,session_id="s",source_sha="x",underlying_token=1)
    accepted=first.capture("0915",100,tick(100,100.5),capture_timestamp_ist="first")
    stale=CASPrimitiveStore(p,session_id="s",source_sha="x",underlying_token=1)
    stale.rows["0915"]={**accepted,"price":999}
    with pytest.raises(ValueError,match="CAS_PRIMITIVE_CONFLICT"):
        stale.persist()
    assert CASPrimitiveStore(p,session_id="s",source_sha="x",underlying_token=1).rows["0915"]==accepted

def test_missing_target_and_malformed_input_fail_closed(tmp_path):
    s=CASPrimitiveStore(tmp_path/"cas.json",session_id="s",source_sha="x",underlying_token=1)
    with pytest.raises(ValueError,match="UNKNOWN_CAS_PRIMITIVE"):
        s.capture("unknown",100,tick(100,100.5),capture_timestamp_ist="x")
    a=s.capture("0915",100,tick(100,100.5),capture_timestamp_ist="x")
    assert build_cas_input({"0915":a},session_id="s",source_sha="x",cycle_id="c") is None
    assert build_cas_input({"0915":a,"1000":{}},session_id="s",source_sha="x",cycle_id="c") is None
    malformed = {**a, "record_sha256": "0" * 64, "price": "not-a-number"}
    assert verify_primitive(malformed,session_id="s",source_sha="x",underlying_token=1)[0] is False

@pytest.mark.parametrize("bad_id", [None, "", 17, True, object()])
def test_malformed_source_event_ids_block_capture_without_raising(tmp_path, bad_id):
    store = CASPrimitiveStore(tmp_path / "bad-event-id.json", session_id="s", source_sha="x", underlying_token=1)
    malformed_tick = {**tick(100, 100.5), "source_event_id": bad_id}

    row = store.capture("0915", 100, malformed_tick, capture_timestamp_ist="x")

    assert row["capture_status"] == "BLOCKED"
    assert row["source_event_id"] is None
    assert not verify_primitive(row, session_id="s", source_sha="x", underlying_token=1)[0]

@pytest.mark.parametrize("bad_id", [None, "", 17, True, object()])
def test_primitive_verifier_rejects_malformed_source_event_ids_without_raising(tmp_path, bad_id):
    import core.cas_primitive_producer as producer

    store = CASPrimitiveStore(tmp_path / "valid-event-id.json", session_id="s", source_sha="x", underlying_token=1)
    row = store.capture("0915", 100, tick(100, 100.5), capture_timestamp_ist="x")
    malformed = {**row, "source_event_id": bad_id}
    malformed["record_sha256"] = producer._hash(malformed)

    valid, reason = verify_primitive(malformed, session_id="s", source_sha="x", underlying_token=1)

    assert valid is False
    assert reason == "source_event_binding_missing"

def test_restart_and_corruption_are_detectable(tmp_path):
    p=tmp_path/"cas.json"; s=CASPrimitiveStore(p,session_id="s",source_sha="x",underlying_token=1)
    row=s.capture("0915",100,tick(100,100.5),capture_timestamp_ist="x")
    reloaded=CASPrimitiveStore(p,session_id="s",source_sha="x",underlying_token=1).rows["0915"]
    assert reloaded == row
    reloaded["price"] = 101
    assert verify_primitive(reloaded,session_id="s",source_sha="x",underlying_token=1)[0] is False

def test_non_nifty_and_unknown_timestamp_authority_are_blocked(tmp_path):
    s=CASPrimitiveStore(tmp_path/"cas.json",session_id="s",source_sha="x",underlying_token=1)
    assert s.capture("0915",100,{**tick(100,100.5),"underlying_symbol":"BANKNIFTY"},capture_timestamp_ist="x")["capture_status"]=="BLOCKED"
    assert s.capture("1000",200,{**tick(100,200.5),"timestamp_authority":"UNKNOWN"},capture_timestamp_ist="x")["capture_status"]=="BLOCKED"

def test_cas_input_rejects_cross_token_records(tmp_path):
    s=CASPrimitiveStore(tmp_path/"cas.json",session_id="s",source_sha="x",underlying_token=1)
    a=s.capture("0915",100,tick(100,100.5),capture_timestamp_ist="x")
    b=s.capture("1000",200,{**tick(110,200.5),"underlying_token":2},capture_timestamp_ist="x")
    b["underlying_token"] = 2
    assert build_cas_input({"0915":a,"1000":b},session_id="s",source_sha="x",cycle_id="c",underlying_token=1) is None

def test_build_input_uses_decision_observation_time_without_mutating_capture(tmp_path):
    s=CASPrimitiveStore(tmp_path/"cas.json",session_id="s",source_sha="x",underlying_token=1)
    a=s.capture("0915",100,tick(100,100.5),capture_timestamp_ist="2026-09-05T09:15:00+05:30")
    b=s.capture("1000",200,tick(110,200.5),capture_timestamp_ist="2026-09-05T10:00:00+05:30")
    observed="2026-09-05T15:14:00+05:30"
    result=build_cas_input({"0915":a,"1000":b},session_id="s",source_sha="x",cycle_id="c",observation_timestamp=observed)
    assert result["observation_timestamp"]==observed
    assert b["capture_timestamp_ist"] != observed
