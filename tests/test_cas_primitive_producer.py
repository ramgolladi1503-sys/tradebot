from core.cas_primitive_producer import CASPrimitiveStore, build_cas_input, verify_primitive

def tick(price, ts):
    return {"underlying_symbol":"NIFTY","last_price":price,"timestamp_epoch":ts,"timestamp_authority":"EXCHANGE_TIMESTAMP","timestamp_source_field":"exchange_timestamp","source_timestamp_epoch":ts,"receive_timestamp_epoch":ts+1,"timestamp_fallback_used":False}

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

def test_missing_target_and_malformed_input_fail_closed(tmp_path):
    s=CASPrimitiveStore(tmp_path/"cas.json",session_id="s",source_sha="x",underlying_token=1)
    a=s.capture("0915",100,tick(100,100.5),capture_timestamp_ist="x")
    assert build_cas_input({"0915":a},session_id="s",source_sha="x",cycle_id="c") is None
    assert build_cas_input({"0915":a,"1000":{}},session_id="s",source_sha="x",cycle_id="c") is None

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
