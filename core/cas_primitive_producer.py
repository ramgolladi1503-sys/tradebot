"""Governed prospective CAS primitive capture; advisory/read-only only."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib, json, math
from pathlib import Path
import os
import tempfile
import fcntl
import time
from zoneinfo import ZoneInfo

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
    admissible_for_prospective_campaign: bool; created_at_ist: str
    source_event_id: str|None = None; source_event_sha256: str|None = None
    source_event_payload: dict|None = None
    target_timestamp_epoch: float|None = None
    record_sha256: str|None = None

def _hash(row: dict) -> str:
    payload = {k:v for k,v in row.items() if k != "record_sha256"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",",":"), default=str).encode()).hexdigest()

def _valid_tick(tick: dict, target_epoch: float, expected_token: int | None = None) -> bool:
    try:
        selected = float(tick["timestamp_epoch"])
        source = float(tick["source_timestamp_epoch"])
        receive = float(tick["receive_timestamp_epoch"])
        price = float(tick["last_price"])
        target = float(target_epoch)
    except (KeyError, TypeError, ValueError):
        return False
    # The frozen CAS contract selects on the validated exchange timestamp and
    # retains local receive time for audit. Receive time is a distinct clock;
    # it need not equal the exchange event epoch.
    event_payload = tick.get("source_event_payload")
    try:
        event_hash = hashlib.sha256(json.dumps(event_payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest() if isinstance(event_payload, dict) else None
        event_bound = (bool(tick.get("source_event_id")) and event_hash is not None
                       and event_hash == tick.get("source_event_sha256")
                       and (expected_token is None or tick.get("instrument_token") == expected_token)
                       and (expected_token is None or tick.get("source_event_id", "").endswith(f":{expected_token}:{event_hash[:16]}"))
                       and event_payload.get("instrument_token") == tick.get("instrument_token")
                       and event_payload.get("underlying_symbol") == tick.get("underlying_symbol")
                       and float(event_payload.get("last_price")) == price
                       and event_payload.get("source_timestamp_epoch") == source
                       and event_payload.get("source_timestamp_field") == tick.get("timestamp_source_field"))
    except (TypeError, ValueError, OverflowError):
        event_bound = False
    return (event_bound and tick.get("underlying_symbol") == "NIFTY"
            and tick.get("timestamp_authority") in ELIGIBLE_AUTHORITIES
            and tick.get("timestamp_source_field")
            and tick.get("timestamp_fallback_used") is False
            and all(math.isfinite(value) for value in (selected, source, receive, price))
            and price > 0 and selected == source
            and math.isfinite(target)
            and selected <= time.time() + 0.05
            and source >= target and (source - target) * 1000 <= 2000)

class CASPrimitiveStore:
    def __init__(self, path: str|Path, *, session_id: str, source_sha: str, underlying_token: int):
        self.path=Path(path); self.session_id=session_id; self.source_sha=source_sha; self.underlying_token=underlying_token
        self.rows = json.loads(self.path.read_text()).get("primitives", {}) if self.path.exists() else {}
    def persist(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path=self.path.with_name(self.path.name+".lock")
        lock_fd=os.open(lock_path,os.O_CREAT|os.O_RDWR,0o600)
        try:
            deadline=time.monotonic()+2.0
            while True:
                try:
                    fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic()>=deadline: raise TimeoutError("CAS_STORE_LOCK_TIMEOUT")
                    time.sleep(0.01)
            merged={}
            if self.path.exists():
                current=json.loads(self.path.read_text(encoding="utf-8"))
                if current.get("session_id") != self.session_id or current.get("source_sha") != self.source_sha:
                    raise ValueError("CAS_STORE_IDENTITY_CONFLICT")
                merged=dict(current.get("primitives") or {})
            for name,row in self.rows.items():
                prior=merged.get(name)
                if prior is not None and prior.get("capture_status")=="CAPTURED" and row.get("capture_status")=="CAPTURED" and prior!=row:
                    raise ValueError("CAS_PRIMITIVE_CONFLICT:"+name)
                if prior is None or prior.get("capture_status")!="CAPTURED" or row.get("capture_status")=="CAPTURED":
                    merged[name]=row
            payload={"schema_version":1,"session_id":self.session_id,"source_sha":self.source_sha,"primitives":merged}
            encoded=json.dumps(payload,sort_keys=True,indent=2)+"\n"
            fd,tmp_name=tempfile.mkstemp(prefix=f".{self.path.name}.",suffix=".tmp",dir=str(self.path.parent))
            try:
                with os.fdopen(fd,"w",encoding="utf-8") as handle:
                    handle.write(encoded); handle.flush(); os.fsync(handle.fileno())
                os.replace(tmp_name,self.path)
                dir_fd=os.open(self.path.parent,os.O_RDONLY)
                try: os.fsync(dir_fd)
                finally: os.close(dir_fd)
            finally:
                if os.path.exists(tmp_name): os.unlink(tmp_name)
            self.rows=merged
        finally:
            try: fcntl.flock(lock_fd,fcntl.LOCK_UN)
            finally: os.close(lock_fd)
    def capture(self, name: str, target_epoch: float, tick: dict, *, capture_timestamp_ist: str) -> dict:
        if name not in TARGETS:
            raise ValueError("UNKNOWN_CAS_PRIMITIVE")
        old=self.rows.get(name)
        if old is not None and old.get("capture_status") == "CAPTURED": return old
        if old is not None and not _valid_tick(tick,target_epoch,self.underlying_token): return old
        if not _valid_tick(tick,target_epoch,self.underlying_token):
            return self._terminal(name,target_epoch,"BLOCKED",None,capture_timestamp_ist)
        row=Primitive(1,STRATEGY_ID,self.session_id,self.source_sha,"NIFTY",self.underlying_token,name,TARGETS[name],"CAPTURED",capture_timestamp_ist,float(tick["last_price"]),"last_price","core/tick_store.py",float(tick["timestamp_epoch"]),tick["timestamp_authority"],tick.get("timestamp_source_field"),tick.get("source_timestamp_epoch"),tick.get("receive_timestamp_epoch"),tick.get("timestamp_fallback_used"),int(round((float(tick["timestamp_epoch"])-target_epoch)*1000)),True,True,True,True,capture_timestamp_ist,tick.get("source_event_id"),tick.get("source_event_sha256"),dict(tick.get("source_event_payload") or {}),float(target_epoch)). __dict__
        row["record_sha256"]=_hash(row); self.rows[name]=row; self.persist(); return row
    def _terminal(self,name,target,status,price,captured):
        row=Primitive(1,STRATEGY_ID,self.session_id,self.source_sha,"NIFTY",self.underlying_token,name,TARGETS[name],status,captured,price,"last_price","core/tick_store.py",None,"UNKNOWN",None,None,None,None,None,False,False,False,False,captured).__dict__
        row["record_sha256"]=_hash(row); self.rows[name]=row; self.persist(); return row

def verify_primitive(row: dict, *, session_id: str, source_sha: str, underlying_token: int) -> tuple[bool,str]:
    try:
        if not isinstance(row, dict): return False,"shape"
        if row.get("record_sha256") != _hash(row): return False,"hash"
        if row.get("session_id") != session_id or row.get("source_sha") != source_sha or row.get("underlying_token") != underlying_token: return False,"identity"
        if row.get("capture_status") != "CAPTURED" or not row.get("captured_live_prospectively") or not row.get("immutable"): return False,"status"
        if row.get("timestamp_authority") not in ELIGIBLE_AUTHORITIES or not row.get("freshness_pass"): return False,"authority"
        if row.get("timestamp_epoch") is None or row.get("source_timestamp_epoch") is None or row.get("receive_timestamp_epoch") is None or row.get("target_timestamp_epoch") is None: return False,"missing_timestamp_binding"
        selected = float(row["timestamp_epoch"])
        source = float(row["source_timestamp_epoch"])
        receive = float(row["receive_timestamp_epoch"])
        target = float(row["target_timestamp_epoch"])
        if not all(math.isfinite(value) for value in (selected, source, receive, target)): return False,"invalid_timestamp_binding"
        if selected != source: return False,"timestamp_binding"
        if row.get("primitive_name") not in TARGETS or row.get("target_timestamp_ist") != TARGETS[row["primitive_name"]]: return False,"target_identity"
        expected_lateness = int(round((selected - target) * 1000))
        if (expected_lateness < 0 or expected_lateness > 2000
                or row.get("lateness_ms") != expected_lateness): return False,"window"
        if row.get("timestamp_source_field") is None or row.get("timestamp_fallback_used") is not False: return False,"timestamp_authority_metadata"
        if not row.get("source_event_id") or not _valid_sha256(row.get("source_event_sha256")): return False,"source_event_binding_missing"
        event_payload = row.get("source_event_payload")
        if not isinstance(event_payload, dict): return False,"source_event_payload_missing"
        event_hash = hashlib.sha256(json.dumps(event_payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        if event_hash != row.get("source_event_sha256"): return False,"source_event_hash_mismatch"
        if (event_payload.get("instrument_token") != underlying_token
                or event_payload.get("underlying_symbol") != row.get("underlying_symbol")
                or float(event_payload.get("last_price")) != float(row["price"])
                or float(event_payload.get("source_timestamp_epoch")) != source
                or event_payload.get("source_timestamp_field") != row.get("timestamp_source_field")
                or not row.get("source_event_id", "").endswith(f":{underlying_token}:{event_hash[:16]}")):
            return False,"source_event_binding_invalid"
        if row.get("price_field") != "last_price" or not math.isfinite(float(row["price"])) or float(row["price"]) <= 0: return False,"price"
        return True,"ok"
    except (KeyError, TypeError, ValueError, OverflowError):
        return False,"malformed"

def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)

def build_cas_input(rows: dict, *, session_id: str, source_sha: str, cycle_id: str,
                    underlying_token: int|None = None, observation_timestamp: str|None = None,
                    trading_session_identity: dict|None = None) -> dict|None:
    a,b=rows.get("0915"),rows.get("1000")
    expected_token = underlying_token if underlying_token is not None else (a.get("underlying_token") if a else None)
    if not a or not b or expected_token is None or any(verify_primitive(r,session_id=session_id,source_sha=source_sha,underlying_token=expected_token)[0] is False for r in (a,b)): return None
    ret=float(b["price"])/float(a["price"])-1
    direction="DOWN" if ret>0 else "UP" if ret<0 else "NO_SIGNAL"
    observed_at = observation_timestamp or b["capture_timestamp_ist"]
    event_hashes = sorted([str(a["source_event_sha256"]), str(b["source_event_sha256"])])
    trading_day = datetime.fromtimestamp(float(a["source_timestamp_epoch"]),
        tz=ZoneInfo("Asia/Kolkata")).date().isoformat()
    session_identity = dict(trading_session_identity or {"trading_date": trading_day})
    if session_identity.get("trading_date") != trading_day:
        return None
    evaluation_identity = hashlib.sha256(json.dumps({
        "strategy_id": STRATEGY_ID, "spec_sha": SPEC_SHA,
        "source_sha": source_sha, "session_identity": session_identity,
        "source_event_sha256s": event_hashes,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"strategy_id":STRATEGY_ID,"session_id":session_id,"source_sha":source_sha,
        "cycle_id":cycle_id,"symbol":"NIFTY","signal_input_09_15":a["price"],
        "signal_input_10_00":b["price"],"morning_return":ret,"signal_direction":direction,
        "observation_timestamp":observed_at,"received_timestamp":observed_at,
        "captured_live_prospectively":True,"admissible_for_prospective_campaign":True,
        "source_event_sha256s":event_hashes,"source_run_ids":[session_id],
        "session_identity":session_identity,"evaluation_identity_sha256":evaluation_identity}


def build_same_session_cas_input(current_primitives: dict, references: dict, *,
                                  current_run_id: str, source_sha: str,
                                  cycle_id: str, underlying_token: int,
                                  session_identity: dict,
                                  decision_epoch: float) -> dict | None:
    """Build advisory inputs from verified current and inherited same-day rows."""
    primitives: dict[str, dict] = {}
    lineage: dict[str, dict] = {}
    try:
        for name in ("0915", "1000"):
            local = current_primitives.get(name) if isinstance(current_primitives, dict) else None
            reference = references.get(name) if isinstance(references, dict) else None
            if isinstance(local, dict) and local.get("capture_status") == "CAPTURED":
                row = local
                source_run_id = current_run_id
                valid, _ = verify_primitive(row, session_id=current_run_id,
                    source_sha=source_sha, underlying_token=underlying_token)
                descriptor = {"lineage_status": "CURRENT_RUN_VERIFIED",
                    "original_capture_status": row.get("capture_status"),
                    "source_run_id": source_run_id,
                    "source_record_sha256": row.get("record_sha256"),
                    "session_identity": dict(session_identity),
                    "read_only": True, "is_order_action": False,
                    "broker_api_called": False, "allowed_for_live_execution": False}
            elif isinstance(reference, dict) and isinstance(reference.get("primitive"), dict):
                row = reference["primitive"]
                descriptor = reference.get("lineage")
                source_run_id = descriptor.get("source_run_id") if isinstance(descriptor, dict) else None
                valid, _ = verify_primitive(row, session_id=source_run_id,
                    source_sha=source_sha, underlying_token=underlying_token) if source_run_id else (False, "missing_lineage")
                if (not isinstance(descriptor, dict)
                        or descriptor.get("lineage_status") != "INHERITED_VERIFIED"
                        or descriptor.get("original_capture_status") != "CAPTURED"
                        or source_run_id != row.get("session_id")
                        or source_run_id == current_run_id
                        or descriptor.get("session_identity") != session_identity):
                    return None
            else:
                return None
            if row.get("source_sha") != source_sha:
                return None
            if not valid:
                return None
            source_day = datetime.fromtimestamp(float(row["source_timestamp_epoch"]),
                tz=ZoneInfo("Asia/Kolkata")).date().isoformat()
            if source_day != session_identity.get("trading_date"):
                return None
            if max(float(row["source_timestamp_epoch"]),
                   float(row["receive_timestamp_epoch"]),
                   float(row["timestamp_epoch"])) > float(decision_epoch):
                return None
            primitives[name] = row
            lineage[name] = descriptor
        first, second = primitives["0915"], primitives["1000"]
        morning_return = float(second["price"]) / float(first["price"]) - 1
        direction = "DOWN" if morning_return > 0 else "UP" if morning_return < 0 else "NO_SIGNAL"
        # The authoritative decision observation is the latest captured source
        # event, not the later cycle execution wall clock. This preserves the
        # CAS freshness boundary across delayed/restarted read-only cycles.
        observed_at = datetime.fromtimestamp(float(decision_epoch), tz=timezone.utc).isoformat()
        event_hashes = sorted(row["source_event_sha256"] for row in primitives.values())
        result = {"strategy_id": STRATEGY_ID, "session_id": current_run_id,
            "source_sha": source_sha, "cycle_id": cycle_id, "symbol": "NIFTY",
            "signal_input_09_15": first["price"], "signal_input_10_00": second["price"],
            "morning_return": morning_return, "signal_direction": direction,
            "observation_timestamp": observed_at, "received_timestamp": observed_at,
            "captured_live_prospectively": True, "admissible_for_prospective_campaign": True,
            "source_event_sha256s": sorted(row["source_event_sha256"] for row in primitives.values())}
        run_ids = {item["source_run_id"] for item in lineage.values()}
        if run_ids == {current_run_id}:
            lineage_status = "CURRENT_RUN_VERIFIED"
        elif current_run_id not in run_ids:
            lineage_status = "INHERITED_VERIFIED"
        else:
            lineage_status = "SAME_SESSION_HERITAGE_VERIFIED"
        result["lineage_status"] = lineage_status
        result["lineage"] = lineage
        result["source_run_ids"] = sorted(run_ids)
        result["session_identity"] = dict(session_identity)
        result["evaluation_identity_sha256"] = hashlib.sha256(json.dumps({
            "strategy_id": STRATEGY_ID,
            "spec_sha": SPEC_SHA,
            "source_sha": source_sha,
            "session_identity": session_identity,
            "source_event_sha256s": event_hashes,
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        result["read_only"] = True
        result["is_order_action"] = False
        result["broker_api_called"] = False
        result["allowed_for_live_execution"] = False
        return result
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None


def build_inherited_cas_input(references: dict, *, current_run_id: str,
                              source_sha: str, cycle_id: str,
                              underlying_token: int,
                              session_identity: dict,
                              decision_epoch: float) -> dict | None:
    """Compatibility wrapper for all-inherited same-session source pairs."""
    return build_same_session_cas_input({}, references,
        current_run_id=current_run_id, source_sha=source_sha, cycle_id=cycle_id,
        underlying_token=underlying_token, session_identity=session_identity,
        decision_epoch=decision_epoch)
