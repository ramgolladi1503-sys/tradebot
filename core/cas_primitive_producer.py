"""Governed prospective CAS primitive capture; advisory/read-only only."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
import hashlib, json, math
from pathlib import Path

SPEC_ID = "CAS_MORNING_REVERSAL_SHORT_HORIZON_PRIMITIVE_SPEC_V1"
STRATEGY_ID = "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1"
SPEC_SHA = "6567c832f26976d6a4ff71e2532dd125bf09888324e463750a8817c094b7bb6c"
ELIGIBLE_AUTHORITIES = {"EXCHANGE_TIMESTAMP"}
TARGETS = {"0915": "09:15:00.000", "1000": "10:00:00.000"}

@dataclass(frozen=True)
class Primitive:
    schema_version: int; strategy_id: str; session_id: str; source_sha: str
    underlying_symbol: str; underlying_token: int; primitive_name: str
    target_timestamp_ist: str; capture_status: str; capture_timestamp_ist: str|None
    price: float|None; price_field: str; price_source: str
    timestamp_epoch: float|None; timestamp_authority: str; timestamp_source_field: str|None
    source_timestamp_epoch: float|None; receive_timestamp_epoch: float|None
    timestamp_fallback_used: bool|None; lateness_ms: int|None; freshness_pass: bool
    captured_live_prospectively: bool; immutable: bool
    admissible_for_prospective_campaign: bool; created_at_ist: str; record_sha256: str|None = None

def _hash(row: dict) -> str:
    payload = {k:v for k,v in row.items() if k != "record_sha256"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",",":"), default=str).encode()).hexdigest()

def _valid_tick(tick: dict, target_epoch: float) -> bool:
    return (tick.get("underlying_symbol") == "NIFTY" and tick.get("timestamp_authority") in ELIGIBLE_AUTHORITIES
            and math.isfinite(float(tick.get("last_price"))) and float(tick.get("last_price")) > 0
            and math.isfinite(float(tick.get("timestamp_epoch"))) and float(tick["timestamp_epoch"]) >= target_epoch
            and (float(tick["timestamp_epoch"]) - target_epoch) * 1000 <= 2000)

class CASPrimitiveStore:
    def __init__(self, path: str|Path, *, session_id: str, source_sha: str, underlying_token: int):
        self.path=Path(path); self.session_id=session_id; self.source_sha=source_sha; self.underlying_token=underlying_token
        self.rows = json.loads(self.path.read_text()).get("primitives", {}) if self.path.exists() else {}
    def persist(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload={"schema_version":1,"session_id":self.session_id,"source_sha":self.source_sha,"primitives":self.rows}
        tmp=self.path.with_suffix(self.path.suffix+".tmp"); tmp.write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n"); tmp.replace(self.path)
    def capture(self, name: str, target_epoch: float, tick: dict, *, capture_timestamp_ist: str) -> dict:
        old=self.rows.get(name)
        if old is not None: return old
        if not _valid_tick(tick,target_epoch):
            return self._terminal(name,target_epoch,"BLOCKED",None,capture_timestamp_ist)
        row=Primitive(1,STRATEGY_ID,self.session_id,self.source_sha,"NIFTY",self.underlying_token,name,TARGETS[name],"CAPTURED",capture_timestamp_ist,float(tick["last_price"]),"last_price","core/tick_store.py",float(tick["timestamp_epoch"]),tick["timestamp_authority"],tick.get("timestamp_source_field"),tick.get("source_timestamp_epoch"),tick.get("receive_timestamp_epoch"),tick.get("timestamp_fallback_used"),int(round((float(tick["timestamp_epoch"])-target_epoch)*1000)),True,True,True,True,capture_timestamp_ist). __dict__
        row["record_sha256"]=_hash(row); self.rows[name]=row; self.persist(); return row
    def _terminal(self,name,target,status,price,captured):
        row=Primitive(1,STRATEGY_ID,self.session_id,self.source_sha,"NIFTY",self.underlying_token,name,TARGETS[name],status,captured,price,"last_price","core/tick_store.py",None,"UNKNOWN",None,None,None,None,None,False,False,False,False,captured).__dict__
        row["record_sha256"]=_hash(row); self.rows[name]=row; self.persist(); return row

def verify_primitive(row: dict, *, session_id: str, source_sha: str, underlying_token: int) -> tuple[bool,str]:
    if row.get("record_sha256") != _hash(row): return False,"hash"
    if row.get("session_id") != session_id or row.get("source_sha") != source_sha or row.get("underlying_token") != underlying_token: return False,"identity"
    if row.get("capture_status") != "CAPTURED" or not row.get("captured_live_prospectively") or not row.get("immutable"): return False,"status"
    if row.get("timestamp_authority") not in ELIGIBLE_AUTHORITIES or not row.get("freshness_pass"): return False,"authority"
    if row.get("price_field") != "last_price" or not math.isfinite(float(row["price"])) or float(row["price"]) <= 0: return False,"price"
    if row.get("lateness_ms") is None or not 0 <= int(row["lateness_ms"]) <= 2000: return False,"window"
    return True,"ok"

def build_cas_input(rows: dict, *, session_id: str, source_sha: str, cycle_id: str, underlying_token: int|None = None, observation_timestamp: str|None = None) -> dict|None:
    a,b=rows.get("0915"),rows.get("1000")
    expected_token = underlying_token if underlying_token is not None else (a.get("underlying_token") if a else None)
    if not a or not b or expected_token is None or any(verify_primitive(r,session_id=session_id,source_sha=source_sha,underlying_token=expected_token)[0] is False for r in (a,b)): return None
    ret=float(b["price"])/float(a["price"])-1
    direction="DOWN" if ret>0 else "UP" if ret<0 else "NO_SIGNAL"
    observed_at = observation_timestamp or b["capture_timestamp_ist"]
    return {"strategy_id":STRATEGY_ID,"session_id":session_id,"source_sha":source_sha,"cycle_id":cycle_id,"symbol":"NIFTY","signal_input_09_15":a["price"],"signal_input_10_00":b["price"],"morning_return":ret,"signal_direction":direction,"observation_timestamp":observed_at,"received_timestamp":observed_at,"captured_live_prospectively":True,"admissible_for_prospective_campaign":True}
