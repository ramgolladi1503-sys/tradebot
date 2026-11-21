"""TradingView Level Receiver
==========================
Receives, verifies, and persists daily OptionMate reversal and trend decider levels
from TradingView webhook alerts or client payloads.

Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

import hmac
import hashlib
import json
import math
import os
import re
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union


DEFAULT_RUNTIME_PATH = Path("runtime") / "optionmate_daily_levels.json"
SUPPORTED_INDICES = {"NIFTY", "SENSEX", "BANKNIFTY"}

# Plausible spot price boundaries for Indian indices to guard against corrupted/fat-finger webhook alerts
INDEX_PLAUSIBLE_BOUNDS: Dict[str, Tuple[float, float]] = {
    "NIFTY": (15000.0, 35000.0),
    "BANKNIFTY": (35000.0, 70000.0),
    "SENSEX": (60000.0, 110000.0),
}


@dataclass(frozen=True)
class OptionMateLevelData:
    index_name: str
    trend_decider: float
    rp1_upper: float
    rp2_upper: float
    rp1_lower: float
    rp2_lower: float
    date: str
    spot_open: Optional[float] = None
    updated_at: Optional[str] = None
    sequence: Optional[int] = None

    def validate_hierarchy(self) -> Tuple[bool, str]:
        """Validates structural price level hierarchy:
        rp2_lower < rp1_lower < trend_decider < rp1_upper < rp2_upper
        """
        numeric_values = (self.trend_decider, self.rp1_upper, self.rp2_upper, self.rp1_lower, self.rp2_lower)
        if not all(math.isfinite(value) for value in numeric_values):
            return False, "All level prices must be finite numbers"
        if self.spot_open is not None and not math.isfinite(self.spot_open):
            return False, "spot_open must be a finite number"
        if not (self.rp2_lower < self.rp1_lower):
            return False, f"rp2_lower ({self.rp2_lower}) must be < rp1_lower ({self.rp1_lower})"
        if not (self.rp1_lower < self.trend_decider):
            return False, f"rp1_lower ({self.rp1_lower}) must be < trend_decider ({self.trend_decider})"
        if not (self.trend_decider < self.rp1_upper):
            return False, f"trend_decider ({self.trend_decider}) must be < rp1_upper ({self.rp1_upper})"
        if not (self.rp1_upper < self.rp2_upper):
            return False, f"rp1_upper ({self.rp1_upper}) must be < rp2_upper ({self.rp2_upper})"
        return True, "OK"

    def validate_bounds(self) -> Tuple[bool, str]:
        """Validates that price levels fall within plausible market bounds for the index."""
        bounds = INDEX_PLAUSIBLE_BOUNDS.get(self.index_name.upper())
        if not bounds:
            return True, "OK"
        min_p, max_p = bounds
        for attr in ["rp2_lower", "rp1_lower", "trend_decider", "rp1_upper", "rp2_upper"]:
            val = getattr(self, attr)
            if not (min_p <= val <= max_p):
                return False, f"{attr} ({val}) out of plausible bounds [{min_p}, {max_p}] for {self.index_name}"
        if self.spot_open is not None and not (min_p <= self.spot_open <= max_p):
            return False, f"spot_open ({self.spot_open}) out of plausible bounds [{min_p}, {max_p}] for {self.index_name}"
        return True, "OK"


class TradingViewLevelReceiver:
    """Authenticates, validates, and atomically persists TradingView OptionMate level webhooks."""

    def __init__(
        self,
        secret_key: Optional[str] = None,
        passphrase: Optional[str] = None,
        storage_path: Optional[Union[str, Path]] = None,
        require_auth: bool = True,
    ):
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.storage_path = Path(storage_path) if storage_path else DEFAULT_RUNTIME_PATH
        self.require_auth = require_auth
        self._persist_lock = threading.RLock()

    def verify_hmac(self, payload_bytes: bytes, signature_header: Optional[str]) -> bool:
        """Verifies HMAC SHA256 signature if secret_key is configured."""
        if not self.secret_key:
            return True
        if not signature_header:
            return False
        expected_sig = hmac.new(
            self.secret_key.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        # Header may be "sha256=<hex>" or raw "<hex>"
        cleaned_sig = signature_header.removeprefix("sha256=").strip()
        return hmac.compare_digest(expected_sig.lower(), cleaned_sig.lower())

    def verify_passphrase(self, payload_passphrase: Optional[str]) -> bool:
        """Verifies passphrase in payload if passphrase is configured."""
        if not self.passphrase:
            return True
        if not payload_passphrase:
            return False
        return hmac.compare_digest(self.passphrase, str(payload_passphrase))

    def parse_payload(self, raw_data: Union[str, bytes, Dict[str, Any]]) -> Dict[str, Any]:
        """Parses json string, bytes, or dict into structured dictionary."""
        if isinstance(raw_data, dict):
            return raw_data
        if isinstance(raw_data, bytes):
            return json.loads(raw_data.decode("utf-8"))
        if isinstance(raw_data, str):
            return json.loads(raw_data)
        raise ValueError(f"Unsupported payload type: {type(raw_data)}")

    def validate_timestamp_freshness(
        self,
        timestamp_val: Optional[Union[str, int, float]],
        max_drift_seconds: float = 60.0,
    ) -> Tuple[bool, str]:
        """Vector 13: Validates timestamp freshness (abs(now - timestamp) <= 60s) if timestamp present."""
        if timestamp_val is None:
            return False, "Missing required timestamp"
        try:
            ts_float: float
            if isinstance(timestamp_val, (int, float)):
                ts_float = float(timestamp_val)
                # If milliseconds (e.g. 13 digits), convert to seconds
                if ts_float > 1e11:
                    ts_float = ts_float / 1000.0
            elif isinstance(timestamp_val, str):
                val_str = timestamp_val.strip()
                try:
                    ts_float = float(val_str)
                    if ts_float > 1e11:
                        ts_float = ts_float / 1000.0
                except ValueError:
                    # Parse ISO format datetime string
                    dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
                    ts_float = dt.timestamp()
            else:
                return False, f"Unsupported timestamp format: {type(timestamp_val)}"

            if not math.isfinite(ts_float) or ts_float <= 0:
                return False, "Timestamp must be finite and positive"
            now_ts = datetime.now(timezone.utc).timestamp()
            drift = abs(now_ts - ts_float)
            if drift > max_drift_seconds:
                return False, f"Timestamp drift {drift:.1f}s exceeds freshness window of {max_drift_seconds}s (replay protection)"
            return True, "OK"
        except Exception as e:
            return False, f"Failed to parse timestamp ({timestamp_val}): {e}"

    def validate_date(self, payload_date: Optional[str], session_date: Optional[str] = None) -> Tuple[bool, str]:
        """Ensures payload date matches current session date (YYYY-MM-DD)."""
        expected_date = session_date or datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
        if not payload_date:
            return False, "Missing date in level payload"
        if payload_date != expected_date:
            return False, f"Stale or mismatched date: payload={payload_date}, expected={expected_date}"
        return True, "OK"

    def process_webhook(
        self,
        raw_body: Union[str, bytes, Dict[str, Any]],
        signature_header: Optional[str] = None,
        session_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """End-to-end webhook processing:
        1. Auth verification (HMAC and/or passphrase)
        2. Date verification
        3. Structural hierarchy validation
        4. Atomic persistence (.tmp -> os.replace)
        """
        # Read raw bytes for HMAC
        if isinstance(raw_body, bytes):
            raw_bytes = raw_body
        elif isinstance(raw_body, str):
            raw_bytes = raw_body.encode("utf-8")
        else:
            raw_bytes = json.dumps(raw_body).encode("utf-8")

        # Auth Enforcement (ARCH-SENTINEL-HARDENING-003)
        if self.require_auth and not self.secret_key and not self.passphrase:
            return {
                "success": False,
                "error": "AUTHENTICATION_REQUIRED: No webhook secret or passphrase configured",
                "persisted": False,
                "read_only": True,
                "is_order_action": False,
                "broker_api_called": False,
                "allowed_for_live_execution": False,
            }

        # 1. HMAC Verification
        if not self.verify_hmac(raw_bytes, signature_header):
            return {
                "success": False,
                "error": "AUTHENTICATION_FAILED: Invalid HMAC signature",
                "persisted": False,
                "read_only": True,
                "is_order_action": False,
                "broker_api_called": False,
                "allowed_for_live_execution": False,
            }

        try:
            payload = self.parse_payload(raw_body)
        except Exception as e:
            return {
                "success": False,
                "error": f"INVALID_JSON: {e}",
                "persisted": False,
                "read_only": True,
                "is_order_action": False,
                "broker_api_called": False,
                "allowed_for_live_execution": False,
            }

        # 2. Passphrase Verification
        payload_passphrase = payload.get("passphrase") or payload.get("secret")
        if not self.verify_passphrase(payload_passphrase):
            return {
                "success": False,
                "error": "AUTHENTICATION_FAILED: Invalid passphrase",
                "persisted": False,
                "read_only": True,
                "is_order_action": False,
                "broker_api_called": False,
                "allowed_for_live_execution": False,
            }

        expected_date = session_date or datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")

        # Format could be single index {"index": "NIFTY", ...} or multi-index {"NIFTY": {...}, "SENSEX": {...}}
        levels_to_save: Dict[str, Dict[str, Any]] = {}

        if "index" in payload or "index_name" in payload or "trend_decider" in payload:
            raw_index = payload.get("index") or payload.get("index_name")
            idx_name = str(raw_index or "").upper().strip()
            if idx_name not in SUPPORTED_INDICES:
                return {
                    "success": False,
                    "error": "UNKNOWN_OR_MISSING_INDEX: Explicit supported index required",
                    "persisted": False,
                    "read_only": True,
                    "is_order_action": False,
                    "broker_api_called": False,
                    "allowed_for_live_execution": False,
                }
            indices_payload = {idx_name: payload}
        else:
            # Multi-index or root dict containing indices
            indices_payload = {
                k.upper(): v for k, v in payload.items()
                if isinstance(v, dict) and k.upper() in SUPPORTED_INDICES
            }

        if not indices_payload:
            return {
                "success": False,
                "error": "NO_VALID_INDEX_DATA: No recognised index data found in payload",
                "persisted": False,
                "read_only": True,
                "is_order_action": False,
                "broker_api_called": False,
                "allowed_for_live_execution": False,
            }

        validated_levels: Dict[str, OptionMateLevelData] = {}

        for idx_name, data in indices_payload.items():
            # Vector 13: Timestamp freshness / replay check
            ts_val = data.get("timestamp") if data.get("timestamp") is not None else payload.get("timestamp")
            ok_ts, err_ts = self.validate_timestamp_freshness(ts_val)
            if not ok_ts:
                return {
                    "success": False,
                    "error": f"TIMESTAMP_VALIDATION_FAILED [{idx_name}]: {err_ts}",
                    "persisted": False,
                }

            sequence_val = data.get("sequence") if data.get("sequence") is not None else payload.get("sequence")
            try:
                sequence_number = float(sequence_val)
                if isinstance(sequence_val, bool) or not math.isfinite(sequence_number) or not sequence_number.is_integer():
                    raise ValueError("sequence must be a positive integer")
                sequence = int(sequence_number)
                if sequence <= 0:
                    raise ValueError("sequence must be a positive integer")
            except (TypeError, ValueError, OverflowError):
                return {
                    "success": False,
                    "error": f"SEQUENCE_VALIDATION_FAILED [{idx_name}]: Missing or invalid positive sequence",
                    "persisted": False,
                    "read_only": True,
                    "is_order_action": False,
                    "broker_api_called": False,
                    "allowed_for_live_execution": False,
                }

            date_val = data.get("date") or payload.get("date")
            ok_date, err_date = self.validate_date(date_val, expected_date)
            if not ok_date:
                return {
                    "success": False,
                    "error": f"DATE_VALIDATION_FAILED [{idx_name}]: {err_date}",
                    "persisted": False,
                }

            try:
                level_obj = OptionMateLevelData(
                    index_name=idx_name,
                    trend_decider=float(data["trend_decider"]),
                    rp1_upper=float(data["rp1_upper"]),
                    rp2_upper=float(data["rp2_upper"]),
                    rp1_lower=float(data["rp1_lower"]),
                    rp2_lower=float(data["rp2_lower"]),
                    date=date_val,
                    spot_open=float(data.get("spot_open", data["trend_decider"])) if data.get("spot_open") is not None else None,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                    sequence=sequence,
                )
            except (KeyError, ValueError, TypeError) as e:
                return {
                    "success": False,
                    "error": f"SCHEMA_VALIDATION_FAILED [{idx_name}]: Missing or invalid level keys ({e})",
                    "persisted": False,
                }

            ok_hier, err_hier = level_obj.validate_hierarchy()
            if not ok_hier:
                return {
                    "success": False,
                    "error": f"HIERARCHY_VALIDATION_FAILED [{idx_name}]: {err_hier}",
                    "persisted": False,
                }

            # Vector 1: Plausible bounds validation
            ok_bounds, err_bounds = level_obj.validate_bounds()
            if not ok_bounds:
                return {
                    "success": False,
                    "error": f"BOUNDS_VALIDATION_FAILED [{idx_name}]: {err_bounds}",
                    "persisted": False,
                }

            validated_levels[idx_name] = level_obj

        # 4. Atomic File Persistence
        try:
            persisted_file = self.atomic_persist(validated_levels)
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "persisted": False,
                "read_only": True,
                "is_order_action": False,
                "broker_api_called": False,
                "allowed_for_live_execution": False,
            }

        return {
            "success": True,
            "indices": list(validated_levels.keys()),
            "persisted_path": str(persisted_file),
            "persisted": True,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "allowed_for_live_execution": False,
        }

    def atomic_persist(self, validated_levels: Dict[str, OptionMateLevelData]) -> Path:
        """Atomically persists levels to storage_path (.tmp -> os.replace)."""
        with self._persist_lock:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            existing: Dict[str, Any] = {}
            if self.storage_path.exists():
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception as exc:
                    raise ValueError("Existing level state is unreadable; refusing overwrite") from exc

            for idx_name, lvl in validated_levels.items():
                old = existing.get(idx_name) or {}
                if old.get("date") == lvl.date:
                    try:
                        old_sequence = int(old.get("sequence", 0))
                    except (TypeError, ValueError):
                        raise ValueError(f"Existing sequence is invalid for {idx_name}; refusing overwrite")
                    if lvl.sequence is None or lvl.sequence <= old_sequence:
                        raise ValueError(f"Out-of-order or duplicate sequence for {idx_name}; refusing overwrite")
                existing[idx_name] = asdict(lvl)

            tmp_path = self.storage_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, self.storage_path)
            return self.storage_path
